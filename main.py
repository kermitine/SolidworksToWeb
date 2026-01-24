import os
import cv2
import numpy as np
from tkinter import Tk
from tkinter.filedialog import askopenfilename
from moviepy import VideoFileClip
from moviepy.video.fx import MaskColor, Crop


def mp4_to_transparent_cropped_webm(
    mp4_file,
    webm_file,
    fps=30,
    thr=35,                 # start lower; increase if green remains
    s=6,
    sample_every_frames=10,
    pad=10
):
    os.makedirs(os.path.dirname(webm_file) or ".", exist_ok=True)

    clip = VideoFileClip(mp4_file)

    # --- pick key color from corners of first frame ---
    frame0 = clip.get_frame(0)
    corners = np.array([
        frame0[5, 5],
        frame0[5, -6],
        frame0[-6, 5],
        frame0[-6, -6],
    ], dtype=np.float32)
    key_color = tuple(np.round(corners.mean(axis=0)).astype(int))
    print("Auto key_color =", key_color)

    # 1) Key out background (MoviePy v2: positional args)
    clip = clip.with_effects([MaskColor(key_color, thr, s)])

    # Quick debug: see if the mask is doing anything
    m0 = clip.mask.get_frame(0) if clip.mask is not None else None
    if m0 is not None:
        print("Mask min/max =", float(m0.min()), float(m0.max()))

    # 2) Crop to content using the mask
    x1, y1, x2, y2 = _tight_bbox_from_mask_v2(clip, sample_every_frames, pad)
    clip = clip.with_effects([Crop(x1=x1, y1=y1, x2=x2, y2=y2)])

    # 3) Export VP9 WebM with alpha (add alpha_mode metadata for better playback)
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
        ys, xs = np.where(m > 0.02)
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


# get file
Tk().withdraw() # we don't want a full GUI, so keep the root window from appearing
input_filepath = askopenfilename() 

cap = cv2.VideoCapture(input_filepath)
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release

mp4_to_transparent_cropped_webm(
    input_filepath,
    "output/animation.webm",
    fps=fps,
    thr=135,
    s=12
)
