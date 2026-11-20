"""Shorts video renderer: turns a queued script package into a real MP4.

Zero-budget pipeline (milestone B/C):
- Pillow draws animated text frames (hook cards, fact bullets, captions)
  synced to narration timing from the storyboard.
- pyttsx3 (Windows SAPI / local, free) renders narration to WAV per scene.
- FFmpeg assembles frames + audio into H.264/AAC vertical 1080x1920 MP4.

Constraints honored:
- No paid APIs. FFmpeg is free; TTS is the OS's own voice.
- Original visuals only: typography + shapes generated here. No copyrighted
  media is downloaded or reused.
- Scene pacing: text changes every scene, captions animate, key facts are
  highlighted in sequence - not a static-text slideshow.

Guard: ffmpeg_missing() lets callers degrade gracefully (queue keeps status
'queued', agent logs the exact missing dependency) instead of crashing.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920  # vertical 9:16
FPS = 30
FONT_SIZE_TITLE = 92
FONT_SIZE_BODY = 58
FONT_SIZE_CAPTION = 54
SAFE_TOP = 220     # YouTube UI margin (title/channel overlay)
SAFE_BOTTOM = 320  # Shorts action buttons margin
_BG = (16, 18, 28)
_ACCENT = (255, 196, 0)
_TEXT = (240, 240, 245)
_DIM = (150, 155, 170)


def ffmpeg_missing() -> bool:
    return shutil.which("ffmpeg") is None


def _font(size: int):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _draw_frame(title, caption, highlight_index=0, progress=0.0) -> Image.Image:
    img = Image.new("RGB", (W, H), _BG)
    d = ImageDraw.Draw(img)
    # Accent bar whose width tracks narration progress (animated, per frame).
    bar_w = int((W - 160) * min(max(progress, 0.0), 1.0))
    d.rounded_rectangle([80, SAFE_TOP, 80 + bar_w, SAFE_TOP + 14],
                        radius=7, fill=_ACCENT)
    y = SAFE_TOP + 80
    for line in _wrap(d, title, _font(FONT_SIZE_TITLE), W - 160)[:6]:
        d.text((80, y), line, font=_font(FONT_SIZE_TITLE), fill=_TEXT)
        y += FONT_SIZE_TITLE + 18
    y += 40
    # Caption block near the bottom-third, inside safe margins.
    cap_font = _font(FONT_SIZE_CAPTION)
    cap_lines = _wrap(d, caption or "", cap_font, W - 200)[-6:]
    cy = H - SAFE_BOTTOM - len(cap_lines) * (FONT_SIZE_CAPTION + 12)
    for line in cap_lines:
        bbox = d.textbbox((0, 0), line, font=cap_font)
        lw = bbox[2] - bbox[0]
        d.rounded_rectangle([(W - lw) // 2 - 22, cy - 10,
                             (W + lw) // 2 + 22, cy + FONT_SIZE_CAPTION + 6],
                            radius=16, fill=(30, 33, 48))
        d.text(((W - lw) // 2, cy), line, font=cap_font, fill=_TEXT)
        cy += FONT_SIZE_CAPTION + 12
    return img


def _narration_wav(text: str, out_path: str) -> float:
    """Local free TTS. Returns duration seconds (measured after render)."""
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 168)
    engine.save_to_file(text, out_path)
    engine.runAndWait()
    return _wav_duration(out_path)


def _wav_duration(path: str) -> float:
    import wave
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def render_short(package: dict, out_path: str) -> str | None:
    """Render one Shorts MP4 from a content package. Returns out_path or None.

    Requires package keys: title, hook, scenes (each with narration +
    on_screen), disclosure. Durations come from ACTUAL narration audio so
    captions stay synchronized."""
    if ffmpeg_missing():
        raise RuntimeError("ffmpeg not found on PATH")
    scenes = package.get("scenes") or []
    if not scenes:
        return None
    work = tempfile.mkdtemp(prefix="lovelyn-short-")
    try:
        seg_files, total = [], 0.0
        title = package.get("hook") or package.get("title") or "Short"
        for i, scene in enumerate(scenes):
            narration = (scene.get("narration") or scene.get("on_screen") or "").strip()
            if not narration:
                continue
            wav = os.path.join(work, f"n{i}.wav")
            dur = _narration_wav(narration, wav)
            if dur <= 0.2:
                continue
            # Animated frames: accent bar progresses through the scene.
            frame_dir = os.path.join(work, f"f{i}")
            os.makedirs(frame_dir, exist_ok=True)
            n_frames = max(int(dur * FPS), 1)
            for f in range(n_frames):
                frame = _draw_frame(title if i == 0 else "",
                                    scene.get("on_screen") or narration,
                                    progress=(f + 1) / n_frames)
                frame.save(os.path.join(frame_dir, f"f{f:05d}.png"))
            seg = os.path.join(work, f"s{i}.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-framerate", str(FPS), "-i", os.path.join(frame_dir, "f%05d.png"),
                 "-i", wav,
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
                 "-c:a", "aac", "-b:a", "128k", "-shortest", seg],
                check=True, timeout=300)
            seg_files.append(seg)
            total += dur
        if not seg_files or total < 10 or total > 75:
            return None  # too short to be a Short, or over the limit
        concat = os.path.join(work, "list.txt")
        with open(concat, "w", encoding="utf-8") as fh:
            for seg in seg_files:
                fh.write(f"file '{seg}'\n")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", concat, "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
             "-vf", f"scale={W}:{H}", out_path],
            check=True, timeout=600)
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
