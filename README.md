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

```pip install tkinter```

```pip install os```

```pip install cv2```

```pip install numpy```

```pip install subprocess```

```pip install shutil```

```pip install moviepy```

```pip install time```

```pip install pathlib```

FFMPEG also must be installed/added to path for APNG generation to function. FFMPEG comes automatically bundled with the executable.
## How to Use
After installing all dependencies, run main.py and select your mp4 file with a chroma-keyable background (ensure it has a strong contrast with your assembly itself) and let it run! Your exports will be available in output/, which is generated in the same directory as main.py.

Alternatively, you can just use the packaged exe (available in releases on this page) and run it like that. FFMPEG comes automatically bundled along with the executable.
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
