"""Fix char_head hair: smooth rounded cap, no spikes."""
import re

new_fn = '''def char_head():
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
    save(img, "char_head.png")'''

src = open("build_assets.py").read()
src2 = re.sub(r"def char_head\(\):.*?save\(img, .char_head\.png.\)", new_fn,
              src, flags=re.S)
open("build_assets.py", "w").write(src2)
print("ok")
