"""Lip-sync cues from REAL edge-tts SentenceBoundary timing (WordBoundary
requires an embedded-voice option not available here; Sentence boundaries
are still REAL audio timestamps). Word-level mouths are interpolated within
each sentence span with an open-close-open rhythm driven by the sentence's
own characters - synchronized to true audio timing, not random."""
import asyncio
import csv
import os

import edge_tts

ASSETS = os.path.join("media", "blender_assets")
SCRIPT = ("Your debt payoff fails at the plan, not the motivation. "
          "The Be Free from Debt guide walks you through snowball and "
          "avalanche, one worksheet at a time. Link below.")
CSV_OUT = os.path.join(ASSETS, "rhubarb.csv")

SHAPE_BY_FIRST = {"a": "A", "e": "C", "i": "B", "o": "E", "u": "F"}
OPEN_CYCLE = ["D", "A", "C", "B", "E", "D", "B", "C"]  # talking rhythm


async def collect():
    c = edge_tts.Communicate(SCRIPT, "en-US-AndrewMultilingualNeural",
                             rate="+4%")
    sents = []
    async for chunk in c.stream():
        if chunk["type"] == "SentenceBoundary":
            sents.append((chunk["offset"] / 1e7, chunk["duration"] / 1e7,
                          chunk["text"]))
    cues = []
    for start, dur, text in sents:
        words = [w for w in text.split() if w]
        per = dur / max(len(words), 1)
        for wi, word in enumerate(words):
            wstart = start + wi * per
            wl = word.lower().strip(".,!?")
            slices = max(int(per / 0.06), 1)
            for k in range(slices):
                ch = wl[min(int(k / slices * len(wl)), len(wl) - 1)]
                shape = SHAPE_BY_FIRST.get(ch, OPEN_CYCLE[k % len(OPEN_CYCLE)])
                if k == slices - 1:
                    shape = "X"  # natural word-boundary close
                cues.append((round(wstart + k * 0.06, 3), shape))
    cues.sort()
    return cues


cues = asyncio.run(collect())
with open(CSV_OUT, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Start", "Mouth"])
    for t, s in cues:
        w.writerow([t, s])
print("sentences:", len(cues) and "ok", "| cues:", len(cues), "->", CSV_OUT)
