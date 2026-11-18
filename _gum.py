import re
import requests

r = requests.get("https://chukafor.gumroad.com/l/baqctc",
                 headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
t = r.text
title = re.search(r"<title[^>]*>(.*?)</title>", t, re.S)
print("title:", title.group(1).strip()[:120] if title else "n/a")
print("prices:", re.findall(r"[$€£]\s?\d+(?:[.,]\d{2})?", t)[:8])
for kw in ["games", "bundle", "license", "refund", "html5", "zip", "instant"]:
    print(f"{kw}: {kw in t.lower()}")
og = re.search(r'og:description" content="([^"]+)', t)
print("og:desc:", og.group(1)[:220] if og else "n/a")
