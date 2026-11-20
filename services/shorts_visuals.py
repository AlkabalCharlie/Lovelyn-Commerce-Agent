"""Visual scene system for Shorts: meaningful illustrated scenes with motion.

Why the first Short looked empty: _draw_frame drew only typography on a flat
dark background. This module adds an SVG-free, Pillow-drawn ILLUSTRATION
LAYER - a library of original vector-style scenes matched to narration
meaning, with per-frame animation (character bobbing, coin drops, snowball
growth, chart line drawing, scene cross-fades).

All art is original, drawn programmatically (no copyrighted assets, no
downloads). Characters are simple stylized figures with expressive poses and
gestures; motion is real per-frame animation, not a static slideshow.
"""
import math

from PIL import Image, ImageDraw

# Same canvas as shorts_renderer (1080x1920) - duplicated here to avoid a
# circular import; a shared constants module would work too if this grows.
W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 220, 320

# Palette (consistent brand look)
SKY = (24, 28, 44)
SKY2 = (32, 38, 62)
GROUND = (28, 44, 40)
GROUND2 = (20, 34, 30)
GOLD = (255, 196, 0)
GREEN = (94, 200, 130)
RED = (232, 93, 93)
GREEN = (94, 200, 130)
BLUE = (86, 148, 232)
SKIN = (232, 190, 154)
CHAR_A = (94, 130, 220)   # character A shirt
CHAR_B = (220, 120, 160)  # character B shirt
WHITE = (240, 240, 245)


class Scene:
    """One illustrated scene: background type, actors, props."""

    def __init__(self, kind: str, caption: str):
        self.kind = kind          # which illustration to draw
        self.caption = caption    # subtitle text (kept from working system)
        self.t = 0.0              # 0..1 progress within scene


def scene_for_narration(narration: str, caption: str) -> Scene:
    """Match visuals to narration MEANING via keyword intent. CTA intent is
    checked FIRST (buy/get/link) so closing lines always get the CTA scene,
    even when they also mention the product."""
    n = narration.lower()
    if any(k in n for k in ("link", "buy", "get the", "download", "cta",
                            "sign up", "subscribe")):
        return Scene("cta", caption)
    if any(k in n for k in ("snowball", "smallest", "momentum")):
        return Scene("snowball", caption)
    if any(k in n for k in ("avalanche", "highest", "interest", "rate")):
        return Scene("avalanche", caption)
    if any(k in n for k in ("free", "tier", "chart", "indicator", "platform",
                            "tradingview")):
        return Scene("chart", caption)
    if any(k in n for k in ("debt", "payoff", "plan", "worksheet", "guide",
                            "budget")):
        return Scene("planner", caption)
    return Scene("hook", caption)


# ---- Character drawing (stylized, expressive, animated) --------------------

def _person(d: ImageDraw.Draw, cx: int, base_y: int, scale: float,
            shirt, t: float, pose: str = "idle", flip: bool = False):
    """A stylized person: head, body, arms with gesture poses, legs.
    bob = gentle vertical breathing motion; pose changes arm angles."""
    s = scale
    bob = int(math.sin(t * 2 * math.pi) * 8 * s)
    head_r = int(34 * s)
    head_cy = base_y - int(150 * s) + bob
    d.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
              fill=SKIN)
    # simple expressive face (eyes + smile), flipped optionally
    eye_dx = -head_r // 3 if flip else head_r // 3
    d.ellipse([cx + eye_dx - 5, head_cy - 8, cx + eye_dx + 5, head_cy + 4],
              fill=(30, 30, 40))
    d.arc([cx - 18 + eye_dx // 2, head_cy + 4, cx + 18 + eye_dx // 2,
           head_cy + 26], start=10, end=170, fill=(60, 45, 40), width=4)
    # body
    body_top = head_cy + head_r + 6
    body_h = int(120 * s)
    body_w = int(74 * s)
    d.rounded_rectangle([cx - body_w // 2, body_top, cx + body_w // 2,
                         body_top + body_h], radius=20, fill=shirt)
    # arms depend on pose (gesture variety)
    arm_len = int(78 * s)
    arm_w = int(20 * s)
    if pose == "point":
        a1, a2 = -30, 20
    elif pose == "present":
        a1, a2 = -70, -70
    elif pose == "celebrate":
        a1, a2 = -140, -140
    else:  # idle
        a1, a2 = -15 + int(6 * math.sin(t * 2 * math.pi)), 15
    for ang in (a1, a2):
        rad = math.radians(ang)
        ex = cx + (body_w // 2) * (1 if ang >= 0 or not flip else -1) \
            + int(math.cos(rad) * arm_len) * (1 if not flip else -1)
        ey = body_top + 14 + int(math.sin(rad) * arm_len)
        d.line([cx, body_top + 16, ex, ey], fill=shirt, width=arm_w)
        d.ellipse([ex - arm_w // 2, ey - arm_w // 2,
                   ex + arm_w // 2, ey + arm_w // 2], fill=SKIN)
    # legs
    leg_h = int(80 * s)
    for side in (-1, 1):
        lx = cx + side * int(22 * s)
        d.line([lx, body_top + body_h, lx, body_top + body_h + leg_h],
               fill=(50, 54, 70), width=int(22 * s))


def _coin(d, cx, cy, r, fall_t):
    yy = cy + int(fall_t * 260)
    d.ellipse([cx - r, yy - r, cx + r, yy + r], fill=GOLD,
              outline=(200, 150, 0), width=3)
    d.text((cx - r * 0.55, yy - r * 0.7), "$", fill=(120, 85, 0))


# ---- Scene backgrounds & actors ---------------------------------------------

def _bg_gradient(d, top, bottom):
    for y in range(H):
        f = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(top[i] + (bottom[i] - top[i]) * f) for i in range(3)))


def _ground(d, y0):
    d.rectangle([0, y0, W, H], fill=GROUND)
    d.ellipse([-100, y0 - 40, W + 100, y0 + 120], fill=GROUND2)


def draw_scene(scene: Scene, frame_idx: int, fps: int) -> Image.Image:
    """Full 1080x1920 illustrated frame for this scene at its progress."""
    t = scene.t
    img = Image.new("RGB", (W, H), SKY)
    d = ImageDraw.Draw(img)
    _bg_gradient(d, SKY, SKY2)
    horizon = H - SAFE_BOTTOM - 260

    kind = scene.kind
    cx = W // 2

    if kind == "snowball":
        _ground(d, horizon)
        # Character pushing a GROWING snowball (motion: ball grows + rolls)
        ball_r = int(60 + 90 * t)
        bx = int(W * 0.32 + t * W * 0.1)
        by = horizon - 10
        d.ellipse([bx - ball_r, by - ball_r, bx + ball_r, by + ball_r],
                  fill=WHITE, outline=(200, 205, 220), width=6)
        # roll marks
        ang = t * 8 * math.pi
        d.arc([bx - ball_r + 14, by - ball_r + 14, bx + ball_r - 14,
               by + ball_r - 14], start=math.degrees(ang) % 360,
              end=(math.degrees(ang) + 90) % 360, fill=(190, 196, 214), width=8)
        _person(d, int(bx - ball_r - 60 * (1 - t)), horizon, 1.25, CHAR_A,
                frame_idx / fps, pose="point")
        d.text((W // 2 - 330, SAFE_TOP + 60), "SNOWBALL", font=None if False
               else __import__("PIL.ImageFont", fromlist=["truetype"])
               .truetype("arialbd.ttf", 84), fill=GOLD)

    elif kind == "avalanche":
        _ground(d, horizon)
        # Mountain with a snow slide + falling coins (interest cost)
        d.polygon([(int(W * 0.1), horizon), (cx, horizon - 480),
                   (int(W * 0.9), horizon)], fill=(58, 66, 96),
                  outline=(90, 100, 140))
        d.polygon([(cx - 40, horizon - 480), (cx, horizon - 560),
                   (cx + 40, horizon - 480)], fill=WHITE)
        # sliding snow blobs accelerate (motion)
        for k in range(3):
            ft = (t + k * 0.33) % 1.0
            sy = horizon - 420 + int(ft * 400)
            sx = cx - 120 + int(ft * 220) + k * 40
            d.ellipse([sx - 26, sy - 26, sx + 26, sy + 26], fill=WHITE)
        _coin(d, int(W * 0.18), horizon - 500, 26, (t * 1.5) % 1.0)
        _coin(d, int(W * 0.82), horizon - 520, 26, (t * 1.2 + 0.4) % 1.0)
        _person(d, int(W * 0.2), horizon, 1.2, CHAR_B, frame_idx / fps,
                pose="present")

    elif kind == "chart":
        _ground(d, horizon)
        # Candlestick chart drawing itself (motion) + pointing character
        px0, py0, pw, ph = int(W * 0.14), horizon - 430, int(W * 0.72), 380
        d.rounded_rectangle([px0, py0, px0 + pw, py0 + ph], radius=18,
                            fill=(22, 26, 40), outline=(70, 78, 110), width=4)
        n = 9
        step = pw // (n + 1)
        for i in range(n):
            if i / n > t + 0.05:
                break  # chart draws in over scene time
            up = (i % 3) != 2
            col = GREEN if up else RED
            bx = px0 + step * (i + 1)
            mid = py0 + ph // 2 + int(math.sin(i * 1.7) * ph * 0.28)
            hgt = 60 + (i * 13) % 90
            d.line([bx, mid - hgt // 2 - 24, bx, mid + hgt // 2 + 24],
                   fill=col, width=5)
            d.rounded_rectangle([bx - 16, mid - hgt // 2, bx + 16,
                                 mid + hgt // 2], radius=6, fill=col)
        _person(d, int(W * 0.16), horizon, 1.2, CHAR_A, frame_idx / fps,
                pose="point", flip=True)

    elif kind == "planner":
        _ground(d, horizon)
        # Desk with worksheet pages flipping (motion), character writing
        d.rounded_rectangle([int(W * 0.22), horizon - 190, int(W * 0.78),
                             horizon - 60], radius=16, fill=(94, 64, 44))
        page_n = 3
        for i in range(page_n):
            lift = (i == int(t * page_n) % page_n)
            px = int(W * 0.30) + i * 8
            py = horizon - 190 - (26 if lift else 0)
            tilt = 14 if lift else 0
            d.polygon([(px, py), (px + 300, py + tilt),
                       (px + 310, py + 110 + tilt), (px + 10, py + 110)],
                      fill=WHITE, outline=(200, 200, 210))
            for ln in range(4):
                d.line([px + 26, py + 22 + ln * 22, px + 270 - ln * 8,
                        py + 22 + ln * 22], fill=(120, 126, 146), width=4)
        _person(d, int(W * 0.17), horizon, 1.2, CHAR_B, frame_idx / fps,
                pose="point")
        # floating checklist ticks (motion)
        for i, f in enumerate((0.2, 0.5, 0.8)):
            if t > f:
                tyx, tyy = int(W * 0.78), horizon - 320 - i * 70
                d.line([tyx - 26, tyy, tyx - 6, tyy + 22], fill=GREEN, width=10)
                d.line([tyx - 6, tyy + 22, tyx + 30, tyy - 22], fill=GREEN,
                       width=10)

    elif kind == "cta":
        _ground(d, horizon)
        # Big glowing button + celebrating characters (motion pulse)
        pulse = 1 + 0.06 * math.sin(t * 2 * math.pi)
        bw, bh = int(560 * pulse), 130
        bx, by = cx - bw // 2, horizon - 300
        d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=34, fill=GOLD)
        fnt = __import__("PIL.ImageFont", fromlist=["truetype"]).truetype(
            "arialbd.ttf", 56)
        d.text((bx + 60, by + 34), "GET THE PACK", font=fnt, fill=(40, 30, 0))
        # downward arrow bounce (motion)
        ay = by - 90 + int(math.sin(t * 2 * math.pi) * 18)
        d.line([cx, ay, cx, ay + 56], fill=GOLD, width=14)
        d.polygon([(cx - 26, ay + 48), (cx + 26, ay + 48), (cx, ay + 84)],
                  fill=GOLD)
        _person(d, int(W * 0.18), horizon, 1.2, CHAR_A, frame_idx / fps,
                pose="celebrate")
        _person(d, int(W * 0.82), horizon, 1.2, CHAR_B, frame_idx / fps,
                pose="celebrate", flip=True)

    else:  # hook
        _ground(d, horizon)
        # Two characters facing each other, question burst above
        _person(d, int(W * 0.28), horizon, 1.25, CHAR_A, frame_idx / fps,
                pose="present")
        _person(d, int(W * 0.72), horizon, 1.25, CHAR_B, frame_idx / fps,
                pose="point", flip=True)
        # animated question burst
        qx, qy = cx, horizon - 430 + int(math.sin(t * 2 * math.pi) * 16)
        fnt = __import__("PIL.ImageFont", fromlist=["truetype"]).truetype(
            "arialbd.ttf", 150)
        d.text((qx - 36, qy), "?", font=fnt, fill=GOLD)
        for k in range(6):
            ang = math.radians(k * 60 + t * 40)
            r1, r2 = 120, 170
            d.line([qx + int(math.cos(ang) * r1), qy + 60 + int(math.sin(ang) * r1),
                    qx + int(math.cos(ang) * r2), qy + 60 + int(math.sin(ang) * r2)],
                   fill=GOLD, width=10)

    return img
