"""Conversion copywriter: fact-lock gate, traffic eligibility, budget off-switch."""
from services.conversion_copywriter import rewrite_for_conversion, should_refresh


def _row(rid="r1", views=10):
    return {"id": rid, "views": views, "clicks": 0}


def test_should_refresh_skips_zero_view_pages():
    assert should_refresh(_row(views=0), set()) is False


def test_should_refresh_skips_already_refreshed():
    assert should_refresh(_row("r1"), {"r1"}) is False


def test_should_refresh_accepts_viewed_page():
    assert should_refresh(_row(views=7), set()) is True


def test_rewrite_noop_without_api_key(monkeypatch):
    import services.conversion_copywriter as cc
    monkeypatch.setattr(cc, "__name__", cc.__name__)  # keep module alive
    # OPENAI_API_KEY is imported inside the function; patch settings.
    import config.settings as settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    assert rewrite_for_conversion("H", "B" * 60, {"p": "x"}, 0, 0) is None


def test_rewrite_rejects_invented_numbers(monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "k")
    import services.conversion_copywriter as cc

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content":
                    "Great tool. Over 50000 traders switched. Only $19 today!"}}]}

    class FakeRequests:
        @staticmethod
        def post(*a, **k):
            return FakeResp()

    monkeypatch.setattr(cc.requests, "post", FakeRequests.post)
    # price fact says $12 - the AI's "$19" and "50000" are inventions.
    result = rewrite_for_conversion("H", "B" * 60, {"price": "$12"}, 0, 0)
    assert result is None


def test_rewrite_accepts_fact_clean_copy(monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "k")
    import services.conversion_copywriter as cc

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content":
                    "## Stop guessing\n\nYou open a chart and freeze. "
                    "TradingView free gives you 3 indicators - enough to start. "
                    "Check the live page for the price."}}]}

    class FakeRequests:
        @staticmethod
        def post(*a, **k):
            return FakeResp()

    monkeypatch.setattr(cc.requests, "post", FakeRequests.post)
    result = rewrite_for_conversion("H", "B" * 60, {"price": "3 indicators"}, 0, 0)
    assert result is not None
    assert result[1].startswith("## ")


def test_rewrite_never_touches_earning_pages(monkeypatch):
    """Revenue > 0 -> no rewrite, even with a key configured."""
    import config.settings as settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "k")
    assert rewrite_for_conversion("H", "B" * 60, {"p": "x"}, 2, 150) is None
