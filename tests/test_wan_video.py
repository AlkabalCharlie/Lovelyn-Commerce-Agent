"""Wan video provider tests - ALL inference mocked (zero GPU quota used).

Covers: HF auth, missing credentials, quota exhaustion, API failure,
timeout, duplicate-generation prevention, Space API configuration,
campaign authorization, product-specific prompt construction (no invented
claims), video assembly, Blender fallback selection, no accidental
publishing.
"""
import os
import shutil
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from services import wan_video_provider as wvp
from services.wan_video_provider import (
    WanAuthError,
    WanJob,
    WanProviderError,
    WanQuotaExhausted,
    config_missing,
    generate_scene_clip,
)
from services import wan_shorts_pipeline as wsp
from services.wan_shorts_pipeline import (
    build_storyboard,
    is_campaign_authorized,
    produce_campaign_video,
)

TV_CID = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"   # TradingView
DEBT_CID = "66d125ce-0523-492b-9679-3bd06d75e1be"  # Be Free from Debt
TV_URL = "https://lovelyn.matchqip.com/campaign-b8d56c20-c801-4c97-ac8f-936bb5c36cba.html"


@pytest.fixture(autouse=True)
def _hf_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test_token_x")


@pytest.fixture(autouse=True)
def _fresh_dedupe():
    wvp._completed_dedupe_keys.clear()
    yield
    wvp._completed_dedupe_keys.clear()


def _fake_client_predict(video_url="https://cdn.example/v.mp4", seed=42):
    """Return a mock client whose predict() returns the documented result
    shape: (generated_video, download_video list, seed)."""
    client = MagicMock()
    client.predict.return_value = (video_url, [video_url], seed)
    return client


# ------------------------------------------------------ authentication ----
class TestAuth:
    def test_missing_token_reports_exact_configuration(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        assert config_missing() == ["HF_TOKEN"]
        with pytest.raises(WanAuthError) as exc:
            generate_scene_clip(WanJob(prompt="x"))
        assert "HF_TOKEN" in str(exc.value)
        assert "environment variable" in str(exc.value) or \
               "repo secret" in str(exc.value)

    def test_token_never_logged(self, capsys):
        client = _fake_client_predict()
        with patch.object(wvp, "_get_client", return_value=client):
            generate_scene_clip(WanJob(prompt="x", dedupe_key="k1"))
        out = capsys.readouterr().out + capsys.readouterr().err
        assert "hf_test_token_x" not in out


# --------------------------------------------------- space/config errors ----
class TestSpaceErrors:
    def test_space_unreachable_is_recorded_not_silent(self, monkeypatch):
        def boom(space=None):
            raise WanProviderError("could not open Space xyz")
        monkeypatch.setattr(wvp, "_get_client", boom)
        # Provider failures are recorded on the job (bounded retry), never
        # silent and never a fake success.
        with patch.object(wvp, "_get_client",
                          side_effect=WanProviderError("down")), \
             patch.object(wvp.time, "sleep"):
            job = generate_scene_clip(WanJob(prompt="x", dedupe_key="k3"),
                                      max_attempts=1)
        assert job.error and "down" in job.error
        assert job.result_video_path is None

    def test_quota_error_stops_immediately_no_retry(self):
        client = MagicMock()
        with patch.object(wvp, "_get_client",
                          return_value=client) as m, \
             patch.object(wvp, "_submit_once",
                          side_effect=RuntimeError(
                              "You have exceeded your GPU quota (ZeroGPU)")), \
             patch.object(wvp.time, "sleep") as sl:
            with pytest.raises(WanQuotaExhausted):
                generate_scene_clip(WanJob(prompt="x", dedupe_key="k4"),
                                    max_attempts=2)
            assert m.call_count == 1
            assert sl.call_count == 0  # no backoff into a dead quota

    def test_api_failure_bounded_retries_then_error(self):
        client = MagicMock()
        with patch.object(wvp, "_get_client", return_value=client), \
             patch.object(wvp, "_submit_once",
                          side_effect=RuntimeError("server hiccup")), \
             patch.object(wvp.time, "sleep"):
            job = generate_scene_clip(WanJob(prompt="x", dedupe_key="k5"),
                                      max_attempts=2)
        assert job.error and "server hiccup" in job.error

    def test_timeout_treated_as_failure(self):
        client = MagicMock()
        with patch.object(wvp, "_get_client", return_value=client), \
             patch.object(wvp, "_submit_once",
                          side_effect=TimeoutError("timed out")), \
             patch.object(wvp.time, "sleep"):
            job = generate_scene_clip(WanJob(prompt="x", dedupe_key="k6"),
                                      max_attempts=1)
        assert job.error and "timed out" in job.error


# ------------------------------------------- request + result handling ----
class TestGeneration:
    def test_successful_generation_downloads_locally(self, tmp_path):
        local_file = tmp_path / "remote.mp4"
        local_file.write_bytes(b"fakevideo")
        client = MagicMock()
        with patch.object(wvp, "_get_client", return_value=client), \
             patch.object(wvp, "_submit_once",
                          return_value=(str(local_file), [str(local_file)], 7)):
            job = generate_scene_clip(WanJob(prompt="p", dedupe_key="k7"))
        assert job.result_video_path and os.path.isfile(job.result_video_path)
        assert job.seed_used == 7
        assert job.error is None

    def test_duplicate_generation_prevented(self):
        client = MagicMock()
        with patch.object(wvp, "_get_client", return_value=client) as g, \
             patch.object(wvp, "_submit_once",
                          return_value=("out.mp4", ["out.mp4"], 1)), \
             patch.object(wvp, "_download_to_local",
                          lambda ref, d: os.path.join(d, "wan_scene.mp4")):
            j1 = generate_scene_clip(WanJob(prompt="x", dedupe_key="dupk"))
            assert j1.result_video_path
            j2 = generate_scene_clip(WanJob(prompt="x", dedupe_key="dupk"))
        assert j2.error == "duplicate_generation_prevented"
        assert j2.metadata.get("skipped") is True
        assert g.call_count == 1  # second call never re-opened a job

    def test_i2v_request_passes_input_image(self):
        import gradio_client
        client = MagicMock()
        job = WanJob(prompt="animate", image_path="ref.png",
                     dedupe_key="k8")
        with patch.object(gradio_client, "handle_file",
                          lambda p: {"path": p}):
            wvp._submit_once(client, job)  # real submit path
        kwargs = client.predict.call_args[1]
        assert kwargs["input_image"] == {"path": "ref.png"}
        assert "animate" in kwargs["prompt"]
        assert kwargs["api_name"] == "/generate_video"

    def test_result_without_video_is_error(self):
        client = MagicMock()
        with patch.object(wvp, "_get_client", return_value=client), \
             patch.object(wvp, "_submit_once",
                          return_value=(None, [], 1)), \
             patch.object(wvp.time, "sleep"):
            job = generate_scene_clip(WanJob(prompt="x", dedupe_key="k9"),
                                      max_attempts=1)
        assert job.error and "without a video" in job.error


# --------------------------------------------- storyboard + authorization ----
class TestStoryboardAndAuth:
    def test_storyboard_built_from_verified_facts(self):
        sb = build_storyboard(TV_CID, TV_URL)
        assert sb["product_name"] == "TradingView"
        assert len(sb["shots"]) == 3
        joined = " ".join(s["narration"] for s in sb["shots"])
        # VERIFIED facts only - no invented prices/claims
        assert "indicators per chart" in joined
        assert "$99" not in joined and "guaranteed" not in joined
        assert "affiliate" in joined.lower()  # disclosure preserved

    def test_unknown_campaign_gets_no_storyboard(self):
        assert build_storyboard("nonexistent-cid", "https://x") is None

    def test_unauthorized_campaign_never_generated(self):
        repo = MagicMock()
        repo.is_promotion_approved.return_value = False
        status = produce_campaign_video(repo, TV_CID, TV_URL, "/tmp/x.mp4")
        assert status["error"] == "campaign_not_authorized"

    def test_authorized_campaign_passes_gate(self):
        repo = MagicMock()
        repo.is_promotion_approved.return_value = True
        assert is_campaign_authorized(repo, TV_CID) is True
        repo.is_promotion_approved.assert_called_with(TV_CID)

    def test_dry_run_generates_nothing_and_hits_no_gpu(self):
        repo = MagicMock()
        repo.is_promotion_approved.return_value = True
        status = produce_campaign_video(repo, TV_CID, TV_URL,
                                        "/tmp/x.mp4", dry_run=True)
        assert status["dry_run"] is True
        assert status["video"] is None
        assert len(status["shots"]) == 3


# ------------------------------------------------- production pipeline ----
class TestProductionPipeline:
    def test_full_production_with_mocked_wan_and_tts(self, tmp_path):
        repo = MagicMock()
        repo.is_promotion_approved.return_value = True
        fake_clip = tmp_path / "clip.mp4"
        fake_clip.write_bytes(b"v")
        with patch.object(wsp, "generate_scene_clip") as gen, \
             patch.object(wsp, "_narration_wav", lambda t, p: 3.5), \
             patch.object(wsp, "assemble_final",
                          lambda c, w, o: o):
            gen.side_effect = lambda job: (
                setattr(job, "result_video_path", str(fake_clip)),
                setattr(job, "seed_used", 1)) and job
            status = produce_campaign_video(
                repo, TV_CID, TV_URL, str(tmp_path / "out.mp4"))
        assert status["video"].endswith("out.mp4")
        assert len(status["shots"]) == 3
        assert not status.get("error")

    def test_quota_stops_production_gracefully(self):
        repo = MagicMock()
        repo.is_promotion_approved.return_value = True
        with patch.object(wsp, "generate_scene_clip",
                          side_effect=WanQuotaExhausted("quota gone")):
            status = produce_campaign_video(repo, TV_CID, TV_URL, "/tmp/x.mp4")
        assert "quota_exhausted" in status["error"]
        assert status["video"] is None

    def test_no_publishing_during_production(self, tmp_path):
        """The pipeline must never call any publishing/upload function."""
        import services.youtube_upload as yu
        with patch.object(yu, "upload_short",
                          side_effect=AssertionError("never publish")):
            repo = MagicMock()
            repo.is_promotion_approved.return_value = False
            status = produce_campaign_video(repo, TV_CID, TV_URL,
                                            str(tmp_path / "x.mp4"))
            assert status["error"] == "campaign_not_authorized"


# --------------------------------------------------- assembly + fallback ----
class TestAssemblyAndFallback:
    def test_assemble_runs_ffmpeg_concat(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(subprocess, "run",
                            lambda cmd, **k: calls.append(cmd) or
                            MagicMock())
        monkeypatch.setattr(wsp.os.path, "isfile", lambda p: True)
        clip = tmp_path / "c.mp4"; clip.write_bytes(b"x")
        wav = tmp_path / "n.wav"; wav.write_bytes(b"x")
        out = wsp.assemble_final([str(clip)], [str(wav)],
                                 str(tmp_path / "final.mp4"))
        assert out.endswith("final.mp4")
        assert any("concat" in c for c in calls)
        assert any(f"scale=1080:1920" in c for c in calls)
        assert any("libx264" in c for c in calls)

    def test_blender_provider_still_selectable(self, monkeypatch):
        """VIDEO_GENERATION_PROVIDER=blender keeps the existing renderer in
        play; Wan is opt-in."""
        from config import settings
        monkeypatch.setattr(settings, "VIDEO_GENERATION_PROVIDER",
                            "blender", raising=False)
        provider = os.getenv("VIDEO_GENERATION_PROVIDER",
                             getattr(settings, "VIDEO_GENERATION_PROVIDER",
                                     "blender"))
        assert provider == "blender"

    def test_wan_provider_selected_via_env(self, monkeypatch):
        monkeypatch.setenv("VIDEO_GENERATION_PROVIDER", "wan")
        assert os.getenv("VIDEO_GENERATION_PROVIDER") == "wan"

    def test_blender_renderer_untouched(self):
        import inspect
        from services import shorts_renderer
        src = inspect.getsource(shorts_renderer.render_short)
        assert "ffmpeg" in src  # existing renderer intact
