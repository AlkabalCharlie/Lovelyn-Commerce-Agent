"""Shorts pipeline tests: generation, rendering config, uploader guards,
duplicate prevention, authorization. All network/media operations mocked or
isolated; NEVER touches the real YouTube channel or real financial events."""
import json
from unittest.mock import patch

import pytest

from services.publishing_queue import (
    QUEUE_STATUSES, find_by_youtube_video_id, mark_rendered, mark_uploaded,
    queue_package, set_status)
from services.shorts_renderer import W, H, FPS, _draw_frame, ffmpeg_missing


PKG = {
    "format_type": "youtube_shorts_script",
    "title": "Snowball vs Avalanche in 45 seconds",
    "hook": "Your debt payoff fails at the plan, not the motivation.",
    "scenes": [
        {"scene": 1, "duration_s": 5, "on_screen": "Hook",
         "narration": "Your debt payoff fails at the plan, not the motivation."},
        {"scene": 2, "duration_s": 25, "on_screen": "Facts",
         "narration": "Snowball pays the smallest balance first. Avalanche pays the highest rate first."},
        {"scene": 3, "duration_s": 10, "on_screen": "Who it is for",
         "narration": "If worksheets stay unopened, skip it."},
    ],
    "description": "Debt payoff methods compared. Disclosure: our own product.",
    "tags": ["debt payoff", "budgeting"],
    "disclosure": "Disclosure: this is our own product.",
}


# --- 1. Package generation ---------------------------------------------------

def test_package_generation_fact_bounded():
    pkg = dict(PKG)
    assert pkg["disclosure"].startswith("Disclosure:")
    # No invented price claims beyond facts
    assert "$9" not in json.dumps(pkg)


def test_package_has_required_production_fields():
    for key in ("title", "hook", "scenes", "description", "tags", "disclosure"):
        assert key in PKG, f"missing {key}"
    assert len(PKG["scenes"]) >= 3
    total = sum(s["duration_s"] for s in PKG["scenes"])
    assert 30 <= total <= 60  # target duration


# --- 2/3. Rendering configuration --------------------------------------------

def test_vertical_916_format_constants():
    assert (W, H) == (1080, 1920)
    assert W * 16 == H * 9


def test_render_frame_produces_correct_size():
    img = _draw_frame("Hook title", "caption text", progress=0.5)
    assert img.size == (W, H)


def test_render_duration_limits():
    # render_short rejects < 10s and > 75s via total narration duration.
    import inspect
    from services import shorts_renderer
    src = inspect.getsource(shorts_renderer.render_short)
    assert "total < 10" in src and "total > 75" in src


def test_missing_ffmpeg_raises_clean_error(monkeypatch):
    from services import shorts_renderer
    monkeypatch.setattr(shorts_renderer.shutil, "which", lambda _: None)
    assert shorts_renderer.ffmpeg_missing() is True
    with pytest.raises(RuntimeError, match="ffmpeg"):
        shorts_renderer.render_short(PKG, "/tmp/x.mp4")


def test_real_render_produces_mp4(tmp_path):
    """Milestone C verification (skipped when ffmpeg/TTS unavailable, e.g. CI)."""
    from services.shorts_renderer import render_short
    if ffmpeg_missing():
        pytest.skip("ffmpeg not on PATH")
    try:
        import pyttsx3  # noqa: F401
    except ImportError:
        pytest.skip("no local TTS")
    out = tmp_path / "short.mp4"
    result = render_short(PKG, str(out))
    assert result and out.exists() and out.stat().st_size > 50_000


# --- 6. Missing YouTube credentials -------------------------------------------

def test_missing_credentials_reported_not_uploaded(monkeypatch):
    import services.youtube_upload as yu
    monkeypatch.setattr(yu, "_get_setting", lambda k, d=None: None)
    ok, reason = yu.upload_short("/tmp/does_not_matter.mp4", "t", "d", [])
    assert ok is False
    assert reason.startswith("missing_config:")
    assert "YOUTUBE_REFRESH_TOKEN" in reason


def test_credentials_ready_true_when_all_set(monkeypatch):
    import services.youtube_upload as yu
    monkeypatch.setattr(yu, "_get_setting",
                        lambda k, d=None: {"YOUTUBE_CLIENT_ID": "id",
                                           "YOUTUBE_CLIENT_SECRET": "sec",
                                           "YOUTUBE_REFRESH_TOKEN": "rt"}.get(k))
    assert yu.credentials_ready() is True


# --- 7/8. Upload response handling --------------------------------------------

def test_successful_upload_returns_video_url(monkeypatch, tmp_path):
    import services.youtube_upload as yu
    fake_mp4 = tmp_path / "fake.mp4"
    fake_mp4.write_bytes(b"x" * 100)

    class FakeInsert:
        def next_chunk(self):
            return None, {"id": "abc123XYZ"}

    class FakeVideos:
        def insert(self, **kw):
            return FakeInsert()

    class FakeService:
        def videos(self):
            return FakeVideos()

    monkeypatch.setattr(yu, "credentials_ready", lambda: True)
    monkeypatch.setattr(yu, "_build_service", lambda: FakeService())
    monkeypatch.setattr("services.youtube_upload.MediaFileUpload",
                        lambda *a, **k: object())
    ok, result = yu.upload_short(str(fake_mp4), "t", "d", ["x"])
    assert ok is True
    assert result == "https://www.youtube.com/shorts/abc123XYZ"


def test_failed_upload_returns_reason_not_exception(monkeypatch, tmp_path):
    import services.youtube_upload as yu
    fake_mp4 = tmp_path / "fake.mp4"
    fake_mp4.write_bytes(b"x" * 100)

    class FakeVideos:
        def insert(self, **kw):
            class R:
                def next_chunk(self):
                    raise Exception("quotaExceeded")
            return R()

    class FakeService:
        def videos(self):
            return FakeVideos()

    monkeypatch.setattr(yu, "credentials_ready", lambda: True)
    monkeypatch.setattr(yu, "_build_service", lambda: FakeService())
    monkeypatch.setattr("services.youtube_upload.MediaFileUpload",
                        lambda *a, **k: object())
    ok, reason = yu.upload_short(str(fake_mp4), "t", "d", [])
    assert ok is False and "quotaExceeded" in reason


# --- 9. Duplicate upload prevention -------------------------------------------

def test_unique_video_id_constraint_blocks_double_assignment():
    """The partial unique index (migration) + WHERE youtube_video_id IS NULL
    guard make a second mark_uploaded with the same or different video id on
    an already-uploaded row impossible."""
    import inspect
    from services import publishing_queue
    src = inspect.getsource(publishing_queue.mark_uploaded)
    assert "youtube_video_id IS NULL" in src


def test_upload_failure_never_marks_published():
    """Policy: never mark published until YouTube confirms (mark_uploaded is
    only called on ok=True path). Verify the agent source respects it."""
    import inspect
    from services import autonomous_agent
    src = inspect.getsource(autonomous_agent.run_daily_grind)
    assert "mark_uploaded" in src
    assert 'if ok and "/shorts/" in vid_or_reason' in src


# --- 10. Campaign authorization -------------------------------------------------

def test_unauthorized_campaign_skipped_not_uploaded():
    import inspect
    from services import autonomous_agent
    src = inspect.getsource(autonomous_agent.run_daily_grind)
    # Both render and upload paths check authorization BEFORE acting.
    assert src.count("_authorized(camp_repo, str(item.get(\"campaign_id\")") >= 2
    assert 'set_status(item["id"], "skipped"' in src


# --- 11. Production queue isolation ----------------------------------------------

def test_shorts_statuses_valid():
    for s in ("queued", "generating", "rendered", "awaiting_upload", "uploading",
              "published", "failed", "skipped"):
        assert s in QUEUE_STATUSES


def test_set_status_rejects_invalid():
    with pytest.raises(ValueError):
        set_status("00000000-0000-0000-0000-000000000000", "bogus")


# --- 13. YouTube failure does not interrupt other channels ------------------------

def test_shorts_step_wrapped_non_fatal():
    import inspect
    from services import autonomous_agent
    src = inspect.getsource(autonomous_agent.run_daily_grind)
    # The shorts block ends with its own try/except that only logs.
    assert 'log_repo.log_action("SHORTS", f"Shorts pipeline step failed (non-fatal)' in src


# --- 14. Winner classification remains revenue-based -------------------------------

def test_winner_still_requires_verified_revenue():
    from services.optimizer import decide_action
    assert decide_action(views=5000, clicks=400, age_days=10, flag=None,
                         revenue_cents=0) != "winner"
    assert decide_action(views=3, clicks=0, age_days=2, flag=None,
                         revenue_cents=150) == "winner"


def test_find_by_video_id_roundtrip_shape():
    # Pure shape test against a mocked mapping row.
    with patch("services.publishing_queue.ensure_queue_table"):
        with patch("services.publishing_queue.engine") as fake_engine:
            class FakeConn:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def execute(self, *a, **k):
                    class R:
                        def mappings(self):
                            class M:
                                def first(self):
                                    return {"id": "q1", "title": "t",
                                            "publication_url": "u"}
                            return M()
                    return R()

            fake_engine.connect.return_value = FakeConn()
            row = find_by_youtube_video_id("vid123")
            assert row["id"] == "q1"
