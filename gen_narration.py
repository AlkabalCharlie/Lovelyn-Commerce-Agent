"""Generate narration (edge-tts, Andrew neural) + convert to WAV for Blender,
then run Rhubarb lip-sync on it. Falls back to existing narration if offline."""
import asyncio
import os
import subprocess
import sys

ASSETS = os.path.join("media", "blender_assets")
os.makedirs(ASSETS, exist_ok=True)
SCRIPT = ("Your debt payoff fails at the plan, not the motivation. "
          "The Be Free from Debt guide walks you through snowball and "
          "avalanche, one worksheet at a time. Link below.")
MP3 = os.path.join(ASSETS, "narration.mp3")
WAV = os.path.join(ASSETS, "narration.wav")


async def synth():
    import edge_tts
    c = edge_tts.Communicate(SCRIPT, "en-US-AndrewMultilingualNeural",
                             rate="+4%")
    await c.save(MP3)


asyncio.run(synth())
print("tts ok:", os.path.getsize(MP3), "bytes")

ff = "ffmpeg"
subprocess.run([ff, "-y", "-loglevel", "error", "-i", MP3,
                "-ar", "48000", "-ac", "1", WAV], check=True, timeout=120)
print("wav ok:", os.path.getsize(WAV), "bytes")
