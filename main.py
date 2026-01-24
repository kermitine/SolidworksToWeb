import os
import cv2
import numpy as np
import subprocess
import shutil
from tkinter import Tk
from tkinter.filedialog import askopenfilename
from moviepy import VideoFileClip
from moviepy.video.fx import MaskColor, Crop

version = '1.0.0'

def empty_folder(folder_path):
    """Deletes all files and subdirectories within a given folder, but not the folder itself."""
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isfile(item_path) or os.path.islink(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
    print(f"Folder '{folder_path}' is now empty.")

def clip_to_apng_v2(clip, apng_file, fps):
    frames_dir = os.path.join(os.path.dirname(apng_file) or ".", "apng_frames")
    os.makedirs(frames_dir, exist_ok=True)

    # times to sample
    n_frames = int(np.ceil(clip.duration * fps))
    times = [i / fps for i in range(n_frames)]

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

    # Stitch into APNG (true alpha, no palette)
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(int(fps)),
        "-i", os.path.join(frames_dir, "frame_%06d.png"),
        "-plays", "0",
        "-f", "apng",
        apng_file
    ]
    subprocess.run(cmd, check=True)



def mp4_to_transparent_webm_and_apng(
    mp4_file,
    webm_file,
    apng_file,
    fps=30,
    thr=35,
    s=6,
    sample_every_frames=10,
    pad=10
):
    os.makedirs(os.path.dirname(webm_file) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(apng_file) or ".", exist_ok=True)

    clip = VideoFileClip(mp4_file)

    frame0 = clip.get_frame(0)
    corners = np.array([frame0[5, 5], frame0[5, -6], frame0[-6, 5], frame0[-6, -6]], dtype=np.float32)
    key_color = tuple(np.round(corners.mean(axis=0)).astype(int))
    print("keying out color:", key_color)

    clip = clip.with_effects([MaskColor(key_color, thr, s)])

    x1, y1, x2, y2 = _tight_bbox_from_mask_v2(clip, sample_every_frames, pad)
    x1, y1, x2, y2 = _make_bbox_even(x1, y1, x2, y2, clip.w, clip.h)
    clip = clip.with_effects([Crop(x1=x1, y1=y1, x2=x2, y2=y2)])

    # WebM for desktop
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
    )

    # APNG for iOS (true alpha)
    print('Generating APNG frames...')
    clip_to_apng_v2(clip, "output/animation.png", fps=min(int(round(fps)), 30))

    clip.close()


def _tight_bbox_from_mask_v2(clip, sample_every_frames=10, pad=10):
    if clip.mask is None:
        return 0, 0, clip.w, clip.h

    w, h = clip.w, clip.h
    step_t = max(1, sample_every_frames) / float(clip.fps)
    t_values = np.arange(0, clip.duration, step_t)

    min_x, min_y = w, h
    max_x, max_y = 0, 0
    found_any = False

    for t in t_values:
        m = clip.mask.get_frame(float(t))
        ys, xs = np.where(m > 0.10)
        if xs.size == 0:
            continue
        found_any = True
        min_x = min(min_x, int(xs.min()))
        max_x = max(max_x, int(xs.max()))
        min_y = min(min_y, int(ys.min()))
        max_y = max(max_y, int(ys.max()))

    if not found_any:
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

    # final sanity: if still odd due to clamp, shrink by 1
    if (x2 - x1) % 2: x2 -= 1
    if (y2 - y1) % 2: y2 -= 1

    return x1, y1, x2, y2


# get file
Tk().withdraw()
print('Please select your original mp4 to chroma key:') 
input_filepath = askopenfilename() 

cap = cv2.VideoCapture(input_filepath)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release

mp4_to_transparent_webm_and_apng(
    input_filepath,
    "output/animation.webm",
    "output/animation.png",
    fps=fps,
    thr=135,
    s=12
)

print('clearing temp apng frames')
empty_folder('output/apng_frames')