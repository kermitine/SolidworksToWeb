import os
import shutil
import uuid
from pathlib import Path

import cv2
from flask import Flask, render_template_string, request, send_from_directory, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from main import mp4_to_transparent_webm_and_apng, version


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = Path(os.environ.get("SWTOWEB_OUTPUT_DIR", BASE_DIR / "output")).resolve()
MAX_UPLOAD_MB = int(os.environ.get("SWTOWEB_MAX_UPLOAD_MB", "512"))
ALLOWED_CORNERS = {"avg", "tl", "tr", "bl", "br"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["SECRET_KEY"] = os.environ.get("SWTOWEB_SECRET_KEY", "local-dev")


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SolidworksToWeb</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172026;
      --muted: #66747d;
      --line: #d7dee2;
      --panel: #ffffff;
      --page: #f4f7f6;
      --accent: #0f8f83;
      --accent-dark: #0b6d65;
      --warn: #a66200;
      --danger: #b42318;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--page);
    }

    .shell {
      width: min(1040px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0;
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

    main {
      display: grid;
      grid-template-columns: minmax(0, 420px) minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }

    .tool,
    .result,
    .empty {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(23, 32, 38, 0.04);
    }

    .tool {
      padding: 18px;
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
      background: #fff;
      color: var(--ink);
      padding: 9px 10px;
      font: inherit;
    }

    fieldset {
      padding: 0;
      margin: 0 0 16px;
      border: 0;
    }

    .segments {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 6px;
      margin-top: 8px;
    }

    .segments input {
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }

    .segments span {
      display: grid;
      min-height: 38px;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }

    .segments input:checked + span {
      border-color: var(--accent);
      background: #e9f7f5;
      color: var(--accent-dark);
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
      min-height: 42px;
      place-items: center;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      padding: 0 16px;
      font: inherit;
      font-weight: 750;
      text-decoration: none;
      cursor: pointer;
    }

    button:hover,
    .button:hover {
      background: var(--accent-dark);
    }

    .button.secondary {
      background: #26343b;
    }

    .button.secondary:hover {
      background: #172026;
    }

    .error {
      border: 1px solid #f3b8b2;
      background: #fff3f1;
      color: var(--danger);
      border-radius: 6px;
      padding: 10px 12px;
      margin-bottom: 16px;
      font-size: 14px;
    }

    .result {
      overflow: hidden;
    }

    .preview {
      min-height: 300px;
      display: grid;
      place-items: center;
      background-color: #dfe7e4;
      background-image:
        linear-gradient(45deg, rgba(255,255,255,.56) 25%, transparent 25%),
        linear-gradient(-45deg, rgba(255,255,255,.56) 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, rgba(255,255,255,.56) 75%),
        linear-gradient(-45deg, transparent 75%, rgba(255,255,255,.56) 75%);
      background-position: 0 0, 0 10px, 10px -10px, -10px 0;
      background-size: 20px 20px;
    }

    .preview video {
      width: min(100%, 520px);
      max-height: 420px;
      display: block;
    }

    .result-body,
    .empty {
      padding: 18px;
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

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    @media (max-width: 820px) {
      .shell { width: min(100% - 24px, 640px); padding: 18px 0; }
      header { align-items: flex-start; }
      main { grid-template-columns: 1fr; }
      .advanced-grid { grid-template-columns: 1fr; }
      .segments { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <img src="{{ url_for('asset_file', filename='icon.ico') }}" alt="">
        <h1>SolidworksToWeb</h1>
      </div>
      <div class="version">v{{ version }}</div>
    </header>

    <main>
      <form class="tool" action="{{ url_for('index') }}" method="post" enctype="multipart/form-data">
        {% if error %}
          <div class="error">{{ error }}</div>
        {% endif %}

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

      {% if result %}
        <section class="result" aria-live="polite">
          <div class="preview">
            <video autoplay loop muted playsinline controls>
              <source src="{{ result.webm_url }}" type="video/webm">
            </video>
          </div>
          <div class="result-body">
            <h2>{{ result.title }}</h2>
            <p>Generated WebM and APNG assets are ready.</p>
            <div class="actions">
              <a class="button" href="{{ result.webm_url }}" download>Download WebM</a>
              <a class="button secondary" href="{{ result.apng_url }}" download>Download APNG</a>
            </div>
          </div>
        </section>
      {% else %}
        <section class="empty">
          <h2>Ready</h2>
          <p>Select an MP4 exported from SolidWorks and choose where the background color should be sampled.</p>
        </section>
      {% endif %}
    </main>
  </div>
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


def render_page(error=None, result=None):
    return render_template_string(
        PAGE,
        version=version,
        error=error,
        result=result,
        corners=[
            ("avg", "Avg"),
            ("tl", "TL"),
            ("tr", "TR"),
            ("bl", "BL"),
            ("br", "BR"),
        ],
        selected_corner=request.form.get("corner", "avg"),
        threshold=clamp_int(request.form.get("threshold"), 135, 1, 255),
        softness=clamp_int(request.form.get("softness"), 12, 1, 50),
        pad=clamp_int(request.form.get("pad"), 10, 0, 240),
        sample_every=clamp_int(request.form.get("sample_every"), 10, 1, 120),
    )


@app.get("/")
def index_get():
    return render_page()


@app.post("/")
def index():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return render_page(error="Choose an MP4 file first."), 400

    source_name = secure_filename(uploaded.filename)
    if Path(source_name).suffix.lower() != ".mp4":
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

    try:
        mp4_to_transparent_webm_and_apng(
            str(input_path),
            str(webm_path),
            str(apng_path),
            fps=get_video_fps(input_path),
            thr=threshold,
            s=softness,
            sample_every_frames=sample_every,
            pad=pad,
            corner=corner,
        )
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        return render_page(error=f"Conversion failed: {exc}"), 500
    finally:
        input_path.unlink(missing_ok=True)
        shutil.rmtree(job_dir / "apng_frames", ignore_errors=True)

    result = {
        "title": title,
        "webm_url": url_for("download_file", job_id=job_id, filename=webm_path.name),
        "apng_url": url_for("download_file", job_id=job_id, filename=apng_path.name),
    }
    return render_page(result=result)


@app.get("/output/<job_id>/<path:filename>")
def download_file(job_id, filename):
    return send_from_directory(OUTPUT_ROOT / "jobs" / job_id, filename, as_attachment=False)


@app.get("/assets/<path:filename>")
def asset_file(filename):
    return send_from_directory(BASE_DIR / "assets", filename)


@app.errorhandler(RequestEntityTooLarge)
def file_too_large(_error):
    return render_page(error=f"Uploads are limited to {MAX_UPLOAD_MB} MB."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
