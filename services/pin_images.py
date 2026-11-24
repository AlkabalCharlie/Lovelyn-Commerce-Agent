"""Pinterest pin image generation using only free, local Pillow drawing.

Reuses the existing Lovelyn visual language (dark card, accent bar, short
headline) to produce 1000x1500 (2:3) vertical pins. No paid image APIs, no
dependence on the Wan video pipeline, and existing images are never
regenerated: if the file exists, it is returned as-is.
"""
import os

from PIL import Image, ImageDraw, ImageFont

PIN_W, PIN_H = 1000, 1500
_BG_TOP = (18, 20, 30)
_BG_BOTTOM = (30, 26, 44)
_ACCENT = (255, 196, 0)
_TEXT = (244, 244, 248)
_DIM = (168, 172, 188)


def _font(size: int):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _vertical_gradient(top, bottom):
    img = Image.new("RGB", (PIN_W, PIN_H), top)
    d = ImageDraw.Draw(img)
    for y in range(PIN_H):
        f = y / (PIN_H - 1)
        d.line([(0, y), (PIN_W, y)],
               fill=tuple(int(top[i] + (bottom[i] - top[i]) * f)
                          for i in range(3)))
    return img


def _wrap(draw, text, font, max_width):
    lines, line = [], ""
    for word in (text or "").split():
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


def generate_pin_image(headline: str, subline: str, out_path: str,
                       badge: str = None) -> str:
    """Create a 1000x1500 pin image. Never overwrites an existing file
    (image reuse is required by the brief)."""
    if os.path.isfile(out_path):
        return out_path
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img = _vertical_gradient(_BG_TOP, _BG_BOTTOM)
    d = ImageDraw.Draw(img)

    # Accent shape: large circle bleeding off the bottom-right corner.
    d.ellipse([PIN_W - 460, PIN_H - 420, PIN_W + 240, PIN_H + 240],
              fill=(52, 44, 78))
    d.ellipse([PIN_W - 360, PIN_H - 320, PIN_W + 140, PIN_H + 140],
              fill=(70, 58, 100))

    # Accent bar (brand mark)
    d.rounded_rectangle([80, 120, 240, 136], radius=8, fill=_ACCENT)
    if badge:
        f = _font(38)
        w = d.textlength(badge, font=f)
        d.rounded_rectangle([80, 170, 80 + w + 44, 170 + 64], radius=32,
                            fill=(255, 196, 0))
        d.text((102, 184), badge, font=f, fill=(20, 20, 28))

    # Headline (large, wrapped, wrapped lines centered-left)
    hfont = _font(94)
    y = 300
    for line in _wrap(d, headline, hfont, PIN_W - 180)[:6]:
        d.text((80, y), line, font=hfont, fill=_TEXT)
        y += 112

    # Subline
    if subline:
        sfont = _font(46)
        y += 40
        for line in _wrap(d, subline, sfont, PIN_W - 200)[:5]:
            d.text((80, y), line, font=sfont, fill=_DIM)
            y += 62

    img.save(out_path, "PNG", optimize=True)
    return out_path
