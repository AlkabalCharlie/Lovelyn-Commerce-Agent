"""Wire product-specific story scenes + expressive neural narration into the
EXisting renderer (no parallel system). Adds render_product_short() which
reuses render_short's FFmpeg assembly via scene dicts with beats."""
import asyncio
import os

from services.product_video import ProductBrief
from services.shorts_renderer import (_font, _narration_wav, _wrap,
                                      ffmpeg_missing, FONT_SIZE_CAPTION,
                                      FONT_SIZE_TITLE, _TEXT, _DIM, SAFE_TOP,
                                      SAFE_BOTTOM, W, H, FPS)
from services.shorts_story import draw_story_scene
from PIL import Image, ImageDraw


def _expressive_narration(text: str, out_path: str) -> float:
    """Sentence-level expressive synthesis: per-sentence rate variation for
    emphasis (probe-verified working), then concat via ffmpeg."""
    import subprocess
    import tempfile

    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".")
                 .split(".") if s.strip()]
    if len(sentences) < 2:  # single sentence: plain synth
        return _plain_tts(text, out_path)
    work = tempfile.mkdtemp(prefix="lovelyn-tts-")
    try:
        parts = []
        for i, s in enumerate(sentences):
            # emphasis: alternate pace slightly; questions quicken.
            # retry once on transient NoAudioReceived (edge-tts flakiness).
            rate = "+8%" if s.endswith("?") else ("+4%" if i % 2 == 0 else "-4%")
            seg = os.path.join(work, f"s{i}.mp3")
            try:
                asyncio.run(_edge(s, seg, rate))
            except Exception:
                asyncio.run(_edge(s, seg, "+4%"))
            parts.append(seg)
        listf = os.path.join(work, "list.txt")
        with open(listf, "w") as fh:
            for p in parts:
                fh.write(f"file '{p}'\n")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat",
                        "-safe", "0", "-i", listf, "-c", "copy", out_path],
                       check=True, timeout=120)
        return _mp3_duration(out_path)
    except Exception:
        return _plain_tts(text, out_path)
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)


async def _edge(text, path, rate):
    import edge_tts
    voice = os.getenv("SHORTS_TTS_VOICE", "en-US-AndrewMultilingualNeural")
    c = edge_tts.Communicate(text, voice, rate=rate)
    await c.save(path)


def _plain_tts(text, out_path):
    import asyncio
    asyncio.run(_edge(text, out_path, "+4%"))
    return _mp3_duration(out_path)


def _mp3_duration(path):
    """Duration of an MP3 via ffprobe (edge-tts emits MP3, not WAV)."""
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, timeout=30)
    return float(r.stdout.strip())


def _compose_story_frame(beat, caption, narration_t, frame_idx, product_name,
                         title, category="digital"):
    img = draw_story_scene(beat, caption, narration_t, frame_idx,
                           product_name, category)
    d = ImageDraw.Draw(img)
    cap_font = _font(FONT_SIZE_CAPTION)
    lines = _wrap(d, caption or "", cap_font, W - 200)[-6:]
    cy = H - SAFE_BOTTOM + 40
    for line in lines:
        bbox = d.textbbox((0, 0), line, font=cap_font)
        lw = bbox[2] - bbox[0]
        d.rounded_rectangle([(W - lw) // 2 - 22, cy - 10,
                             (W + lw) // 2 + 22, cy + FONT_SIZE_CAPTION + 6],
                            radius=16, fill=(15, 15, 22))
        d.text(((W - lw) // 2, cy), line, font=cap_font, fill=_TEXT)
        cy += FONT_SIZE_CAPTION + 12
    if title:
        tf = _font(44)
        tl = _wrap(d, title, tf, W - 200)[:2]
        ty = SAFE_TOP - 110
        for line in tl:
            bbox = d.textbbox((0, 0), line, font=tf)
            lw = bbox[2] - bbox[0]
            d.rounded_rectangle([(W - lw) // 2 - 18, ty - 8,
                                 (W + lw) // 2 + 18, ty + 56], radius=12,
                                fill=(15, 15, 22))
            d.text(((W - lw) // 2, ty), line, font=tf, fill=_DIM)
            ty += 60
    return img


def render_product_short(brief: ProductBrief, script: dict,
                         out_path: str) -> str | None:
    """Product-specific render: six-beat story scenes, expressive narration,
    captions synced to ACTUAL audio duration. Returns out_path or None."""
    if ffmpeg_missing():
        raise RuntimeError("ffmpeg not found on PATH")
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    work = tempfile.mkdtemp(prefix="lovelyn-pshort-")
    try:
        seg_files, total = [], 0.0
        prev_last = None
        FADE = FPS // 3
        for i, scene in enumerate(script["scenes"]):
            narration = scene["narration"].strip()
            if not narration:
                continue
            wav = os.path.join(work, f"n{i}.mp3")
            dur = _expressive_narration(narration, wav)
            if dur <= 0.2:
                continue
            fdir = os.path.join(work, f"f{i}")
            os.makedirs(fdir, exist_ok=True)
            n_frames = max(int(dur * FPS), 1)
            for f in range(n_frames):
                nt = (f + 1) / n_frames
                frame = _compose_story_frame(scene["beat"],
                                             scene["on_screen"], nt, f,
                                             brief.product_name,
                                             script["title"] if i == 0 else "",
                                             category=brief.category)
                if prev_last is not None and f < FADE:
                    frame = Image.blend(prev_last, frame, (f + 1) / FADE)
                frame.save(os.path.join(fdir, f"f{f:05d}.png"))
            if prev_last is None:
                black = Image.new("RGB", (W, H), (0, 0, 0))
                for f in range(FADE):
                    p = os.path.join(fdir, f"f{f:05d}.png")
                    Image.blend(black, Image.open(p), (f + 1) / FADE).save(p)
            prev_last = Image.open(os.path.join(fdir, f"f{n_frames - 1:05d}.png"))
            seg = os.path.join(work, f"s{i}.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                 "-i", os.path.join(fdir, "f%05d.png"), "-i", wav,
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
                 "-c:a", "aac", "-b:a", "160k", "-shortest", seg],
                check=True, timeout=300)
            seg_files.append(seg)
            total += dur
        if not seg_files or total < 10 or total > 75:
            return None
        listf = os.path.join(work, "list.txt")
        with open(listf, "w", encoding="utf-8") as fh:
            for seg in seg_files:
                fh.write(f"file '{seg}'\n")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", listf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path],
            check=True, timeout=600)
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
