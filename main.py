import os
import cv2
import numpy as np
import subprocess
import shutil
import time
import sys
from pathlib import Path
from moviepy import VideoFileClip
from moviepy.video.fx import MaskColor, Crop
from KermLib.KermLib import *

# pyinstaller --onefile --icon assets/icon.ico --add-binary "C:\ffmpeg\bin\ffmpeg.exe;." main.py


version = '1.1.2'


def _emit_log(log_callback, *parts):
    message = " ".join(str(part) for part in parts)
    if log_callback:
        log_callback(message)
    print(message)


def _emit_progress(progress_callback, value, message=None):
    if progress_callback:
        progress_callback(max(0, min(100, int(value))), message)


def delete_folder_recursive(folder_path):
    shutil.rmtree(folder_path)


def get_ffmpeg_path() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "ffmpeg.exe")
        if os.path.exists(bundled):
            return bundled

    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg.exe")
    if os.path.exists(local):
        return local

    return "ffmpeg"



def clip_to_apng_v2(
    clip,
    apng_file,
    fps,
    log_callback=None,
    progress_callback=None,
    progress_start=75,
    progress_end=95,
):
    frames_dir = os.path.join(os.path.dirname(apng_file) or ".", "apng_frames")
    os.makedirs(frames_dir, exist_ok=True)

    # times to sample
    n_frames = int(np.ceil(clip.duration * fps))
    times = [i / fps for i in range(n_frames)]
    progress_span = max(1, progress_end - progress_start)
    last_logged_percent = -1

    for i, t in enumerate(times, start=1):
        rgb = clip.get_frame(t)  # HxWx3 uint8
        if clip.mask is None:
            # no alpha available
            rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, dtype=np.uint8)])
        else:
            m = clip.mask.get_frame(t)  # HxW float 0..1
            a = np.clip(m * 255, 0, 255).astype(np.uint8)
            rgba = np.dstack([rgb, a])

        # OpenCV wants BGRA
        bgra = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)

        out_png = os.path.join(frames_dir, f"frame_{i:06d}.png")
        cv2.imwrite(out_png, bgra)
        percent_done = int((i / max(1, n_frames)) * 100)
        if percent_done >= last_logged_percent + 10 or i == n_frames:
            last_logged_percent = percent_done
            _emit_log(log_callback, f"APNG frames: {i}/{n_frames}")
        _emit_progress(
            progress_callback,
            progress_start + int((i / max(1, n_frames)) * progress_span),
            f"Generating APNG frames ({i}/{n_frames})",
        )

    # Stitch into APNG
    ffmpeg = get_ffmpeg_path()
    _emit_log(log_callback, 'Writing to APNG...')
    _emit_progress(progress_callback, progress_end, "Stitching APNG")
    cmd = [
        ffmpeg, "-y",
        "-framerate", str(int(fps)),
        "-i", os.path.join(frames_dir, "frame_%06d.png"),
        "-plays", "0",
        "-f", "apng",
        apng_file
    ]
    subprocess.run(cmd, check=True)
    _emit_progress(progress_callback, 98, "APNG complete")



def mp4_to_transparent_webm_and_apng(
    mp4_file,
    webm_file,
    apng_file,
    fps=30,
    thr=35,
    s=6,
    sample_every_frames=10,
    pad=10,
    corner='avg',
    log_callback=None,
    progress_callback=None,
):
    _emit_progress(progress_callback, 1, "Preparing output folders")
    os.makedirs(os.path.dirname(webm_file) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(apng_file) or ".", exist_ok=True)

    try:
        _emit_log(log_callback, f"Opening source MP4: {mp4_file}")
        _emit_progress(progress_callback, 5, "Opening source MP4")
        clip = VideoFileClip(mp4_file)
    except FileNotFoundError:
        _emit_log(log_callback, 'File not found/File not selected. Program will close in 3 seconds.')
        time.sleep(3)
        sys.exit()

    _emit_progress(progress_callback, 10, "Reading first frame")
    frame0 = clip.get_frame(0)

    if corner == 'avg':
        corners = np.array([frame0[5, 5], frame0[5, -6], frame0[-6, 5], frame0[-6, -6]], dtype=np.float32)
        key_color = tuple(np.round(corners.mean(axis=0)).astype(int))
    elif corner == 'tl':  # top-left
        key_color = tuple(frame0[5, 5].astype(int))
    elif corner == 'tr':  # top-right
        key_color = tuple(frame0[5, -6].astype(int))
    elif corner == 'bl':  # bottom-left
        key_color = tuple(frame0[-6, 5].astype(int))
    elif corner == 'br':  # bottom-right
        key_color = tuple(frame0[-6, -6].astype(int))

    _emit_log(log_callback, "Keying out detected background color:", key_color)
    _emit_progress(progress_callback, 15, "Applying chroma key")

    clip = clip.with_effects([MaskColor(key_color, thr, s)])

    _emit_log(log_callback, "Detecting transparent crop bounds...")
    x1, y1, x2, y2 = _tight_bbox_from_mask_v2(
        clip,
        sample_every_frames,
        pad,
        log_callback=log_callback,
        progress_callback=progress_callback,
        progress_start=18,
        progress_end=30,
    )
    x1, y1, x2, y2 = _make_bbox_even(x1, y1, x2, y2, clip.w, clip.h)
    _emit_log(log_callback, f"Crop bounds: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
    _emit_progress(progress_callback, 32, "Cropping transparent bounds")
    clip = clip.with_effects([Crop(x1=x1, y1=y1, x2=x2, y2=y2)])

    # WebM for desktop
    _emit_log(log_callback, 'Writing to WebM...')
    _emit_progress(progress_callback, 38, "Encoding WebM")
    clip.write_videofile(
        webm_file,
        fps=fps,
        codec="libvpx-vp9",
        audio=False,
        ffmpeg_params=[
            "-pix_fmt", "yuva420p",
            "-auto-alt-ref", "0",
            "-metadata:s:v:0", "alpha_mode=1",
            "-b:v", "0",
            "-crf", "30",
        ],
        logger=None,
    )
    _emit_progress(progress_callback, 72, "WebM complete")
    _emit_log(log_callback, f"WebM saved: {webm_file}")

    # APNG for iOS and other platforms
    _emit_log(log_callback, 'Generating APNG frames...')
    clip_to_apng_v2(
        clip,
        apng_file,
        fps=min(int(round(fps)), (fps/2)),
        log_callback=log_callback,
        progress_callback=progress_callback,
    )
    _emit_log(log_callback, f"APNG saved: {apng_file}")

    clip.close()
    _emit_progress(progress_callback, 100, "Complete")
    _emit_log(log_callback, "Animation generation complete.")


def _tight_bbox_from_mask_v2(
    clip,
    sample_every_frames=10,
    pad=10,
    log_callback=None,
    progress_callback=None,
    progress_start=18,
    progress_end=30,
):
    if clip.mask is None:
        return 0, 0, clip.w, clip.h

    w, h = clip.w, clip.h
    step_t = max(1, sample_every_frames) / float(clip.fps)
    t_values = np.arange(0, clip.duration, step_t)

    min_x, min_y = w, h
    max_x, max_y = 0, 0
    found_any = False
    progress_span = max(1, progress_end - progress_start)
    total_samples = max(1, len(t_values))

    for sample_index, t in enumerate(t_values, start=1):
        m = clip.mask.get_frame(float(t))
        ys, xs = np.where(m > 0.10)
        if xs.size == 0:
            continue
        found_any = True
        min_x = min(min_x, int(xs.min()))
        max_x = max(max_x, int(xs.max()))
        min_y = min(min_y, int(ys.min()))
        max_y = max(max_y, int(ys.max()))
        if sample_index == 1 or sample_index == total_samples or sample_index % 10 == 0:
            _emit_log(log_callback, f"Crop scan: {sample_index}/{total_samples}")
        _emit_progress(
            progress_callback,
            progress_start + int((sample_index / total_samples) * progress_span),
            f"Scanning crop bounds ({sample_index}/{total_samples})",
        )

    if not found_any:
        _emit_log(log_callback, "No transparent crop area detected; using full frame.")
        return 0, 0, w, h

    return (
        max(0, min_x - pad),
        max(0, min_y - pad),
        min(w, max_x + pad),
        min(h, max_y + pad),
    )

def _make_bbox_even(x1, y1, x2, y2, W, H):
    # clamp first
    x1 = max(0, min(int(x1), W - 2))
    y1 = max(0, min(int(y1), H - 2))
    x2 = max(x1 + 2, min(int(x2), W))
    y2 = max(y1 + 2, min(int(y2), H))

    # make top-left even (alignment for 4:2:0)
    if x1 % 2: x1 -= 1
    if y1 % 2: y1 -= 1
    x1 = max(0, x1)
    y1 = max(0, y1)

    # recompute min x2/y2 after possibly shifting x1/y1
    x2 = max(x1 + 2, min(x2, W))
    y2 = max(y1 + 2, min(y2, H))

    # ensure even width/height by adjusting x2/y2 (prefer expanding, else shrink)
    width = x2 - x1
    height = y2 - y1

    if width % 2:
        if x2 < W:
            x2 += 1
        else:
            x2 -= 1

    if height % 2:
        if y2 < H:
            y2 += 1
        else:
            y2 -= 1

    # final clamp
    x2 = min(W, x2)
    y2 = min(H, y2)

    # if still odd due to clamp, shrink by 1
    if (x2 - x1) % 2: x2 -= 1
    if (y2 - y1) % 2: y2 -= 1

    return x1, y1, x2, y2


def run_cli():
    from tkinter import Tk
    from tkinter.filedialog import askopenfilename

    KermLib.ascii_run()
    print(f'SolidworksToWeb V{version} initialized')

    # get file
    Tk().withdraw()
    print('Please select your original mp4 to chroma key:')
    input_filepath = askopenfilename()

    # extract filename (no extension)
    path = Path(input_filepath)
    filename = path.stem

    print('tl = color of top left pixel')
    print('tr = color of top right pixel')
    print('bl = color of bottom left pixel')
    print('br = color of bottom right pixel')
    print('avg = average color of all 4 corners')
    print('Please select which corner(s) to extract greenscreen color from:')

    while True:
        selected_corner = str(input()).lower().strip()
        if selected_corner not in ['tl', 'tr', 'bl', 'br', 'avg']:
            print(f'"{selected_corner}" not recognized as a corner. Please select which corner(s) to extract greenscreen color from:')
            continue
        break

    cap = cv2.VideoCapture(input_filepath) # grab fps for video
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()

    mp4_to_transparent_webm_and_apng(
        input_filepath,
        f"output/{filename}/{filename}.webm",
        f"output/{filename}/{filename}.png",
        fps=fps,
        thr=135,
        s=12,
        corner=selected_corner
    )

    print('Clearing temp files...')
    delete_folder_recursive(f'output/{filename}/apng_frames')
    print(f'Animation generation complete. Output is available in output/{filename}. Program will automatically close in 10 seconds.')
    time.sleep(10)


if __name__ == "__main__":
    run_cli()
