import pathlib
import re

d = pathlib.Path(r"c:\Users\Owner\Lovelyn\docs")
HELD = ["36f0f37b-2e81-49c7-874b-285317abee7c",
        "b3a66faa-77bf-45ba-9630-8cb9a66cf373",
        "f74e3f29-6693-40e4-afc3-e0408aea5689",
        "90edc596-8575-4328-8cae-ac639d97fc62"]
for cid in HELD:
    p = d / f"campaign-{cid}.html"
    print(f"{cid[:8]}: local page exists: {p.exists()}")
idx = (d / "index.html").read_text(encoding="utf-8")
sm = (d / "sitemap.xml").read_text(encoding="utf-8")
print("index links total:", len(re.findall(r"campaign-", idx)),
      "| held in index:", [c[:8] for c in HELD if c in idx])
print("sitemap urls:", len(re.findall(r"<loc>", sm)),
      "| held in sitemap:", [c[:8] for c in HELD if c in sm])
print("pages on disk:", sorted(p.name[9:17] for p in d.glob("campaign-*.html")))
