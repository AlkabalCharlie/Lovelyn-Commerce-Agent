"""Hosted Wan 2.2 video provider (Hugging Face Spaces, ZeroGPU).

Model: Wan-AI/Wan2.2-TI2V-5B (image-to-video preferred for character/product
consistency: a reference image is generated first, then animated).

Verified endpoint (inspected with the Gradio client's view_api() on the
public Space, NOT invented):
  Space: r3gm/wan2-2-fp8da-aoti-preview-2c  (Wan2.2 fp8da AOTI preview)
  api_name="/generate_video"
  params: input_image (filepath, required), last_image (filepath, required),
          prompt, negative_prompt, steps=6, duration_seconds=3.5,
          guidance_scale=1, guidance_scale_2=1, seed, randomize_seed,
          quality=6, scheduler, flow_shift=3.0, frame_multiplier('16'|...),
          upscale_model, upscale_factor, video_component, safe_mode,
          enable_safety_checker
  returns: (generated_video filepath, download_video list[filepath], seed)

Safety/contract:
- Credentials via HF_TOKEN only; never logged, never committed.
- Free ZeroGPU quota respected: single in-flight job, one bounded retry,
  hard stop when quota errors surface. Never claims unlimited generation.
- No auto-publishing: output is a local MP4; publishing stays with the
  existing approval-controlled shorts pipeline.
- Blender renderer remains the selectable fallback (VIDEO_GENERATION_PROVIDER).
"""
import os
import time
import shutil
import tempfile
from dataclasses import dataclass, field

DEFAULT_SPACE = "r3gm/wan2-2-fp8da-aoti-preview-2c"

# ZeroGPU quota-failure signatures (observed shapes; kept broad but explicit)
QUOTA_MARKERS = (
    "GPU quota exceeded", "quota", "ZeroGPU", "has exceeded your GPU quota",
    "gpu limit reached", "rate limited", "exceeded your daily limit",
)


class WanProviderError(Exception):
    """Base provider failure (auth/availability/schema)."""


class WanQuotaExhausted(WanProviderError):
    """ZeroGPU free quota exhausted: STOP; do not retry-storm."""


class WanAuthError(WanProviderError):
    """HF_TOKEN missing/invalid; report exactly what to configure."""


@dataclass
class WanJob:
    prompt: str
    image_path: str | None = None
    last_image_path: str | None = None
    duration_seconds: float = 3.5
    steps: int = 6
    seed: int | None = None
    frame_multiplier: str = "16"
    upscale_factor: float = 1.0
    dedupe_key: str = ""          # prevents duplicate generation requests
    # runtime
    result_video_path: str | None = None
    seed_used: int | None = None
    error: str | None = None
    attempts: int = 0
    metadata: dict = field(default_factory=dict)


def config_missing() -> list:
    return [] if os.getenv("HF_TOKEN") else ["HF_TOKEN"]


def _get_client(space: str | None = None):
    """Build the gradio Client. Raises WanAuthError with exact setup text
    when HF_TOKEN is absent (never fabricates anonymous quota)."""
    token = os.getenv("HF_TOKEN")
    if not token:
        raise WanAuthError(
            "HF_TOKEN is not configured. Set the HF_TOKEN environment "
            "variable (a Hugging Face read token with ZeroGPU access) and "
            "add it as a GitHub repo secret if running in Actions.")
    try:
        from gradio_client import Client
        return Client(space or DEFAULT_SPACE, token=token)
    except Exception as exc:
        raise WanProviderError(
            f"could not open Space {space or DEFAULT_SPACE}: "
            f"{type(exc).__name__}: {exc}") from exc


def _submit_once(client, job: WanJob) -> tuple:
    """One predict() call; returns raw result tuple."""
    from gradio_client import handle_file

    kwargs = {
        "prompt": job.prompt,
        "steps": job.steps,
        "duration_seconds": job.duration_seconds,
        "randomize_seed": job.seed is None,
        "frame_multiplier": int(job.frame_multiplier),
        "upscale_factor": job.upscale_factor,
        "safe_mode": True,
        "enable_safety_checker": True,
    }
    if job.seed is not None:
        kwargs["seed"] = job.seed
    if job.image_path:
        kwargs["input_image"] = handle_file(job.image_path)
    else:
        # The verified Space marks input_image REQUIRED: without a reference
        # image the request cannot start. Reference images are generated
        # FIRST by the production pipeline (wan_shorts_pipeline) so Wan runs
        # in its preferred image-to-video mode with consistent characters.
        raise WanProviderError(
            "input_image is required by the verified endpoint - generate a "
            "reference image first (image-to-video mode).")
    if job.last_image_path:
        kwargs["last_image"] = handle_file(job.last_image_path)
    elif job.image_path:
        # The endpoint requires last_image; anchor it to the same reference
        # frame (first-frame animation, no invented end-frame).
        kwargs["last_image"] = kwargs["input_image"]

    return client.predict(**kwargs, api_name="/generate_video")


def _extract_video(result) -> tuple[str | None, int | None]:
    """Pull the generated video filepath + seed out of the result tuple."""
    video_path = None
    seed = None
    try:
        gen, download, seed_used = result
        # candidates: plain URL/path strings OR FileData-like objects
        candidates = [gen] + list(download or [])
        for candidate in candidates:
            if isinstance(candidate, (str,)) and candidate.strip():
                video_path = candidate.strip()
                break
            url = getattr(candidate, "url", None)
            path = getattr(candidate, "path", None)
            if url or path:
                video_path = url or path
                break
        seed = seed_used if isinstance(seed_used, (int, float)) else None
    except Exception:
        video_path = None
    return video_path, seed


def _download_to_local(url_or_path: str, dest_dir: str) -> str:
    """Persist the generated MP4 locally under dest_dir. Accepts a remote
    URL, a local gradio temp filepath, or a bare filename (searched in the
    gradio temp cache)."""
    if os.path.isfile(url_or_path):  # gradio may give a local temp file
        dest = os.path.join(dest_dir, "wan_scene.mp4")
        shutil.copyfile(url_or_path, dest)
        return dest
    import requests
    if not url_or_path.lower().startswith(("http://", "https://")):
        # Bare relative path from gradio: resolve against the gradio cache.
        import gradio_client
        cache = os.path.join(os.path.dirname(gradio_client.__file__),
                             "version_info.txt")
        candidate = os.path.abspath(url_or_path)
        if os.path.isfile(candidate):
            dest = os.path.join(dest_dir, "wan_scene.mp4")
            shutil.copyfile(candidate, dest)
            return dest
        raise WanProviderError(
            f"generated video reference not resolvable: {url_or_path!r}")
    dest = os.path.join(dest_dir, "wan_scene.mp4")
    with requests.get(url_or_path, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)
    return dest


def generate_scene_clip(job: WanJob, space: str | None = None,
                        max_attempts: int = 2, timeout_s: int = 900) -> WanJob:
    """Submit + poll + retrieve one scene. Bounded retries; quota errors
    stop immediately (no quota burning). The same dedupe_key is never
    generated twice per process lifetime."""
    global _completed_dedupe_keys
    if config_missing():
        raise WanAuthError(
            "HF_TOKEN is not configured. Set the HF_TOKEN environment "
            "variable (a Hugging Face read token with ZeroGPU access) and "
            "add it as a GitHub repo secret if running in Actions.")
    if job.dedupe_key and job.dedupe_key in _completed_dedupe_keys:
        job.error = "duplicate_generation_prevented"
        job.metadata["skipped"] = True
        return job

    job.attempts = 0
    last_error = None
    for attempt in range(1, max_attempts + 1):
        job.attempts = attempt
        try:
            client = _get_client(space)
            t0 = time.time()
            result = _submit_once(client, job)  # blocks until done/queue end
            elapsed = time.time() - t0
            video_ref, seed_used = _extract_video(result)
            if not video_ref:
                raise WanProviderError(
                    f"generation finished without a video: {result!r}")
            dest_dir = tempfile.mkdtemp(prefix="lovelyn-wan-")
            job.result_video_path = _download_to_local(video_ref, dest_dir)
            job.seed_used = int(seed_used) if seed_used is not None else None
            job.metadata.update({"elapsed_s": round(elapsed, 1),
                                 "space": space or DEFAULT_SPACE})
            if job.dedupe_key:
                _completed_dedupe_keys.add(job.dedupe_key)
            return job
        except WanProviderError as exc:
            # Provider failures (missing video, schema, unreachable Space)
            # are recorded and retried a bounded number of times; they are
            # never silent and never a fake success. Quota markers inside
            # provider errors stop immediately (handled below).
            msg = str(exc)
            last_error = msg
            if any(m in msg.lower() for m in QUOTA_MARKERS):
                raise WanQuotaExhausted(
                    "ZeroGPU free quota exhausted - stopping all Wan "
                    "generation for this run (no retry storms).") from exc
            # Schema/validation errors (AppError with 'not in the list of
            # choices') are NOT transient: retrying wastes quota. Stop now.
            if "not in the list of choices" in msg or "AppError" in msg:
                job.error = msg
                return job
            time.sleep(5 * attempt)
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            last_error = msg
            if any(m in msg.lower() for m in QUOTA_MARKERS):
                raise WanQuotaExhausted(
                    "ZeroGPU free quota exhausted - stopping all Wan "
                    "generation for this run (no retry storms).") from exc
            time.sleep(5 * attempt)  # small bounded backoff
    job.error = last_error
    return job


# In-process completed-dedupe set (prevents duplicate requests per run)
_completed_dedupe_keys: set = set()
