"""AI copy polish: fact-lock enforcement, graceful no-key degradation."""
import services.copy_polisher as cp
from services.copy_polisher import _facts_allow_all_numbers, _numbers_in, polish_body


def test_numbers_extraction():
    assert _numbers_in("costs $12.34 today") == {"12.34"}
    assert _numbers_in("3 charts, 40 pages") == {"3", "40"}
    assert _numbers_in("") == set()


def test_fact_lock_accepts_matching_numbers():
    facts = ["$7", "Debt Guide"]
    assert _facts_allow_all_numbers("It costs 7 dollars and has 7 chapters", facts)


def test_fact_lock_rejects_invented_numbers():
    facts = ["$7", "Debt Guide"]
    assert not _facts_allow_all_numbers("Now only $4.99!", facts)
    assert not _facts_allow_all_numbers("Over 10000 users", facts)


def test_no_key_means_template_passthrough(monkeypatch):
    monkeypatch.setattr(cp, "OPENAI_API_KEY", None)
    body = "## Verdict\nTemplate copy."
    assert polish_body(body, {"name": "X"}) == body  # byte-identical


def test_hallucinated_price_rejected_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(cp, "OPENAI_API_KEY", "test-key")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content":
                "Great news! Now only $3.99 - was $7! Over 5000 users love it."}}]}

    monkeypatch.setattr(cp.requests, "post",
                        lambda *a, **k: FakeResp())
    template = "## Verdict\nCosts $7."
    result = polish_body(template, {"name": "Debt Guide", "price": "$7"})
    assert result == template  # invented 3.99/5000 -> rejected, template kept


def test_clean_polish_accepted(monkeypatch):
    monkeypatch.setattr(cp, "OPENAI_API_KEY", "test-key")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content":
                "This $7 guide walks you through budgeting step by step. "
                "## Verdict\nDebt Guide earns a direct look."}}]}

    monkeypatch.setattr(cp.requests, "post", lambda *a, **k: FakeResp())
    result = polish_body("## Verdict\nCosts $7.", {"name": "Debt Guide", "price": "$7"})
    assert "budgeting" in result  # rephrase accepted
    assert "$7" in result        # locked price preserved


def test_http_error_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(cp, "OPENAI_API_KEY", "test-key")

    class BadResp:
        status_code = 500
        text = "server error"

    monkeypatch.setattr(cp.requests, "post", lambda *a, **k: BadResp())
    template = "## Verdict\nCosts $7."
    assert polish_body(template, {"price": "$7"}) == template


def test_network_exception_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(cp, "OPENAI_API_KEY", "test-key")

    def boom(*a, **k):
        raise ConnectionError("offline")

    monkeypatch.setattr(cp.requests, "post", boom)
    template = "## Verdict\nCosts $7."
    assert polish_body(template, {"price": "$7"}) == template


def test_generator_unchanged_without_key(monkeypatch):
    """The critical integration guarantee: no API key -> identical output."""
    monkeypatch.setattr(cp, "OPENAI_API_KEY", None)
    from services.campaign_generator import generate_campaign
    r = generate_campaign("Debt Guide", "Payhip", "Review",
                          description="A plan.", price="$7")
    assert "What it is: A plan." in r["body"]
    assert "What we checked" in r["body"]
