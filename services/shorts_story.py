"""Product-specific visual scenes: characters INTERACT with story objects.

Upgrades over shorts_visuals: facial expressions (mood parameter), objects
characters hold/use, two-character interactions, struggle->progress arcs.
All still original Pillow-drawn art (no copyrighted assets).
"""
import math

from PIL import Image, ImageDraw, ImageFont

# Same canvas constants as shorts_visuals (kept in sync deliberately).
W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 220, 320

SKY, SKY2 = (24, 28, 44), (34, 40, 66)
GROUND, GROUND2 = (28, 44, 40), (20, 34, 30)
GOLD, GREEN, RED, BLUE = (255, 196, 0), (94, 200, 130), (232, 93, 93), (86, 148, 232)
SKIN = (232, 190, 154)
CHAR_A, CHAR_B = (94, 130, 220), (220, 120, 160)
WHITE, DIM = (240, 240, 245), (150, 155, 170)
BILL_WHITE, BILL_RED = (250, 250, 252), (220, 70, 70)


def _font(size):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _face(d, cx, cy, r, mood, t):
    """Expressive face: mood in happy|worried|neutral|excited."""
    dx = r // 3
    eye_h = 9 if mood != "worried" else 5
    d.ellipse([cx - dx - 6, cy - 10, cx - dx + 6, cy - 10 + eye_h], fill=(30, 30, 40))
    d.ellipse([cx + dx - 6, cy - 10, cx + dx + 6, cy - 10 + eye_h], fill=(30, 30, 40))
    if mood == "happy":
        d.arc([cx - 20, cy + 2, cx + 20, cy + 26], 10, 170, fill=(60, 45, 40), width=5)
    elif mood == "excited":
        d.arc([cx - 24, cy - 2, cx + 24, cy + 30], 10, 170, fill=(60, 45, 40), width=6)
        # raised brows
        d.line([cx - dx - 10, cy - 22, cx - dx + 10, cy - 26], fill=(60, 45, 40), width=4)
        d.line([cx + dx - 10, cy - 26, cx + dx + 10, cy - 22], fill=(60, 45, 40), width=4)
    elif mood == "worried":
        d.arc([cx - 16, cy + 16, cx + 16, cy + 34], 190, 350, fill=(60, 45, 40), width=5)
        # slanted brows
        d.line([cx - dx - 10, cy - 20, cx - dx + 8, cy - 14], fill=(60, 45, 40), width=4)
        d.line([cx + dx - 8, cy - 14, cx + dx + 10, cy - 20], fill=(60, 45, 40), width=4)
    else:
        d.line([cx - 14, cy + 18, cx + 14, cy + 18], fill=(60, 45, 40), width=5)


def _person(d, cx, base_y, scale, shirt, t, pose="idle", mood="neutral",
            holding=None):
    s = scale
    bob = int(math.sin(t * 2 * math.pi) * 7 * s)
    head_r = int(34 * s)
    head_cy = base_y - int(150 * s) + bob
    d.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
              fill=SKIN)
    _face(d, cx, head_cy, head_r, mood, t)
    body_top = head_cy + head_r + 6
    body_h, body_w = int(120 * s), int(74 * s)
    d.rounded_rectangle([cx - body_w // 2, body_top, cx + body_w // 2,
                         body_top + body_h], radius=20, fill=shirt)
    arm_len, arm_w = int(78 * s), int(20 * s)
    angles = {"point": (-30, 20), "present": (-70, -70), "celebrate": (-140, -140),
              "carry": (-45, -45), "struggle": (-100, -100), "idle": (-12, 14)}
    a1, a2 = angles.get(pose, (-12, 14))
    if pose == "idle":
        a1 += int(5 * math.sin(t * 2 * math.pi))
    hands = []
    for ang in (a1, a2):
        rad = math.radians(ang)
        ex = cx + int(math.cos(rad) * arm_len)
        ey = body_top + 14 + int(math.sin(rad) * arm_len)
        d.line([cx, body_top + 16, ex, ey], fill=shirt, width=arm_w)
        d.ellipse([ex - arm_w // 2, ey - arm_w // 2, ex + arm_w // 2,
                   ey + arm_w // 2], fill=SKIN)
        hands.append((ex, ey))
    if holding == "bills":
        for k, (hx, hy) in enumerate(hands[:2]):
            d.rounded_rectangle([hx - 40, hy - 28, hx + 40, hy + 28],
                                radius=6, fill=BILL_WHITE, outline=(190, 190, 200))
            d.line([hx - 26, hy - 8, hx + 26, hy - 8], fill=BILL_RED, width=5)
    elif holding == "guide":
        hx, hy = hands[0]
        d.rounded_rectangle([hx - 46, hy - 60, hx + 46, hy + 40], radius=8,
                            fill=(90, 60, 160), outline=(60, 40, 110), width=4)
        f = _font(24)
        d.text((hx - 36, hy - 46), "DEBT", font=f, fill=WHITE)
        d.text((hx - 36, hy - 16), "FREE", font=f, fill=GOLD)
    elif holding == "chart_up":
        hx, hy = hands[0]
        d.line([hx - 40, hy + 30, hx + 40, hy - 30], fill=GREEN, width=8)
        d.polygon([(hx + 40, hy - 30), (hx + 12, hy - 26), (hx + 34, hy - 6)],
                  fill=GREEN)
    return hands, body_top


def _bg(d):
    for y in range(H):
        f = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(SKY[i] + (SKY2[i] - SKY[i]) * f)
                                            for i in range(3)))


def _ground(d, horizon):
    d.rectangle([0, horizon, W, H], fill=GROUND)
    d.ellipse([-100, horizon - 40, W + 100, horizon + 120], fill=GROUND2)


def draw_story_scene(beat: str, caption: str, t: float, frame_idx: int,
                     product_name: str = "Product",
                     category: str = "digital") -> Image.Image:
    """Narrative-scene renderer. beat in hook|problem|discovery|demo|benefit|cta.
    category selects demo visuals: software/digital/physical."""
    img = Image.new("RGB", (W, H), SKY)
    d = ImageDraw.Draw(img)
    _bg(d)
    horizon = H - SAFE_BOTTOM - 220
    cx = W // 2

    if beat == "hook":
        _ground(d, horizon)
        _person(d, int(W * 0.32), horizon, 1.25, CHAR_A, frame_idx / FPSX,
                pose="idle", mood="worried")
        # swirling question over head
        qx, qy = int(W * 0.32), horizon - 400 + int(math.sin(t * 6.28) * 14)
        d.text((qx - 30, qy), "?", font=_font(130), fill=GOLD)

    elif beat == "problem":
        _ground(d, horizon)
        # character STRUGGLING under a stack of bills
        _person(d, cx, horizon + 8, 1.25, CHAR_A, frame_idx / FPSX,
                pose="struggle", mood="worried", holding="bills")
        # falling bill shreds (motion)
        for k in range(5):
            ft = (t * 1.4 + k * 0.2) % 1.0
            fy = horizon - 500 + int(ft * 460)
            fx = cx - 160 + k * 80 + int(math.sin(ft * 9) * 20)
            d.rounded_rectangle([fx - 30, fy - 18, fx + 30, fy + 18], radius=4,
                                fill=BILL_WHITE, outline=(200, 200, 210))
            d.line([fx - 16, fy, fx + 16, fy], fill=BILL_RED, width=4)

    elif beat == "discovery":
        _ground(d, horizon)
        # product 'appears' with a glow: scale-in + rays
        glow = 1 + 0.08 * math.sin(t * 6.28)
        gr = int(150 * glow)
        d.ellipse([cx - gr, horizon - 330 - gr // 2, cx + gr,
                   horizon - 330 + gr // 2], fill=(60, 54, 110))
        f = _font(64)
        tw = d.textlength(product_name[:22], font=f)
        d.text((cx - tw / 2, horizon - 380), product_name[:22], font=f,
               fill=GOLD)
        _person(d, int(W * 0.24), horizon, 1.2, CHAR_A, frame_idx / FPSX,
                pose="present", mood="happy")

    elif beat == "demo":
        _ground(d, horizon)
        # Category-aware product visual: software -> chart panel; digital ->
        # the actual product named on the cover; physical -> product box.
        if category == "software":
            # mini candlestick panel the character presents
            px0, py0, pw, ph = int(W * 0.36), horizon - 420, int(W * 0.5), 300
            d.rounded_rectangle([px0, py0, px0 + pw, py0 + ph], radius=16,
                                fill=(22, 26, 40), outline=(70, 78, 110), width=4)
            n = 7
            step = pw // (n + 1)
            for i in range(n):
                if i / n > t + 0.05:
                    break
                up = (i % 3) != 2
                col = GREEN if up else RED
                bx = px0 + step * (i + 1)
                mid = py0 + ph // 2 + int(math.sin(i * 1.7) * ph * 0.25)
                hgt = 50 + (i * 11) % 70
                d.line([bx, mid - hgt // 2 - 20, bx, mid + hgt // 2 + 20],
                       fill=col, width=4)
                d.rounded_rectangle([bx - 14, mid - hgt // 2, bx + 14,
                                     mid + hgt // 2], radius=5, fill=col)
            _person(d, int(W * 0.2), horizon, 1.2, CHAR_A, frame_idx / FPSX,
                    pose="present", mood="happy")
        else:
            # product cover/box with the ACTUAL product name on it
            box_w, box_h = 300, 380
            bx, by = cx + 40, horizon - 430
            d.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=14,
                                fill=(90, 60, 160), outline=(60, 40, 110),
                                width=5)
            f = _font(34)
            words = product_name.upper().split()
            for wi, word in enumerate(words[:4]):
                d.text((bx + 24, by + 40 + wi * 48), word[:12], font=f,
                       fill=GOLD if wi % 2 else WHITE)
            _person(d, int(W * 0.24), horizon, 1.3, CHAR_A, frame_idx / FPSX,
                    pose="carry", mood="happy")
            # flipping detail page next to the box
            tilt = int(14 * math.sin(t * 6.28))
            d.polygon([(bx - 250, by + 60 + tilt), (bx - 30, by + 40),
                       (bx - 30, by + 190), (bx - 250, by + 210 + tilt)],
                      fill=WHITE, outline=(200, 200, 210))
            for ln in range(4):
                d.line([bx - 226, by + 80 + ln * 30, bx - 60,
                        by + 80 + ln * 30], fill=(120, 126, 146), width=4)

    elif beat == "benefit":
        _ground(d, horizon)
        # progress arc fills as t advances (debt shrinking = hopeful mood)
        d.arc([cx - 220, horizon - 480, cx + 220, horizon - 40], start=-90,
              end=-90 + int(360 * t), fill=GREEN, width=26)
        pct = int(t * 100)
        d.text((cx - 70, horizon - 300), f"{pct}%", font=_font(96), fill=GREEN)
        _person(d, int(W * 0.18), horizon, 1.2, CHAR_A, frame_idx / FPSX,
                pose="celebrate" if t > 0.6 else "point",
                mood="excited" if t > 0.6 else "happy")

    elif beat == "cta":
        _ground(d, horizon)
        pulse = 1 + 0.07 * math.sin(t * 6.28)
        bw = int(580 * pulse)
        bx, by = cx - bw // 2, horizon - 300
        d.rounded_rectangle([bx, by, bx + bw, by + 140], radius=36, fill=GOLD)
        f = _font(52)
        d.text((bx + 56, by + 40), "GET THE GUIDE", font=f, fill=(40, 30, 0))
        ay = by - 100 + int(math.sin(t * 6.28) * 16)
        d.line([cx, ay, cx, ay + 50], fill=GOLD, width=14)
        d.polygon([(cx - 26, ay + 44), (cx + 26, ay + 44), (cx, ay + 80)],
                  fill=GOLD)
        _person(d, int(W * 0.2), horizon, 1.2, CHAR_A, frame_idx / FPSX,
                pose="celebrate", mood="excited")
        _person(d, int(W * 0.8), horizon, 1.2, CHAR_B, frame_idx / FPSX,
                pose="celebrate", mood="excited")
    return img


FPSX = 30  # local frame-rate constant (mirrors shorts_renderer.FPS)
