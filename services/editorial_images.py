"""Editorial featured images for Blogger articles.

Two paths, tried in order:
1. `photoreal_editorial_image` - FLUX.1-schnell on Hugging Face ZeroGPU
   (free tier). Produces a genuine photographic editorial image.
2. `illustrated_featured_image` - local Pillow composition. A designed
   EDITORIAL ILLUSTRATION (flat, typographic, non-photographic). It is
   NEVER described as a photograph; alt text and captions say illustration.

Both write to docs/assets/ so the existing GitHub Pages hosting serves them
at SITE_BASE_URL/assets/<file>. Existing files are never overwritten.
"""
import os
import re

from PIL import Image, ImageDraw, ImageFont

DOCS_ASSETS = os.path.join("docs", "assets")
IMG_W, IMG_H = 1280, 720   # 16:9 featured image
FLUX_SPACE = "black-forest-labs/FLUX.1-schnell"

_BG = (244, 241, 236)
_INK = (28, 32, 40)
_ACCENT = (176, 84, 58)
_MUTED = (120, 118, 112)


def _font(size, bold=False):
    names = (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold
             else ("arial.ttf", "DejaVuSans.ttf"))
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:60] or "featured"


def _wrap(draw, text, font, max_w):
    lines, line = [], ""
    for word in (text or "").split():
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def illustrated_featured_image(headline: str, kicker: str, out_name: str,
                               motif: str = "ledger") -> str:
    """Local editorial illustration (NOT a photograph). Warm paper background,
    restrained typography, and a simple drawn motif. Designed to look like a
    finance publication illustration rather than stock art."""
    os.makedirs(DOCS_ASSETS, exist_ok=True)
    out_path = os.path.join(DOCS_ASSETS, out_name)
    if os.path.isfile(out_path):
        return out_path

    img = Image.new("RGB", (IMG_W, IMG_H), _BG)
    d = ImageDraw.Draw(img)

    # Paper texture: faint horizontal rules, like a ledger page.
    for y in range(0, IMG_H, 36):
        d.line([(0, y), (IMG_W, y)], fill=(234, 230, 222))

    # Left: editorial type block. Right: motif panel.
    panel_x = int(IMG_W * 0.58)
    d.rectangle([panel_x, 0, IMG_W, IMG_H], fill=(236, 231, 221))

    # Kicker
    kfont = _font(26, bold=True)
    d.text((72, 96), kicker.upper(), font=kfont, fill=_ACCENT)
    d.line([(72, 140), (72 + d.textlength(kicker.upper(), font=kfont), 140)],
           fill=_ACCENT, width=3)

    # Headline
    hfont = _font(64, bold=True)
    y = 190
    for line in _wrap(d, headline, hfont, panel_x - 140)[:5]:
        d.text((72, y), line, font=hfont, fill=_INK)
        y += 78

    # Motif: a simple ledger sheet with columns, ticks and a rising line.
    if motif == "ledger":
        x0, y0 = panel_x + 70, 150
        x1, y1 = IMG_W - 80, IMG_H - 130
        d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=(252, 250, 246),
                            outline=(206, 199, 186), width=3)
        # header row
        d.rectangle([x0, y0, x1, y0 + 62], fill=(232, 226, 214))
        f = _font(17, bold=True)
        col_w = (x1 - x0 - 40) // 4
        col_x = [x0 + 22, x0 + 22 + col_w, x0 + 22 + 2 * col_w,
                 x0 + 22 + 3 * col_w]
        for i, label in enumerate(("LENDER", "BALANCE", "RATE", "MIN")):
            d.text((col_x[i], y0 + 23), label, font=f, fill=_MUTED)
        # rows
        rows = (("Card A", "$3,200", "22%", "$80"),
                ("Card B", "$900", "18%", "$30"),
                ("Store", "$450", "26%", "$25"),
                ("Loan", "$6,000", "9%", "$180"))
        rf = _font(20)
        for r, row in enumerate(rows):
            ry = y0 + 84 + r * 66
            for i, cell in enumerate(row):
                d.text((col_x[i], ry), cell, font=rf,
                       fill=_INK if i else _MUTED)
            d.line([(x0 + 20, ry + 48), (x1 - 20, ry + 48)], fill=(238, 234, 226))
        # arrow: smallest balance first
        d.line([(x0 + 26, y0 + 84 + 2 * 66 + 30), (x0 + 150, y0 + 84 + 2 * 66 + 30)],
               fill=_ACCENT, width=5)
    elif motif == "chart":
        x0, y0 = panel_x + 70, 150
        x1, y1 = IMG_W - 80, IMG_H - 130
        d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=(252, 250, 246),
                            outline=(206, 199, 186), width=3)
        # candlestick-ish bars
        import random
        rnd = random.Random(7)
        n = 9
        bw = (x1 - x0 - 80) // n
        for i in range(n):
            bx = x0 + 40 + i * bw
            top = y0 + 120 + rnd.randint(-60, 60)
            bot = top + rnd.randint(50, 110)
            d.line([(bx + bw // 2, top - 26), (bx + bw // 2, bot + 26)],
                   fill=_MUTED, width=2)
            d.rectangle([bx + 8, top, bx + bw - 8, bot], fill=_ACCENT)
        d.line([(x0 + 40, y1 - 60), (x1 - 40, y0 + 90)], fill=_INK, width=4)

    # Footer caption - honest about what the image is.
    cf = _font(20)
    d.text((72, IMG_H - 64), "Pointer Insights  ·  editorial illustration",
           font=cf, fill=_MUTED)

    img.save(out_path, "PNG", optimize=True)
    return out_path


def photoreal_editorial_image(prompt: str, out_name: str) -> str | None:
    """FLUX.1-schnell on free ZeroGPU. Returns None when quota is exhausted
    (callers fall back, they never pretend an illustration is a photo)."""
    os.makedirs(DOCS_ASSETS, exist_ok=True)
    out_path = os.path.join(DOCS_ASSETS, out_name)
    if os.path.isfile(out_path):
        return out_path
    token = os.getenv("HF_TOKEN")
    if not token:
        return None
    try:
        from gradio_client import Client
        client = Client(FLUX_SPACE, token=token, verbose=False)
        img_obj, _seed = client.predict(
            prompt=prompt, seed=0, randomize_seed=True,
            width=1344, height=768, num_inference_steps=4, api_name="/infer")
        src = getattr(img_obj, "path", None) or getattr(img_obj, "url", None)
        if not src:
            return None
        if os.path.isfile(src):
            import shutil
            shutil.copyfile(src, out_path)
        else:
            import requests
            r = requests.get(src, timeout=120)
            r.raise_for_status()
            with open(out_path, "wb") as fh:
                fh.write(r.content)
        return out_path
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        if "quota" in msg.lower() or "GPU" in msg:
            print(f"FLUX unavailable (quota): {msg[:140]}")
        else:
            print(f"FLUX failed: {msg[:140]}")
        return None


DEBT_IMAGE_PROMPT = (
    "Editorial photograph, 16:9. A woman in her early thirties sits at a "
    "kitchen table in a bright, modest home, thoughtfully reviewing a "
    "notebook and a calculator beside a small stack of bills and envelopes. "
    "Natural window light from the left, warm and calm atmosphere. Candid "
    "documentary style, shallow depth of field, realistic skin texture, "
    "natural posture, neutral expression of concentration. No visible "
    "branding, no readable text, no watermark, no logos."
)

TV_IMAGE_PROMPT = (
    "Editorial photograph, 16:9. A man in his late twenties at a home desk "
    "studying financial charts on a laptop, notepad beside the keyboard, "
    "warm evening lamp light, calm concentration on his face. Candid "
    "documentary style, realistic detail, shallow depth of field, natural "
    "hands, screen content abstract and unreadable. No branding, no "
    "watermarks, no logos."
)
