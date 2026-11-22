"""Draw the layered character + environment art as transparent PNGs.
Original programmatic illustration (no copyrighted assets). Layers:
bg_far, bg_mid, desk, char_body, char_arms, char_head, char_eyes_open,
char_brows_neutral, mouth_{a..x,closed}.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

A = os.path.join("media", "blender_assets")
os.makedirs(A, exist_ok=True)

W, H = 1080, 1920
SKY1, SKY2 = (36, 44, 74), (58, 70, 112)
GLOW = (255, 214, 120)
SKIN = (238, 196, 162)
SKIN_SH = (214, 170, 134)
HAIR = (74, 50, 38)
HAIR_HI = (100, 70, 52)
SHIRT = (86, 128, 210)
SHIRT_SH = (62, 96, 170)
DESK_W = (122, 84, 54)
DESK_TOP = (160, 112, 70)
WHITE = (245, 245, 248)


def _font(sz):
    return ImageFont.truetype("arialbd.ttf", sz)


def save(img, name):
    img.save(os.path.join(A, name))
    print("saved", name)


# ---------- backgrounds (parallax layers) ----------
def bg_far():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, H], fill=SKY1 + (255,))
    # gradient to SKY2
    for y in range(H):
        f = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(SKY1[i] + (SKY2[i] - SKY1[i]) * f) for i in range(3)) + (255,))
    # window with warm light
    d.rounded_rectangle([640, 500, 1010, 980], radius=18, fill=(255, 226, 160, 255))
    d.rounded_rectangle([640, 500, 1010, 980], radius=18, outline=(30, 36, 58), width=14)
    d.line([825, 500, 825, 980], fill=(30, 36, 58), width=12)
    # distant bookshelf silhouettes
    for i, x in enumerate((40, 180, 320)):
        d.rounded_rectangle([x, 620, x + 110, 1050], radius=8,
                            fill=(28, 34, 56, 255))
        for s in range(4):
            d.rectangle([x + 10, 650 + s * 95, x + 100, 660 + s * 95],
                        fill=(50, 62, 100, 255))
    # hanging plant
    d.line([940, 0, 940, 180], fill=(40, 48, 76, 255), width=6)
    d.ellipse([880, 170, 1010, 280], fill=(46, 96, 72, 255))
    d.ellipse([900, 150, 960, 210], fill=(60, 120, 88, 255))
    save(img, "bg_far.png")


def bg_mid():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # wall paneling + framed chart poster (ties to finance theme)
    d.rectangle([0, 900, W, H], fill=(52, 62, 100, 255))
    d.rounded_rectangle([80, 960, 460, 1300], radius=14, fill=(30, 36, 58, 255))
    d.rounded_rectangle([110, 990, 430, 1270], radius=8, fill=(22, 27, 44, 255))
    # mini chart inside poster
    pts = [(130, 1220), (180, 1150), (230, 1180), (280, 1080), (330, 1110),
           (380, 1030), (410, 1050)]
    d.line(pts, fill=(94, 200, 130, 255), width=10)
    for p in pts[::2]:
        d.ellipse([p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8],
                  fill=(94, 200, 130, 255))
    # clock
    d.ellipse([880, 1010, 1000, 1130], fill=(245, 245, 248, 255),
              outline=(30, 36, 58), width=8)
    d.line([940, 1070, 940, 1030], fill=(30, 36, 58), width=6)
    d.line([940, 1070, 975, 1085], fill=(30, 36, 58), width=6)
    save(img, "bg_mid.png")


def desk():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 1350, W, H], fill=DESK_W + (255,))
    d.rectangle([0, 1350, W, 1400], fill=DESK_TOP + (255,))
    d.line([0, 1400, W, 1400], fill=(96, 64, 40, 255), width=6)
    # wood grain
    for y in range(1440, H, 60):
        d.line([0, y, W, y + 8], fill=(108, 72, 44, 120), width=3)
    # coffee mug
    d.rounded_rectangle([80, 1240, 200, 1360], radius=12,
                        fill=(220, 224, 232, 255))
    d.arc([190, 1262, 250, 1340], 270, 90, fill=(220, 224, 232), width=16)
    d.ellipse([96, 1252, 184, 1284], fill=(94, 62, 40, 255))
    # papers
    d.polygon([(300, 1360), (560, 1360), (540, 1250), (330, 1256)],
              fill=(245, 245, 248, 255))
    for i in range(3):
        d.line([340, 1280 + i * 26, 520, 1276 + i * 26],
               fill=(150, 156, 176, 255), width=5)
    # pen
    d.line([600, 1330, 700, 1310], fill=(200, 60, 60, 255), width=10)
    save(img, "desk.png")


# ---------- character layers ----------
def char_body():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # torso: rounded trapezoid, centered lower third
    cx = W // 2
    d.polygon([(cx - 190, 1560), (cx - 150, 1160), (cx + 150, 1160),
               (cx + 190, 1560), (cx + 130, 1600), (cx - 130, 1600)],
              fill=SHIRT + (255,))
    d.polygon([(cx - 150, 1160), (cx - 90, 1160), (cx - 110, 1560),
               (cx - 150, 1560)], fill=SHIRT_SH + (255,))
    # collar
    d.polygon([(cx - 70, 1165), (cx, 1225), (cx + 70, 1165)],
              fill=(70, 108, 190, 255))
    # neck (narrower, starts below the mouth line so it reads as a neck)
    d.rounded_rectangle([cx - 38, 1110, cx + 38, 1190], radius=22,
                        fill=SKIN_SH + (255,))
    save(img, "char_body.png")


def char_arms():
    """Two arms as separate rounded shapes; posed mid-gesture (explaining)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = W // 2
    # left arm resting toward desk
    d.rounded_rectangle([cx - 330, 1230, cx - 160, 1310], radius=40,
                        fill=SHIRT + (255,))
    d.ellipse([cx - 350, 1226, cx - 274, 1314], fill=SKIN + (255,))
    # right arm raised, open palm (explaining)
    d.rounded_rectangle([cx + 170, 1150, cx + 320, 1230], radius=40,
                        fill=SHIRT + (255,))
    d.ellipse([cx + 310, 1120, cx + 396, 1214], fill=SKIN + (255,))
    # fingers hint
    for k in range(3):
        d.line([cx + 330 + k * 18, 1128, cx + 336 + k * 18, 1112],
               fill=SKIN + (255,), width=9)
    save(img, "char_arms.png")


def char_head():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = W // 2, 940, 210
    # ears first (behind face edge)
    d.ellipse([cx - r - 18, cy - 10, cx - r + 30, cy + 76], fill=SKIN + (255,))
    d.ellipse([cx + r - 30, cy - 10, cx + r + 18, cy + 76], fill=SKIN + (255,))
    # face oval
    d.ellipse([cx - int(r*.88), cy - r, cx + int(r*.88), cy + int(r*1.04)],
              fill=SKIN + (255,))
    # blush
    d.ellipse([cx - 148, cy + 46, cx - 72, cy + 98], fill=(240, 172, 150, 110))
    d.ellipse([cx + 72, cy + 46, cx + 148, cy + 98], fill=(240, 172, 150, 110))
    # HAIR: one smooth cap ellipse slightly wider than head, top half only.
    # Lower edge sits at eyebrow line, rounded sides hug the head.
    d.ellipse([cx - int(r*.95), cy - r - 26, cx + int(r*.95), cy - r*0.18],
              fill=HAIR + (255,))
    # face reopen (skin) so hair reads as a cap, not a helmet:
    d.ellipse([cx - int(r*.76), cy - int(r*.52), cx + int(r*.76),
               cy + int(r*1.02)], fill=SKIN + (255,))
    # fringe: smooth arc band across the forehead (part of the same cap)
    d.pieslice([cx - int(r*.95), cy - r - 26, cx + int(r*.95), cy - r*0.18],
               200, 340, fill=HAIR + (255,))
    # sideburns: small rounded rects hugging cheeks (rounded corners = no spikes)
    d.rounded_rectangle([cx - int(r*.88), cy - r*0.45, cx - int(r*.70),
                         cy + r*0.15], radius=26, fill=HAIR + (255,))
    d.rounded_rectangle([cx + int(r*.70), cy - r*0.45, cx + int(r*.88),
                         cy + r*0.15], radius=26, fill=HAIR + (255,))
    # highlight sweep
    d.arc([cx - int(r*.72), cy - r - 12, cx + int(r*.4), cy - r*0.35],
          195, 295, fill=HAIR_HI + (255,), width=13)
    # warm smile line
    d.arc([cx - 62, cy + 70, cx + 62, cy + 152], 20, 160,
          fill=SKIN_SH + (255,), width=7)
    save(img, "char_head.png")


def char_eyes():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, 900
    for side in (-1, 1):
        ex = cx + side * 92
        d.ellipse([ex - 46, cy - 34, ex + 46, cy + 34], fill=(252, 250, 248, 255))
        d.ellipse([ex - 22, cy - 24, ex + 22, cy + 22], fill=(46, 38, 60, 255))
        d.ellipse([ex - 10, cy - 18, ex + 2, cy - 6], fill=(255, 255, 255, 230))
        # lids
        d.arc([ex - 46, cy - 40, ex + 46, cy + 30], 200, 340,
              fill=(150, 118, 96, 255), width=6)
    save(img, "char_eyes_open.png")


def char_brows():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, 812
    for side in (-1, 1):
        bx = cx + side * 96
        d.rounded_rectangle([bx - 62, cy - 12, bx + 62, cy + 14], radius=14,
                            fill=HAIR + (255,))
    save(img, "char_brows_neutral.png")


# ---------- mouth shapes (Rhubarb A-X) ----------
def mouth(shape, open_h, width, curve_down=False):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, 1092
    w2, h2 = width // 2, open_h // 2
    if open_h <= 6:  # closed
        d.line([cx - width // 2, cy, cx + width // 2, cy],
               fill=(120, 62, 52, 255), width=10)
    else:
        d.rounded_rectangle([cx - w2, cy - h2, cx + w2, cy + h2], radius=18,
                            fill=(120, 62, 52, 255))
        d.ellipse([cx - w2 + 14, cy - h2 + 8, cx + w2 - 14, cy + h2 - 8],
                  fill=(64, 30, 28, 255))  # inner mouth
        d.ellipse([cx - w2 // 2 - 14, cy + h2 // 2 - 6, cx + w2 // 2 + 14,
                   cy + h2 // 2 + 16], fill=(240, 160, 160, 200))  # tongue
    save(img, f"mouth_{shape.lower()}.png")


bg_far(); bg_mid(); desk(); char_body(); char_arms(); char_head()
char_eyes(); char_brows()
mouth("closed", 4, 120)
mouth("a", 130, 150)   # wide open
mouth("b", 80, 140)    # mid
mouth("c", 56, 120)    # narrow
mouth("d", 34, 130)    # slight
mouth("e", 90, 110)    # round-ish
mouth("f", 44, 90)     # small round
mouth("x", 4, 90)      # rest/closed
print("ALL ASSETS DONE")

# ---------- v2: painterly shading pass ----------
def shade_layer(name, light_from="top_left", tint=(255, 236, 210, 70),
                shadow=(20, 26, 48, 90)):
    """Add gradient lighting ONLY where the layer's alpha exists (never
    touches transparent background)."""
    p = os.path.join(A, name)
    img = Image.open(p).convert("RGBA")
    w, h = img.size
    alpha = img.getchannel("A")
    # light gradient
    grad = Image.new("L", (w, h), 0)
    dg = ImageDraw.Draw(grad)
    for i in range(w + h):
        dg.line([(0, i), (i, 0)], fill=int(255 * max(0, 1 - i / (w * 0.9))))
    lit = Image.new("RGBA", (w, h), tint)
    img = Image.composite(Image.alpha_composite(img, lit), img,
                          Image.composite(grad, Image.new("L", (w, h), 0), alpha))
    # shadow bottom band, masked to alpha
    sh = Image.new("RGBA", (w, h), shadow)
    mask = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(mask)
    for i in range(w):
        dm.line([(i, h), (i, int(h * 0.55 + i * 0.1))],
                fill=int(120 * max(0, 1 - i / (w * 0.7))))
    img = Image.composite(Image.alpha_composite(img, sh), img,
                          Image.composite(mask, Image.new("L", (w, h), 0), alpha))
    img.putalpha(alpha)  # restore original transparency
    img.save(p)
    print("shaded", name)


for layer in ("char_head.png", "char_body.png", "char_arms.png"):
    shade_layer(layer)

print("SHADING PASS DONE")
