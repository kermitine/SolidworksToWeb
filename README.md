# SolidworksToWeb

A Python3-based tool that makes sharing your Solidworks animations easier than ever,

## Motivation
This program was made by me as a way to automatically convert Solidworks Motion Study Animations into something shareable and embed-able (don't dictionary check me) on the web, in my case, my wordpress site.

## Features
### Automatic Chroma-Keying
Chroma-Keys out a background, leaving outputs with a clean, transparent background.

### WEBM Export
Exports your MP4 file into a web optimized Web Media file.

### APNG Export
For certain devices/browsers which dont support WEBM, it also supports exporting it into an Animated PNG, for those that don't support WEBM files.


## Dependencies

```pip install tkinter```

```pip install os```

```pip install cv2```

```pip install numpy```

```pip install subprocess```

```pip install shutil```

```pip install moviepy```

## How to Use
After installing all dependencies, run main.py and select your mp4 file with a chroma-keyable background (ensure it has a strong contrast with your assembly itself) and let it run! Your exports will be available in output/, which is generated in the same directory as main.py.

## Examples
You can probably see at least one of these, right?

![kermitine](https://github.com/kermitine/SolidworksToWeb/blob/9c1784e6c2bc257d038ddcc785ce37960a3ba222/examples/i3engine.png)

![kermitine](https://github.com/kermitine/SolidworksToWeb/blob/9c1784e6c2bc257d038ddcc785ce37960a3ba222/examples/i3engine.webm)
## License
This repository/project is licensed under the GNU Affero General Public v3.0-or-later. For more information, please consult the LICENSE file (located in the root of the project), or visit https://www.gnu.org/licenses/agpl-3.0.en.html to read the full license.


![kermitine](https://github.com/kermitine/kermitine/blob/b523c5954ea8820f70eb6ff786f2dbec7ce08955/images/kermitine.png)
