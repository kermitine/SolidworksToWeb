import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import cv2
from flask import Flask, abort, jsonify, render_template_string, request, send_from_directory, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from main import mp4_to_transparent_webm_and_apng, version


BASE_DIR = Path(__file__).resolve().parent


def env_int(name, default, minimum=None):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def env_float(name, default, minimum=None):
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


OUTPUT_ROOT = Path(os.environ.get("SWTOWEB_OUTPUT_DIR", BASE_DIR / "output")).resolve()
MAX_UPLOAD_MB = env_int("SWTOWEB_MAX_UPLOAD_MB", 512, minimum=1)
MAX_LOG_LINES = env_int("SWTOWEB_MAX_LOG_LINES", 250, minimum=25)
RETENTION_HOURS = env_float("SWTOWEB_RETENTION_HOURS", 24, minimum=0.25)
CLEANUP_INTERVAL_SECONDS = env_int("SWTOWEB_CLEANUP_INTERVAL_MINUTES", 30, minimum=5) * 60
MAX_ACTIVE_JOBS = env_int("SWTOWEB_MAX_ACTIVE_JOBS", 1, minimum=1)
FRAME_ANCESTORS = os.environ.get(
    "SWTOWEB_FRAME_ANCESTORS",
    "'self' https://ayriknabirahni.com https://www.ayriknabirahni.com",
)
ALLOWED_CORNERS = {"avg", "tl", "tr", "bl", "br"}
OUTPUT_EXTENSIONS = {".webm", ".png"}
JOB_ID_RE = re.compile(r"^[a-f0-9]{32}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["SECRET_KEY"] = os.environ.get("SWTOWEB_SECRET_KEY") or os.urandom(32)

JOBS = {}
JOBS_LOCK = threading.Lock()
CLEANUP_STARTED = False


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SolidworksToWeb</title>
  <link rel="icon" href="{{ url_for('asset_file', filename='icon.ico') }}" sizes="any">
  <style>
    :root {
      color-scheme: dark;
      --ink: #f4f7f8;
      --muted: #9ca9b2;
      --line: #303942;
      --panel: #151a20;
      --panel-2: #101419;
      --page: #090c10;
      --field: #0d1117;
      --accent: #f90000;
      --accent-dark: #b90000;
      --accent-soft: rgba(249, 0, 0, 0.16);
      --accent-line: rgba(249, 0, 0, 0.58);
      --danger: #ff6a62;
      --success: #8ee4b8;
      --console: #020202;
      --console-text: #d8ffd8;
    }

    * { box-sizing: border-box; }

    [hidden] { display: none !important; }

    h1,
    h2,
    h3,
    p,
    label,
    legend,
    summary,
    button,
    .button,
    .help-link,
    .notice,
    .error,
    .status-pill {
      min-width: 0;
      overflow-wrap: normal;
      word-break: normal;
    }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #10141a 0%, var(--page) 44%);
      min-height: 100vh;
    }

    body.embed-mode {
      min-height: 0;
      background: var(--page);
    }

    .shell {
      width: min(1060px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0;
    }

    .embed-mode .shell {
      width: min(100% - 24px, 1020px);
      padding: 12px 0;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 20px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }

    .brand img {
      width: 42px;
      height: 42px;
      flex: 0 0 auto;
      filter: drop-shadow(0 0 18px rgba(249, 0, 0, 0.32));
    }

    h1 {
      margin: 0;
      font-size: 24px;
      line-height: 1.1;
      letter-spacing: 0;
    }

    .version {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .help-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      max-width: 100%;
      color: var(--ink);
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-2);
      padding: 7px 10px;
      font-size: 13px;
      font-weight: 750;
      line-height: 1.15;
      text-align: center;
      text-decoration: none;
    }

    .help-link:hover {
      border-color: var(--accent-line);
      background: var(--accent-soft);
    }

    main {
      display: grid;
      grid-template-columns: minmax(0, 420px) minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }

    main > * {
      min-width: 0;
    }

    .tool,
    .result,
    .empty {
      min-width: 0;
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01)), var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 18px 60px rgba(0, 0, 0, 0.25);
    }

    .tool {
      padding: 18px;
    }

    .embed-mode main {
      grid-template-columns: minmax(0, 400px) minmax(0, 1fr);
      gap: 14px;
    }

    .field {
      display: grid;
      gap: 8px;
      margin-bottom: 16px;
    }

    label,
    legend {
      color: var(--ink);
      font-weight: 650;
      font-size: 14px;
    }

    input[type="file"],
    input[type="number"] {
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--field);
      color: var(--ink);
      padding: 9px 10px;
      font: inherit;
    }

    input[type="file"]::file-selector-button {
      border: 0;
      border-radius: 5px;
      background: #242c34;
      color: var(--ink);
      padding: 7px 11px;
      margin-right: 10px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }

    input[type="file"]::file-selector-button:hover {
      background: #313b45;
    }

    input[type="number"]:focus,
    input[type="file"]:focus {
      border-color: var(--accent-line);
      outline: 2px solid var(--accent-soft);
      outline-offset: 0;
    }

    fieldset {
      padding: 0;
      margin: 0 0 16px;
      border: 0;
    }

    .segments {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
      gap: 6px;
      margin-top: 8px;
    }

    .segments label {
      min-width: 0;
    }

    .segments input {
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }

    .segments span {
      display: grid;
      width: 100%;
      min-height: 38px;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel-2);
      color: var(--muted);
      padding: 8px 10px;
      font-size: 13px;
      font-weight: 700;
      line-height: 1.1;
      text-align: center;
      white-space: normal;
      cursor: pointer;
    }

    .segments input:checked + span {
      border-color: var(--accent);
      background: var(--accent-soft);
      color: #fff;
      box-shadow: inset 0 0 0 1px rgba(249, 0, 0, 0.2);
    }

    details {
      border-top: 1px solid var(--line);
      padding-top: 14px;
      margin-bottom: 18px;
    }

    summary {
      cursor: pointer;
      color: var(--muted);
      font-weight: 650;
      margin-bottom: 12px;
    }

    .advanced-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    button,
    .button {
      appearance: none;
      display: inline-grid;
      max-width: 100%;
      min-height: 42px;
      place-items: center;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      padding: 0 16px;
      font: inherit;
      font-weight: 750;
      line-height: 1.15;
      text-align: center;
      text-decoration: none;
      cursor: pointer;
      box-shadow: 0 10px 24px rgba(249, 0, 0, 0.18);
    }

    button:hover,
    .button:hover {
      background: var(--accent-dark);
    }

    .button.secondary {
      background: #2b333d;
      box-shadow: none;
    }

    .button.secondary:hover {
      background: #3a4551;
    }

    .error {
      border: 1px solid rgba(255, 106, 98, 0.42);
      background: rgba(255, 106, 98, 0.1);
      color: var(--danger);
      border-radius: 6px;
      padding: 10px 12px;
      margin-bottom: 16px;
      font-size: 14px;
      line-height: 1.4;
    }

    .notice {
      border: 1px solid rgba(255, 255, 255, 0.1);
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted);
      border-radius: 6px;
      padding: 10px 12px;
      margin-bottom: 16px;
      font-size: 13px;
      line-height: 1.45;
    }

    .result {
      overflow: hidden;
    }

    .result-body,
    .empty {
      padding: 18px;
    }

    .result-head {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }

    .result-body h2,
    .empty h2 {
      margin: 0 0 8px;
      font-size: 18px;
      letter-spacing: 0;
    }

    .result-body p,
    .empty p {
      margin: 0 0 14px;
      color: var(--muted);
      line-height: 1.45;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      background: var(--panel-2);
      padding: 5px 9px;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.1;
      text-align: center;
      text-transform: uppercase;
    }

    .status-pill.running,
    .status-pill.queued {
      border-color: var(--accent-line);
      color: #fff;
      background: var(--accent-soft);
    }

    .status-pill.complete {
      border-color: rgba(142, 228, 184, 0.45);
      color: var(--success);
      background: rgba(142, 228, 184, 0.12);
    }

    .status-pill.failed {
      border-color: rgba(255, 106, 98, 0.45);
      color: var(--danger);
      background: rgba(255, 106, 98, 0.12);
    }

    .progress-wrap {
      display: grid;
      gap: 8px;
      margin: 12px 0 14px;
    }

    .progress-meta {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }

    .progress-track {
      height: 12px;
      border-radius: 999px;
      background: #080a0d;
      border: 1px solid var(--line);
      overflow: hidden;
    }

    .progress-fill {
      width: 0%;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, #8f0000, var(--accent));
      box-shadow: 0 0 20px rgba(249, 0, 0, 0.5);
      transition: width 280ms ease;
    }

    .console {
      min-height: 180px;
      max-height: 280px;
      margin: 0;
      overflow: auto;
      border: 1px solid #202020;
      border-radius: 6px;
      background: var(--console);
      color: var(--console-text);
      padding: 12px;
      font: 13px/1.45 Consolas, "Courier New", monospace;
      white-space: pre-wrap;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }

    .console::selection {
      background: var(--accent);
      color: #fff;
    }

    .preview {
      min-height: 300px;
      display: grid;
      place-items: center;
      background-color: #171d22;
      background-image:
        linear-gradient(45deg, rgba(255,255,255,.06) 25%, transparent 25%),
        linear-gradient(-45deg, rgba(255,255,255,.06) 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, rgba(255,255,255,.06) 75%),
        linear-gradient(-45deg, transparent 75%, rgba(255,255,255,.06) 75%);
      background-position: 0 0, 0 10px, 10px -10px, -10px 0;
      background-size: 20px 20px;
      border-top: 1px solid var(--line);
    }

    .preview video {
      width: min(100%, 520px);
      max-height: 420px;
      display: block;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }

    .actions .button {
      flex: 1 1 150px;
    }

    .embed-help {
      margin-top: 16px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }

    .embed-help h3 {
      margin: 0 0 6px;
      font-size: 15px;
      letter-spacing: 0;
    }

    .embed-help p {
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }

    .embed-code {
      max-height: 280px;
      overflow: auto;
      margin: 0;
      border: 1px solid #242a31;
      border-radius: 6px;
      background: #07090c;
      color: #f2f5f7;
      padding: 12px;
      font: 12px/1.45 Consolas, "Courier New", monospace;
      white-space: pre;
    }

    @media (max-width: 820px) {
      .shell { width: min(100% - 24px, 640px); padding: 18px 0; }
      header { align-items: flex-start; }
      .header-actions { align-items: flex-end; }
      main { grid-template-columns: 1fr; }
      .advanced-grid { grid-template-columns: 1fr; }
      .segments { grid-template-columns: repeat(auto-fit, minmax(112px, 1fr)); }
      .result-head { align-items: flex-start; }
    }

    @media (max-width: 420px) {
      .shell,
      .embed-mode .shell {
        width: min(100% - 16px, 640px);
      }

      .tool,
      .result-body,
      .empty {
        padding: 14px;
      }

      .notice,
      .error {
        padding: 9px 10px;
      }

      .segments {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .result-head {
        flex-direction: column;
      }
    }
  </style>
</head>
<body class="{% if embed_mode %}embed-mode{% endif %}">
  <div class="shell">
    <header {% if embed_mode %}hidden{% endif %}>
      <div class="brand">
        <img src="{{ url_for('asset_file', filename='icon.ico') }}" alt="">
        <h1>SolidworksToWeb</h1>
      </div>
      <div class="header-actions">
        <a class="help-link" href="https://github.com/kermitine/SolidworksToWeb#how-to-use" target="_blank" rel="noopener noreferrer">How to use</a>
        <div class="version">v{{ version }}</div>
      </div>
    </header>

    <main>
      <form class="tool" action="{{ url_for('index', embed=1) if embed_mode else url_for('index') }}" method="post" enctype="multipart/form-data">
        {% if embed_mode %}
          <input type="hidden" name="_embed" value="1">
        {% endif %}
        {% if error %}
          <div class="error">{{ error }}</div>
        {% endif %}

        <div class="notice">Generated server files are deleted after {{ retention_label }}.</div>

        <div class="field">
          <label for="file">MP4 source</label>
          <input id="file" name="file" type="file" accept="video/mp4" required>
        </div>

        <fieldset>
          <legend>Background sample</legend>
          <div class="segments">
            {% for value, label in corners %}
              <label>
                <input type="radio" name="corner" value="{{ value }}" {% if value == selected_corner %}checked{% endif %}>
                <span>{{ label }}</span>
              </label>
            {% endfor %}
          </div>
        </fieldset>

        <details>
          <summary>Processing</summary>
          <div class="advanced-grid">
            <div class="field">
              <label for="threshold">Threshold</label>
              <input id="threshold" name="threshold" type="number" min="1" max="255" value="{{ threshold }}">
            </div>
            <div class="field">
              <label for="softness">Softness</label>
              <input id="softness" name="softness" type="number" min="1" max="50" value="{{ softness }}">
            </div>
            <div class="field">
              <label for="pad">Crop pad</label>
              <input id="pad" name="pad" type="number" min="0" max="240" value="{{ pad }}">
            </div>
            <div class="field">
              <label for="sample_every">Sample frames</label>
              <input id="sample_every" name="sample_every" type="number" min="1" max="120" value="{{ sample_every }}">
            </div>
          </div>
        </details>

        <button type="submit">Convert</button>
      </form>

      {% if job %}
        <section class="result" data-job-id="{{ job.id }}" aria-live="polite">
          <div class="result-body">
            <div class="result-head">
              <div>
                <h2 data-role="title">{{ job.title }}</h2>
                <p data-role="message">{{ job.message }}</p>
              </div>
              <span class="status-pill {{ job.status }}" data-role="status">{{ job.status }}</span>
            </div>

            <div class="progress-wrap">
              <div class="progress-meta">
                <span>Progress</span>
                <strong data-role="progress-text">{{ job.progress }}%</strong>
              </div>
              <div class="progress-track" aria-hidden="true">
                <div class="progress-fill" data-role="progress-fill" style="width: {{ job.progress }}%"></div>
              </div>
            </div>

            <pre class="console" data-role="logs">{{ job.logs | join('\\n') }}</pre>

            <div class="actions" data-role="actions" {% if job.status != "complete" %}hidden{% endif %}>
              <a class="button" data-role="webm-link" href="{{ job.webm_url or '#' }}" download>Download WebM</a>
              <a class="button secondary" data-role="apng-link" href="{{ job.apng_url or '#' }}" download>Download APNG</a>
            </div>
            <p data-role="expiry-note" {% if job.status != "complete" %}hidden{% endif %}>Temporary server files expire after {{ retention_label }}.</p>

            <div class="embed-help" data-role="embed-help" {% if job.status != "complete" %}hidden{% endif %}>
              <h3>Website Compatibility Embed</h3>
              <p>Upload both generated files to your website or CDN, then replace these sample URLs with those public file URLs. The download links above are temporary local server files.</p>
              <pre class="embed-code" data-role="embed-code">&lt;div class=&quot;alpha-anim&quot;&gt;
  &lt;video class=&quot;alpha-webm&quot; autoplay loop muted playsinline&gt;
    &lt;source src=&quot;https://ayriknabirahni.com/wp-content/uploads/2026/08/ffsign.webm&quot; type=&quot;video/webm&quot;&gt;
  &lt;/video&gt;

  &lt;img class=&quot;alpha-apng&quot; src=&quot;https://ayriknabirahni.com/wp-content/uploads/2026/08/ffsign.png&quot; alt=&quot;&quot;&gt;
&lt;/div&gt;

&lt;script&gt;
(function () {
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
                (navigator.platform === &quot;MacIntel&quot; &amp;&amp; navigator.maxTouchPoints &gt; 1);

  if (isIOS) {
    document.querySelectorAll(&quot;.alpha-anim&quot;).forEach(wrap =&gt; {
      const v = wrap.querySelector(&quot;.alpha-webm&quot;);
      const i = wrap.querySelector(&quot;.alpha-apng&quot;);
      if (v) v.style.display = &quot;none&quot;;
      if (i) i.style.display = &quot;block&quot;;
    });
  }
})();
&lt;/script&gt;

&lt;style&gt;
.alpha-anim {
  position: relative;
  width: 100%;
}

.alpha-webm,
.alpha-apng {
  display: block;
  width: 100%;
  height: auto;
  background: transparent;
}

.alpha-apng {
  display: none;
}
&lt;/style&gt;</pre>
            </div>
          </div>
          <div class="preview" data-role="preview" {% if job.status != "complete" %}hidden{% endif %}>
            <video autoplay loop muted playsinline controls data-role="video">
              {% if job.webm_url %}
                <source src="{{ job.webm_url }}" type="video/webm">
              {% endif %}
            </video>
          </div>
        </section>
      {% else %}
        <section class="empty">
          <h2>Ready</h2>
          <p>MP4 input pending.</p>
        </section>
      {% endif %}
    </main>
  </div>

  <script>
    const panel = document.querySelector("[data-job-id]");
    const embedMode = document.body.classList.contains("embed-mode");

    function postEmbedHeight() {
      if (!embedMode || window.parent === window) return;
      const shell = document.querySelector(".shell");
      const shellRect = shell ? shell.getBoundingClientRect() : document.body.getBoundingClientRect();
      const height = Math.ceil(shellRect.top + shellRect.height + 4);
      window.parent.postMessage({ type: "swtoweb:resize", height }, "*");
    }

    function setText(role, value) {
      const node = panel.querySelector(`[data-role="${role}"]`);
      if (node) node.textContent = value;
    }

    function updateJob(job) {
      const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
      const fill = panel.querySelector('[data-role="progress-fill"]');
      const status = panel.querySelector('[data-role="status"]');
      const logs = panel.querySelector('[data-role="logs"]');
      const actions = panel.querySelector('[data-role="actions"]');
      const preview = panel.querySelector('[data-role="preview"]');
      const video = panel.querySelector('[data-role="video"]');
      const webmLink = panel.querySelector('[data-role="webm-link"]');
      const apngLink = panel.querySelector('[data-role="apng-link"]');
      const embedHelp = panel.querySelector('[data-role="embed-help"]');
      const expiryNote = panel.querySelector('[data-role="expiry-note"]');

      if (fill) fill.style.width = `${progress}%`;
      setText("progress-text", `${progress}%`);
      setText("message", job.message || job.status);

      if (status) {
        status.textContent = job.status || "running";
        status.className = `status-pill ${job.status || "running"}`;
      }

      if (logs) {
        logs.textContent = (job.logs || []).join("\\n");
        logs.scrollTop = logs.scrollHeight;
      }

      if (job.status === "complete") {
        if (webmLink) webmLink.href = job.webm_url;
        if (apngLink) apngLink.href = job.apng_url;
        if (actions) actions.hidden = false;
        if (embedHelp) embedHelp.hidden = false;
        if (expiryNote) expiryNote.hidden = false;
        if (preview) preview.hidden = false;
        if (video && job.webm_url && !video.querySelector("source")) {
          const source = document.createElement("source");
          source.src = job.webm_url;
          source.type = "video/webm";
          video.appendChild(source);
          video.load();
        }
      }

      postEmbedHeight();
    }

    async function pollJob() {
      if (!panel) return;

      try {
        const response = await fetch(`/jobs/${panel.dataset.jobId}`, { cache: "no-store" });
        if (!response.ok) throw new Error(`status ${response.status}`);
        const job = await response.json();
        updateJob(job);

        if (job.status === "queued" || job.status === "running") {
          window.setTimeout(pollJob, 900);
        }
      } catch (error) {
        setText("message", "Status check failed");
        window.setTimeout(pollJob, 2000);
        postEmbedHeight();
      }
    }

    if (panel) {
      pollJob();
    }

    if (embedMode) {
      window.addEventListener("load", postEmbedHeight);
      window.addEventListener("resize", postEmbedHeight);
      if ("ResizeObserver" in window) {
        new ResizeObserver(postEmbedHeight).observe(document.querySelector(".shell"));
      }
      postEmbedHeight();
      let embedPingCount = 0;
      const embedPingTimer = window.setInterval(() => {
        postEmbedHeight();
        embedPingCount += 1;
        if (embedPingCount >= 10) {
          window.clearInterval(embedPingTimer);
        }
      }, 1000);
    }
  </script>
</body>
</html>
"""


def clamp_int(raw_value, default, minimum, maximum):
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def clean_stem(filename):
    cleaned = secure_filename(filename)
    stem = Path(cleaned).stem
    return stem or "animation"


def get_video_fps(path):
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
    finally:
        cap.release()
    if not fps or fps < 1:
        return 30
    return fps


def retention_label():
    if RETENTION_HOURS >= 1:
        return f"{RETENTION_HOURS:g} hours"
    return f"{int(RETENTION_HOURS * 60)} minutes"


def is_valid_job_id(job_id):
    return bool(JOB_ID_RE.fullmatch(job_id or ""))


def jobs_root():
    return OUTPUT_ROOT / "jobs"


def newest_mtime(path):
    try:
        latest = path.stat().st_mtime
    except OSError:
        return 0

    if not path.is_dir():
        return latest

    for child in path.rglob("*"):
        try:
            latest = max(latest, child.stat().st_mtime)
        except OSError:
            continue
    return latest


def active_job_ids():
    with JOBS_LOCK:
        return {
            job_id
            for job_id, job in JOBS.items()
            if job.get("status") in {"queued", "running"}
        }


def active_job_count():
    return len(active_job_ids())


def cleanup_expired_jobs():
    root = jobs_root()
    root.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - (RETENTION_HOURS * 60 * 60)
    active_ids = active_job_ids()

    for job_dir in root.iterdir():
        if not job_dir.is_dir() or job_dir.name in active_ids:
            continue
        if newest_mtime(job_dir) < cutoff:
            shutil.rmtree(job_dir, ignore_errors=True)

    with JOBS_LOCK:
        expired_job_ids = [
            job_id
            for job_id, job in JOBS.items()
            if job.get("status") not in {"queued", "running"}
            and job.get("created_at", 0) < cutoff
        ]
        for job_id in expired_job_ids:
            JOBS.pop(job_id, None)


def cleanup_loop():
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        cleanup_expired_jobs()


def start_cleanup_thread():
    global CLEANUP_STARTED
    if CLEANUP_STARTED:
        return
    CLEANUP_STARTED = True
    cleanup_expired_jobs()
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()


def looks_like_mp4(path):
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return False
    return len(header) >= 12 and header[4:8] == b"ftyp"


def now_label():
    return datetime.now().strftime("%H:%M:%S")


def add_log(job_id, message):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["logs"].append(f"{now_label()}  {message}")
        job["logs"] = job["logs"][-MAX_LOG_LINES:]


def update_job(job_id, **fields):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def set_job_progress(job_id, progress, message=None):
    fields = {"progress": max(0, min(100, int(progress)))}
    if message:
        fields["message"] = message
    update_job(job_id, **fields)


def snapshot_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        snapshot = dict(job)
        snapshot["logs"] = list(job["logs"])
        return snapshot


def create_job(job_id, title):
    job = {
        "id": job_id,
        "title": title,
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "logs": [f"{now_label()}  Job queued"],
        "webm_url": None,
        "apng_url": None,
        "error": None,
        "created_at": time.time(),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    return job


def run_conversion_job(
    job_id,
    input_path,
    webm_path,
    apng_path,
    threshold,
    softness,
    sample_every,
    pad,
    corner,
):
    def log(message):
        add_log(job_id, message)

    def progress(value, message=None):
        set_job_progress(job_id, value, message)

    update_job(job_id, status="running", message="Starting", progress=0)
    add_log(job_id, f"Source: {input_path.name}")

    try:
        fps = get_video_fps(input_path)
        add_log(job_id, f"Detected source FPS: {fps:.2f}")
        mp4_to_transparent_webm_and_apng(
            str(input_path),
            str(webm_path),
            str(apng_path),
            fps=fps,
            thr=threshold,
            s=softness,
            sample_every_frames=sample_every,
            pad=pad,
            corner=corner,
            log_callback=log,
            progress_callback=progress,
        )
        update_job(
            job_id,
            status="complete",
            progress=100,
            message="Complete",
            webm_url=f"/output/{job_id}/{webm_path.name}",
            apng_url=f"/output/{job_id}/{apng_path.name}",
        )
    except Exception as exc:
        add_log(job_id, f"ERROR: {exc}")
        update_job(job_id, status="failed", message="Failed", error=str(exc))
    finally:
        input_path.unlink(missing_ok=True)
        shutil.rmtree(webm_path.parent / "apng_frames", ignore_errors=True)


def render_page(error=None, job=None):
    embed_mode = request.args.get("embed") == "1" or request.form.get("_embed") == "1"
    return render_template_string(
        PAGE,
        version=version,
        error=error,
        job=job,
        retention_label=retention_label(),
        embed_mode=embed_mode,
        corners=[
            ("avg", "Average"),
            ("tl", "Top Left"),
            ("tr", "Top Right"),
            ("bl", "Bottom Left"),
            ("br", "Bottom Right"),
        ],
        selected_corner=request.form.get("corner", "avg"),
        threshold=clamp_int(request.form.get("threshold"), 135, 1, 255),
        softness=clamp_int(request.form.get("softness"), 12, 1, 50),
        pad=clamp_int(request.form.get("pad"), 10, 0, 240),
        sample_every=clamp_int(request.form.get("sample_every"), 10, 1, 120),
    )


@app.after_request
def set_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", f"frame-ancestors {FRAME_ANCESTORS}")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.path.startswith("/jobs/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index_get():
    return render_page()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/")
def index():
    cleanup_expired_jobs()
    if active_job_count() >= MAX_ACTIVE_JOBS:
        return render_page(error="The converter is busy. Please try again in a few minutes."), 429

    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return render_page(error="Choose an MP4 file first."), 400

    source_name = secure_filename(uploaded.filename)
    if not source_name or Path(source_name).suffix.lower() != ".mp4":
        return render_page(error="Only MP4 uploads are supported."), 400

    corner = request.form.get("corner", "avg")
    if corner not in ALLOWED_CORNERS:
        return render_page(error="Choose a valid background sample."), 400

    threshold = clamp_int(request.form.get("threshold"), 135, 1, 255)
    softness = clamp_int(request.form.get("softness"), 12, 1, 50)
    pad = clamp_int(request.form.get("pad"), 10, 0, 240)
    sample_every = clamp_int(request.form.get("sample_every"), 10, 1, 120)

    job_id = uuid.uuid4().hex
    title = clean_stem(source_name)
    job_dir = OUTPUT_ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / source_name
    webm_path = job_dir / f"{title}.webm"
    apng_path = job_dir / f"{title}.png"
    uploaded.save(input_path)

    if not looks_like_mp4(input_path):
        shutil.rmtree(job_dir, ignore_errors=True)
        return render_page(error="That file does not look like a valid MP4."), 400

    job = create_job(job_id, title)
    worker = threading.Thread(
        target=run_conversion_job,
        args=(
            job_id,
            input_path,
            webm_path,
            apng_path,
            threshold,
            softness,
            sample_every,
            pad,
            corner,
        ),
        daemon=True,
    )
    worker.start()

    return render_page(job=snapshot_job(job_id) or job)


@app.get("/jobs/<job_id>")
def job_status(job_id):
    if not is_valid_job_id(job_id):
        return jsonify({"error": "Job not found"}), 404
    job = snapshot_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.get("/output/<job_id>/<path:filename>")
def download_file(job_id, filename):
    requested = Path(filename)
    if (
        not is_valid_job_id(job_id)
        or "/" in filename
        or "\\" in filename
        or requested.name != filename
        or requested.suffix.lower() not in OUTPUT_EXTENSIONS
    ):
        abort(404)
    return send_from_directory(OUTPUT_ROOT / "jobs" / job_id, filename, as_attachment=False)


@app.get("/assets/<path:filename>")
def asset_file(filename):
    if filename != "icon.ico":
        abort(404)
    return send_from_directory(BASE_DIR / "assets", filename)


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(BASE_DIR / "assets", "icon.ico")


@app.errorhandler(RequestEntityTooLarge)
def file_too_large(_error):
    return render_page(error=f"Uploads are limited to {MAX_UPLOAD_MB} MB."), 413


start_cleanup_thread()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), threaded=True)
