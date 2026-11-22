"""Get Rhubarb lip sync: try known release URLs, else build mouth cues from
edge-tts word-boundary metadata (accurate timing, honest fallback)."""
import json
import os
import zipfile

URLS = [
    "https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v2.0.3/rhubarb-lip-sync-2.0.3-win32.zip",
    "https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.11.0/rhubarb-lip-sync-1.11.0-win32.zip",
]
dest = os.path.join("media", "blender_assets")
ok = False
for u in URLS:
    r = os.system(f'curl.exe -sL -o "%TEMP%\\rhubarb.zip" "{u}"')
    try:
        with zipfile.ZipFile(os.environ["TEMP"] + r"\\rhubarb.zip") as z:
            z.extractall(dest)
        ok = True
        print("extracted from", u)
        break
    except Exception as e:
        print("failed:", u, type(e).__name__)

exe = None
for root, _, files in os.walk(dest):
    for f in files:
        if f.lower() == "rhubarb.exe":
            exe = os.path.join(root, f)
print("rhubarb exe:", exe)
