# SolidworksToWeb <img src="https://github.com/kermitine/SolidworksToWeb/blob/91779338dc7ff0fc549041e5aa3be40f8f05665a/assets/icon.ico" width="64">


A Python3-based tool that makes sharing your Solidworks animations easier than ever.

## Motivation
This program was made by me as a way to automatically convert Solidworks Motion Study Animations into something shareable and embed-able (don't dictionary check me) on the web, in my case, my wordpress site.

## Features
### Automatic Chroma-Keying
Automatic chroma-keying, leaving outputs with a clean, transparent background.

### WEBM Export
Exports your MP4 file into a web optimized Web Media file.

### APNG Export
For certain devices/browsers which dont support WEBM, it also supports exporting it into an Animated PNG.


## Dependencies
run ```pip install -r requirements.txt``` in the root of the project.

FFMPEG also must be installed/added to path for APNG generation to function. FFMPEG comes automatically bundled with the executable.
## How to Use
After installing all dependencies, run main.py and select your mp4 file with a chroma-keyable background (ensure it has a strong contrast with your assembly itself) and let it run! Your exports will be available in output/, which is generated in the same directory as main.py.

Alternatively, you can just use the packaged exe (available in releases on this page) and run it like that. FFMPEG comes automatically bundled along with the executable.

## Hosted Converter
You can use the self-hosted web converter here:

https://swtoweb.ex1.prxima.uk/

For embedding the converter inside another page, use the compact iframe view:

https://swtoweb.ex1.prxima.uk/?embed=1

## Web UI with Docker Compose
The repo also includes a simple upload UI that can be built directly from the GitHub source.

```
git clone https://github.com/kermitine/SolidworksToWeb.git
cd SolidworksToWeb
docker compose up -d --build
```

Open `http://localhost:8000`, upload an MP4, choose the background sample corner, and download the generated WebM/APNG outputs. Converted files are persisted under `output/jobs/` on the host through the Compose volume.

The web UI also keeps a persistent `Total files converted` count in `output/stats.json` on the host. It increments after a conversion finishes successfully and survives container restarts, image rebuilds, and container removal as long as the host `output/` directory is kept.

For public deployments, the web UI keeps generated files temporarily and cleans up old job folders at startup and every 30 minutes. The default settings in `docker-compose.yml` keep outputs for 24 hours and allow one active conversion at a time:

```
SWTOWEB_RETENTION_HOURS=24
SWTOWEB_CLEANUP_INTERVAL_MINUTES=30
SWTOWEB_MAX_ACTIVE_JOBS=1
SWTOWEB_MAX_QUEUE_SIZE=10
SWTOWEB_MAX_UPLOAD_MB=512
SWTOWEB_FRAME_ANCESTORS="'self' https://ayriknabirahni.com https://www.ayriknabirahni.com"
```

Uploads with the same filename are safe. Each conversion is stored in its own unique job folder, so files do not overwrite each other.

Conversions are queued. By default, one job is processed at a time and up to 10 jobs can wait in line. Increase `SWTOWEB_MAX_ACTIVE_JOBS` only if the server has enough CPU/RAM for multiple video conversions at once.

Put the app behind HTTPS when exposing it publicly.

The Compose service also drops Linux capabilities, prevents privilege escalation, uses a read-only container filesystem, and keeps `/tmp` writable for video processing scratch files.

To embed the converter on another site, allow that site in `SWTOWEB_FRAME_ANCESTORS` and use the compact iframe URL:

```
<div class="swtoweb-frame-wrap">
  <div class="swtoweb-loader" id="swtoweb-loader">
    <span></span>
    <strong>Loading converter...</strong>
  </div>

  <iframe
    id="swtoweb-converter"
    src="https://swtoweb.ex1.prxima.uk/?embed=1"
    title="SolidworksToWeb animation converter"
    loading="lazy"
  ></iframe>
</div>

<script>
const swtowebIframe = document.getElementById("swtoweb-converter");
const swtowebLoader = document.getElementById("swtoweb-loader");
const swtowebLoaderText = swtowebLoader ? swtowebLoader.querySelector("strong") : null;
const swtowebMaxRetries = 3;
const swtowebRetryDelayMs = 7000;
let swtowebRetryCount = 0;
let swtowebReady = false;
let swtowebRetryTimer = null;

function showSwtowebFrame() {
  swtowebReady = true;
  window.clearTimeout(swtowebRetryTimer);
  if (swtowebLoader) swtowebLoader.hidden = true;
  if (swtowebIframe) swtowebIframe.classList.add("is-loaded");
}

function resetSwtowebFrame() {
  if (!swtowebIframe || swtowebReady) return;

  if (swtowebRetryCount >= swtowebMaxRetries) {
    if (swtowebLoaderText) {
      swtowebLoaderText.textContent = "Converter is taking longer than expected. Refresh this page to try again.";
    }
    return;
  }

  swtowebRetryCount += 1;
  if (swtowebLoaderText) {
    swtowebLoaderText.textContent = `Retrying converter... (${swtowebRetryCount}/${swtowebMaxRetries})`;
  }

  const nextUrl = new URL(swtowebIframe.src);
  nextUrl.searchParams.set("retry", Date.now().toString());
  swtowebIframe.classList.remove("is-loaded");
  swtowebIframe.src = nextUrl.toString();
  startSwtowebWatchdog();
}

function startSwtowebWatchdog() {
  window.clearTimeout(swtowebRetryTimer);
  swtowebRetryTimer = window.setTimeout(resetSwtowebFrame, swtowebRetryDelayMs);
}

window.addEventListener("message", event => {
  if (event.origin !== "https://swtoweb.ex1.prxima.uk") return;
  if (!event.data || event.data.type !== "swtoweb:resize") return;

  showSwtowebFrame();
  if (swtowebIframe) {
    swtowebIframe.style.height = `${Math.max(360, Math.min(event.data.height, 1600))}px`;
  }
});

startSwtowebWatchdog();
</script>

<style>
.swtoweb-frame-wrap {
  position: relative;
  width: 100%;
  min-height: 360px;
}

#swtoweb-converter {
  display: block;
  width: 100%;
  height: 520px;
  border: 0;
  opacity: 0;
  transition: opacity 180ms ease;
}

#swtoweb-converter.is-loaded {
  opacity: 1;
}

.swtoweb-loader {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: grid;
  place-items: center;
  gap: 12px;
  align-content: center;
  min-height: 360px;
  border: 1px solid #303942;
  border-radius: 8px;
  background: #090c10;
  color: #f4f7f8;
  font: 16px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.swtoweb-loader span {
  width: 34px;
  height: 34px;
  border: 3px solid rgba(249, 0, 0, 0.24);
  border-top-color: #f90000;
  border-radius: 50%;
  animation: swtoweb-spin 800ms linear infinite;
}

.swtoweb-loader[hidden] {
  display: none;
}

@keyframes swtoweb-spin {
  to { transform: rotate(360deg); }
}
</style>
```

The wrapper keeps the loader visible until the converter sends a ready/resize message, and retries the iframe up to three times if that message never arrives. If connection reset errors persist, confirm the reverse proxy points at the published Docker port and that the container healthcheck is healthy. For the included Compose file, the host port is `8001` and the container port is `8000`.

To update a deployed checkout:

```
git pull
docker compose up -d --build
```
## Examples
Here are the source files, which are directly uploaded to SWToWeb. No other human inputs required.

https://youtube.com/shorts/soDnxHmB2o8 (I3 Engine)

https://youtu.be/oANaYYsdhUI (Espresso Machine)

Here are SWToWeb-generated animated pngs below, as Github does not seem to support WebM.

![kermitine](https://github.com/kermitine/SolidworksToWeb/blob/9c1784e6c2bc257d038ddcc785ce37960a3ba222/examples/i3engine.png)
![kermitine](https://github.com/kermitine/SolidworksToWeb/blob/85fc7ccae3b526db24a88533571ac1ba9a18c321/examples/espresso_machine_explode.png)

A live example is visible on a blog post on my site here: https://ayriknabirahni.com/writeup/i3-engine/

## Sample HTML/CSS
This is the live, working code which I use on my wordpress site to control which assets are displayed.

HTML:
```
<div class="alpha-anim">
  <video class="alpha-webm" autoplay loop muted playsinline>
    <source src="LINK_TO_WEBM_FILE" type="video/webm">
  </video>

  <img class="alpha-apng" src="LINK_TO_APNG_FILE" alt="">
</div>

<script>
(function () {
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
                (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

  if (isIOS) {
    document.querySelectorAll(".alpha-anim").forEach(wrap => {
      const v = wrap.querySelector(".alpha-webm");
      const i = wrap.querySelector(".alpha-apng");
      if (v) v.style.display = "none";
      if (i) i.style.display = "block";
    });
  }
})();
</script>
```

Custom CSS:
```
.alpha-anim { 
  position: relative;
  margin: 0 auto;
  max-width: 300px;   /* LIMIT SIZE ON DESKTOP */
  width: 100%;
}

.alpha-webm, .alpha-apng {
  width: 100%;       /* force scale inside container */
  height: auto;
  background: transparent !important;
  display: block;
}

.alpha-apng { 
  display: none; 
} /* default: hide APNG unless iOS */
```
## Common Issues
Certain Wordpress compression plugins that automatically handle delivery can affect the plugin. An issue I encountered was with CompressX, which would optimize the png with AVIF and WebP alternatives and automatically deliver the most optimal. Obviously, this affected the animated png on ios, as the AVIF and WebP were not animated. Ensure that your APNG files are excluded from this compression plugins.

## License
This repository/project is licensed under the GNU Affero General Public v3.0-or-later. For more information, please consult the LICENSE file (located in the root of the project), or visit https://www.gnu.org/licenses/agpl-3.0.en.html to read the full license.


![kermitine](https://github.com/kermitine/kermitine/blob/b523c5954ea8820f70eb6ff786f2dbec7ce08955/images/kermitine.png)
