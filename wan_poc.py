"""One-off controlled proof of concept: ONE Wan-generated shot for the
authorized TradingView campaign. Saves the MP4 locally; does NOT publish,
upload, or touch financial records. Reports elapsed time and result."""
import os
import time
from dotenv import load_dotenv
load_dotenv()

from database.repositories import CampaignRepository
from services.wan_shorts_pipeline import (
    build_storyboard,
    is_campaign_authorized,
    assemble_final,
    _narration_wav,
)
from services.wan_video_provider import (
    WanJob,
    WanProviderError,
    WanQuotaExhausted,
    generate_scene_clip,
)

TV_CID = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
TV_URL = ("https://lovelyn.matchqip.com/"
          "campaign-b8d56c20-c801-4c97-ac8f-936bb5c36cba.html")
OUT = os.path.join("media", "wan_shorts",
                   "tradingview_wan_poc.mp4")

repo = CampaignRepository()
print("authorized:", is_campaign_authorized(repo, TV_CID))
sb = build_storyboard(TV_CID, TV_URL)
print("storyboard shots:", len(sb["shots"]))

clips, wavs, work = [], [], "media/wan_poc_work"
os.makedirs(work, exist_ok=True)
os.makedirs(os.path.dirname(OUT), exist_ok=True)

for i, shot in enumerate(sb["shots"][:3]):
    t0 = time.time()
    from services.wan_shorts_pipeline import _reference_image
    ref = _reference_image(shot["prompt"], os.path.join(work, f"ref{i}.png"))
    job = WanJob(prompt=shot["prompt"], image_path=ref,
                 duration_seconds=3.5, steps=6,
                 frame_multiplier="16", dedupe_key=f"poc-tv-shot{i}")
    try:
        generate_scene_clip(job)
    except WanQuotaExhausted as exc:
        print(f"QUOTA STOPPED after {i} shots: {exc}")
        break
    except WanProviderError as exc:
        print(f"PROVIDER ERROR shot {i}: {exc}")
        break
    if not job.result_video_path:
        print(f"shot {i} failed: {job.error}")
        break
    wav = os.path.join(work, f"n{i}.wav")
    _narration_wav(shot["narration"], wav)
    clips.append(job.result_video_path)
    wavs.append(wav)
    print(f"shot {i}: ok in {time.time() - t0:.0f}s "
          f"(seed {job.seed_used}, {job.metadata.get('elapsed_s')}s) -> "
          f"{job.result_video_path}")

if clips:
    final = assemble_final(clips, wavs, OUT)
    print("FINAL:", final)
else:
    print("NO CLIPS - nothing assembled")
