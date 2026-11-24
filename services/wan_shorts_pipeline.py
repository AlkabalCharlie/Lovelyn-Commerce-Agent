"""Campaign-aware Wan video production pipeline.

Contract:
- Reads ACTUAL campaign data from the existing verified-products pipeline
  (services/content_packages.PRODUCT_FACTS) - never invented.
- promotion_approved is the sole authorization source of truth: a video is
  generated ONLY for campaigns whose promotion is authorized in the DB.
- Three distinct cinematic shots, product-specific, human-centred.
- Uses the existing narration (edge-tts neural) + FFmpeg subtitle pipeline;
  Wan clips carry the visuals, existing code carries voice/subs/assembly.
- No auto-publish: output MP4 lands in media/wan_shorts/ for review.
- Provider selection: VIDEO_GENERATION_PROVIDER=wan|blender; Blender stays
  untouched as fallback.
"""
import os
import shutil
import subprocess
import tempfile

from services.content_packages import PRODUCT_FACTS, CTA
from services.wan_video_provider import (
    WanJob,
    WanProviderError,
    WanQuotaExhausted,
    generate_scene_clip,
)

W, H = 1080, 1920
FPS = 30

# ------------------------------------------------------------- prompts ----
# Style block shared by every shot: realistic humans, natural motion.
STYLE = ("realistic cinematic photography, natural skin texture, "
         "soft window light, shallow depth of field, 9:16 vertical "
         "composition, smooth natural motion, steady camera")

NEGATIVE = ("distorted face, deformed hands, extra fingers, text overlay, "
            "watermark, cartoon, anime, oversaturated, jerky motion, "
            "static frame")


FLUX_SPACE = "black-forest-labs/FLUX.1-schnell"
REF_STYLE = ("photorealistic, natural proportions, cinematic lighting, "
             "9:16 vertical framing, no text, no watermark")


def _reference_image(prompt: str, out_path: str) -> str | None:
    """Generate a photorealistic 9:16 reference image with FREE FLUX.1-schnell
    ZeroGPU inference (separate free quota from Wan's), then Wan animates it
    image-to-video with consistent characters. Never claims to be Wan output
    itself - it is the compositional seed frame. Falls back to a flat Pillow
    layout only if FLUX is unreachable (logged loudly; production quality
    depends on FLUX being up)."""
    import os as _os
    token = _os.getenv("HF_TOKEN")
    try:
        from gradio_client import Client
        client = Client(FLUX_SPACE, token=token, verbose=False)
        # 720x1280 (9:16, 4-step schnell = fast + quota-light)
        result = client.predict(
            prompt=f"{prompt} {REF_STYLE}", seed=0, randomize_seed=True,
            width=720, height=1280, num_inference_steps=4,
            api_name="/infer")
        img_obj, _seed = result
        src = getattr(img_obj, "path", None) or getattr(img_obj, "url", None)
        if not src:
            raise RuntimeError(f"FLUX returned no image: {result!r}")
        if os.path.isfile(src):
            import shutil
            shutil.copyfile(src, out_path)
        else:
            import requests
            r = requests.get(src, timeout=120)
            r.raise_for_status()
            with open(out_path, "wb") as fh:
                fh.write(r.content)
        return out_path
    except Exception as exc:
        print(f"WARNING: FLUX reference generation failed "
              f"({type(exc).__name__}: {exc}) - using flat Pillow seed. "
              f"Video quality will be limited.")
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (720, 1280), (24, 26, 34))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([90, 420, 630, 800], radius=28,
                            fill=(38, 42, 56))
        img.save(out_path)
        return out_path


def build_storyboard(campaign_id: str, campaign_url: str) -> dict | None:
    """Three-shot storyboard from VERIFIED facts only. Returns None for
    campaigns without verified facts (never invents)."""
    facts = PRODUCT_FACTS.get(campaign_id)
    if not facts:
        return None
    name = facts["name"]

    if campaign_id == "b8d56c20-c801-4c97-ac8f-936bb5c36cba":  # TradingView
        shots = [
            {"prompt": (
                "A focused young trader at a home desk at dusk, leaning "
                "forward with natural curiosity, a laptop open before them "
                "showing financial candlestick charts glowing softly on "
                "screen. Slow dolly-in over the shoulder. " + STYLE),
             "narration": (
                 "Every trader hits the same wall: the free plan runs out "
                 "of room fast.")},
            {"prompt": (
                 "Close-up of hands typing on the laptop, the screen "
                 "showing two chart panels side by side, the person nods "
                 "slowly, satisfied, comparing plans. Gentle handheld "
                 "camera. " + STYLE),
             "narration": (
                 "TradingView's paid tiers mainly add indicators per "
                 "chart, charts per tab, alert capacity and ad removal.")},
            {"prompt": (
                 "The trader relaxes back in the chair with a small "
                 "confident smile, warm desk lamp glow, charts still "
                 "visible, looks toward camera with quiet confidence. "
                 "Slow push-in. " + STYLE),
             "narration": (
                 "Compare the plans yourself - the link is below. " +
                 facts["disclosure"])},
        ]
    else:
        # Generic-but-factual storyboard from the verified facts list.
        shots = [
            {"prompt": ("A person at a tidy desk opens a laptop showing "
                        "generic product-related imagery, interested "
                        "expression. Slow dolly-in. " + STYLE),
             "narration": f"A practical option: {name}."},
            {"prompt": ("Close-up of the person using the product "
                        "naturally, soft light, satisfied nod. Gentle "
                        "handheld. " + STYLE),
             "narration": ". ".join(facts["facts"][:1])},
            {"prompt": ("The person relaxes, small confident smile toward "
                        "camera, warm lighting. Slow push-in. " + STYLE),
             "narration": (CTA.get(campaign_id, "") + " " +
                           facts["disclosure"])},
        ]
    return {"product_name": name, "shots": shots,
            "campaign_url": campaign_url, "campaign_id": campaign_id}


def is_campaign_authorized(camp_repo, campaign_id: str) -> bool:
    """promotion_approved is the ONLY authorization source."""
    return camp_repo.is_promotion_approved(campaign_id)


def _narration_wav(text: str, out_path: str) -> float:
    """Neural TTS with a bounded edge-tts retry before any SAPI downgrade.
    The SAPI fallback is a DOWNGRADE and is logged loudly (never silent)."""
    import asyncio
    import time as _time

    async def _synth():
        import edge_tts
        voice = os.getenv("SHORTS_TTS_VOICE", "en-US-AndrewMultilingualNeural")
        c = edge_tts.Communicate(text, voice, rate="+4%")
        await c.save(out_path)

    for attempt in range(3):
        try:
            asyncio.run(_synth())
            from services.shorts_renderer import _wav_duration
            return _wav_duration(out_path)
        except Exception as exc:
            print(f"edge-tts attempt {attempt + 1} failed: "
                  f"{type(exc).__name__}; retrying...")
            _time.sleep(4 * (attempt + 1))
    print("WARNING: edge-tts failed 3x - falling back to SAPI. "
          "This is a DOWNGRADE, not a silent fallback.")
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 168)
    engine.save_to_file(text, out_path)
    engine.runAndWait()
    from services.shorts_renderer import _wav_duration
    return _wav_duration(out_path)


def _clip_duration(path: str) -> float:
    import json
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", path],
        capture_output=True, text=True, check=True, timeout=60)
    return float(json.loads(out.stdout)["format"]["duration"])


def assemble_final(clips: list, wav_files: list, out_path: str) -> str:
    """Existing-FFmpeg-style assembly: per-scene clip + narration track,
    concat, 1080x1920 H.264/AAC. Cross-fades avoided here (Wan clips are
    self-animating); simple concat keeps motion natural."""
    work = tempfile.mkdtemp(prefix="lovelyn-wan-assemble-")
    segs = []
    try:
        for i, (clip, wav) in enumerate(zip(clips, wav_files)):
            seg = os.path.join(work, f"seg{i}.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-i", wav,
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
                 "-c:a", "aac", "-b:a", "128k", "-shortest", seg],
                check=True, timeout=300)
            segs.append(seg)
        concat = os.path.join(work, "list.txt")
        with open(concat, "w", encoding="utf-8") as fh:
            for s in segs:
                fh.write(f"file '{s}'\n")
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat",
             "-safe", "0", "-i", concat, "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", "-vf", f"scale={W}:{H}",
             out_path],
            check=True, timeout=600)
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)


def produce_campaign_video(camp_repo, campaign_id: str, campaign_url: str,
                           out_path: str, max_shots: int = 3,
                           dry_run: bool = False) -> dict:
    """One video per campaign per run. Returns a status dict; NEVER
    publishes, NEVER touches financial records, NEVER auto-uploads."""
    status = {"campaign_id": campaign_id, "video": None, "shots": [],
              "error": None, "provider": "wan"}
    if not is_campaign_authorized(camp_repo, campaign_id):
        status["error"] = "campaign_not_authorized"
        return status
    storyboard = build_storyboard(campaign_id, campaign_url)
    if not storyboard:
        status["error"] = "no_verified_facts"
        return status
    if dry_run:
        status["shots"] = [s["narration"] for s in storyboard["shots"]]
        status["dry_run"] = True
        return status

    work = tempfile.mkdtemp(prefix="lovelyn-wan-prod-")
    clips, wavs = [], []
    try:
        for i, shot in enumerate(storyboard["shots"][:max_shots]):
            ref = _reference_image(shot["prompt"],
                                   os.path.join(work, f"ref{i}.png"))
            job = WanJob(prompt=f"{shot['prompt']}".strip(),
                         image_path=ref,
                         duration_seconds=3.5, steps=6,
                         dedupe_key=f"{campaign_id}-shot{i}",
                         frame_multiplier="16")
            try:
                generate_scene_clip(job)
            except WanQuotaExhausted as exc:
                status["error"] = f"quota_exhausted: {exc}"
                return status
            except WanProviderError as exc:
                status["error"] = f"provider_error: {exc}"
                return status
            if not job.result_video_path:
                status["error"] = f"shot_{i}_failed: {job.error}"
                return status
            wav = os.path.join(work, f"n{i}.wav")
            _narration_wav(shot["narration"], wav)
            clips.append(job.result_video_path)
            wavs.append(wav)
            status["shots"].append({"shot": i,
                                    "elapsed_s": job.metadata.get("elapsed_s"),
                                    "seed": job.seed_used})
        status["video"] = assemble_final(clips, wavs, out_path)
        status["campaign_url"] = campaign_url
        return status
    finally:
        # Keep source clips + narration for troubleshooting by moving the
        # work dir next to the output when a video was produced.
        if status["video"]:
            keep = (out_path.rsplit(".", 1)[0] + "_sources")
            shutil.copytree(work, keep, dirs_exist_ok=True)
        shutil.rmtree(work, ignore_errors=True)
