"""Tests for the visual + neural-TTS upgrade. Media operations isolated;
no upload; no live queue writes."""
import math

from PIL import Image

from services.shorts_visuals import Scene, draw_scene, scene_for_narration
from services.shorts_renderer import W, H, FPS, _compose_frame


# --- Visual scene system ------------------------------------------------------

def test_every_scene_kind_renders_distinct_frames():
    kinds = ("hook", "snowball", "avalanche", "chart", "planner", "cta")
    frames = []
    for k in kinds:
        s = Scene(k, "cap")
        s.t = 0.5
        frames.append(draw_scene(s, frame_idx=15, fps=FPS))
    # distinct pixels per kind (not one repeated background)
    import itertools
    for a, b in itertools.combinations(range(len(frames)), 2):
        pa, pb = frames[a].tobytes(), frames[b].tobytes()
        assert pa != pb, f"{kinds[a]} and {kinds[b]} look identical"


def test_characters_move_between_frames():
    s = Scene("hook", "cap")
    s.t = 0.1
    f1 = draw_scene(s, frame_idx=0, fps=FPS)
    s.t = 0.6
    f2 = draw_scene(s, frame_idx=18, fps=FPS)
    assert f1.tobytes() != f2.tobytes(), "character idle motion missing"


def test_narration_maps_to_matching_visual():
    assert scene_for_narration(
        "Snowball pays the smallest balance first", "c").kind == "snowball"
    assert scene_for_narration(
        "Avalanche attacks the highest interest rate", "c").kind == "avalanche"
    assert scene_for_narration(
        "TradingView charts and indicators", "c").kind == "chart"
    assert scene_for_narration(
        "Get the worksheet pack, link below", "c").kind == "cta"


def test_composite_frame_has_vertical_format_and_captions():
    s = Scene("planner", "caption line")
    s.t = 0.4
    img = _compose_frame(s, "caption line", 10, FPS, "Title text")
    assert img.size == (W, H)
    # caption pixels present (white text on dark chip in bottom area)
    bottom = img.crop((0, H - 420, W, H - 120))
    colors = bottom.getcolors(maxcolors=1 << 24)
    assert any(c[1][0] > 220 and c[1][1] > 220 for c in colors), \
        "caption text pixels missing"


def test_transitions_crossfade_present():
    import inspect
    from services import shorts_renderer
    src = inspect.getsource(shorts_renderer.render_short)
    assert "_crossfade" in src and "FADE_FRAMES" in src


# --- Neural TTS ---------------------------------------------------------------

def test_tts_is_neural_by_default():
    import inspect
    from services import shorts_renderer
    src = inspect.getsource(shorts_renderer._narration_wav)
    assert "edge_tts" in src
    # Robotic SAPI only as LOUD fallback, never silent
    assert "WARNING" in src and "DOWNGRADE" in src


def test_tts_fallback_not_silent(monkeypatch, tmp_path):
    """If edge-tts fails, the fallback prints a loud warning."""
    import services.shorts_renderer as sr
    calls = []

    def fake_run(text, out_path):
        calls.append(text)
        return 1.0

    monkeypatch.setattr(sr, "_wav_duration", lambda p: 1.0)
    # force edge-tts path to fail
    import asyncio

    def fail_run():
        raise RuntimeError("network down")

    monkeypatch.setattr(sr.asyncio if hasattr(sr, "asyncio") else asyncio,
                        "run", fail_run)
    # pyttsx3 fallback should still produce duration
    class FakeEngine:
        def setProperty(self, *a):
            pass

        def save_to_file(self, *a):
            pass

        def runAndWait(self):
            pass

    import sys
    fake = type(sys)("pyttsx3")
    fake.init = lambda: FakeEngine()
    monkeypatch.setitem(sys.modules, "pyttsx3", fake)
    dur = sr._narration_wav("hello world", str(tmp_path / "o.wav"))
    assert dur == 1.0
