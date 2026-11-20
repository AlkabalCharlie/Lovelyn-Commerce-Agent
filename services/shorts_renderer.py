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

from services.shorts_visuals import Scene, draw_scene, scene_for_narration

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
    """Legacy text frame - still used for caption overlay compositing."""
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
    """Neural TTS (edge-tts, free Microsoft neural voices). Falls back to
    Windows SAPI ONLY if edge-tts is unreachable - and logs loudly so the
    robotic voice is never a silent downgrade."""
    import asyncio

    async def _synth():
        import edge_tts
        voice = os.getenv("SHORTS_TTS_VOICE", "en-US-AndrewMultilingualNeural")
        c = edge_tts.Communicate(text, voice, rate="+4%")
        await c.save(out_path)

    try:
        asyncio.run(_synth())
        return _wav_duration(out_path)
    except Exception as exc:
        print(f"WARNING: edge-tts failed ({type(exc).__name__}) - falling "
              f"back to SAPI. This is a DOWNGRADE, not a silent fallback.")
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


def _compose_frame(scene: Scene, caption: str, global_idx: int,
                   fps: int, title: str) -> Image.Image:
    """Visual scene + caption overlay (subtitles preserved, composited ON TOP
    of the illustrated scene)."""
    img = draw_scene(scene, global_idx, fps)
    d = ImageDraw.Draw(img)
    # Caption block (identical placement/style to the working subtitle system)
    cap_font = _font(FONT_SIZE_CAPTION)
    cap_lines = _wrap(d, caption or "", cap_font, W - 200)[-6:]
    cy = H - SAFE_BOTTOM + 60  # below illustration ground, inside safe area
    for line in cap_lines:
        bbox = d.textbbox((0, 0), line, font=cap_font)
        lw = bbox[2] - bbox[0]
        d.rounded_rectangle([(W - lw) // 2 - 22, cy - 10,
                             (W + lw) // 2 + 22, cy + FONT_SIZE_CAPTION + 6],
                            radius=16, fill=(15, 15, 22))
        d.text(((W - lw) // 2, cy), line, font=cap_font, fill=_TEXT)
        cy += FONT_SIZE_CAPTION + 12
    # Scene label (top, small) for context continuity
    if title:
        tfont = _font(44)
        tl = _wrap(d, title, tfont, W - 200)[:2]
        ty = SAFE_TOP - 120
        for line in tl:
            bbox = d.textbbox((0, 0), line, font=tfont)
            lw = bbox[2] - bbox[0]
            d.rounded_rectangle([(W - lw) // 2 - 18, ty - 8,
                                 (W + lw) // 2 + 18, ty + 56],
                                radius=12, fill=(15, 15, 22))
            d.text(((W - lw) // 2, ty), line, font=tfont, fill=_DIM)
            ty += 60
    return img


def _crossfade(a: Image.Image, b: Image.Image, f: float) -> Image.Image:
    return Image.blend(a, b, f)


def render_short(package: dict, out_path: str) -> str | None:
    """Render one Shorts MP4. VISUAL UPGRADE: each scene gets a meaning-matched
    illustration (characters, motion, transitions from shorts_visuals) with
    the working caption/subtitle system composited on top. Durations come
    from ACTUAL narration audio so captions stay synchronized."""
    if ffmpeg_missing():
        raise RuntimeError("ffmpeg not found on PATH")
    scenes = package.get("scenes") or []
    if not scenes:
        return None
    work = tempfile.mkdtemp(prefix="lovelyn-short-")
    try:
        seg_files, total = [], 0.0
        title = package.get("hook") or package.get("title") or "Short"
        FADE_FRAMES = FPS // 3  # ~0.33s cross-fade between scenes
        prev_last = None
        for i, scene in enumerate(scenes):
            narration = (scene.get("narration") or scene.get("on_screen") or "").strip()
            if not narration:
                continue
            wav = os.path.join(work, f"n{i}.wav")
            dur = _narration_wav(narration, wav)
            if dur <= 0.2:
                continue
            vs = scene_for_narration(narration,
                                     scene.get("on_screen") or narration)
            frame_dir = os.path.join(work, f"f{i}")
            os.makedirs(frame_dir, exist_ok=True)
            n_frames = max(int(dur * FPS), 1)
            for f in range(n_frames):
                vs.t = (f + 1) / n_frames
                frame = _compose_frame(vs, vs.caption, global_idx=f,
                                       fps=FPS, title=title if i == 0 else "")
                # Cross-fade from the previous scene's last frame
                if prev_last is not None and f < FADE_FRAMES:
                    frame = _crossfade(prev_last, frame, (f + 1) / FADE_FRAMES)
                frame.save(os.path.join(frame_dir, f"f{f:05d}.png"))
            if prev_last is None:
                # Fade-in from black for the opening scene
                black = Image.new("RGB", (W, H), (0, 0, 0))
                for f in range(FADE_FRAMES):
                    p = os.path.join(frame_dir, f"f{f:05d}.png")
                    Image.blend(black, Image.open(p), (f + 1) / FADE_FRAMES
                                ).save(p)
            prev_last = Image.open(os.path.join(frame_dir,
                                                f"f{n_frames - 1:05d}.png"))
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
