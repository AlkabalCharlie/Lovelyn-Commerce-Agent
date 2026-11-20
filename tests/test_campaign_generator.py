from services.campaign_generator import generate_campaign


def test_uses_real_price_and_description():
    r = generate_campaign(
        "Debt Guide", "Payhip", "Review",
        description="A 40-page plan covering budgeting and snowball payoff.", price="$7",
    )
    assert "$7" in r["body"]
    assert "snowball payoff" in r["body"]


def test_falls_back_without_facts(monkeypatch):
    """Template headline contains the product name. The AI polisher (live
    when a key is configured, e.g. Groq in this environment) can rephrase
    the headline, so pin the key OFF for this deterministic-template test."""
    from services import copy_polisher as cp
    monkeypatch.setattr(cp, "OPENAI_API_KEY", None)
    r = generate_campaign("Mystery Item", "Etsy", "Review")
    assert "Mystery Item" in r["headline"]
    assert "not listed" in r["body"]


def test_comparison_angle_mentions_merchant(monkeypatch):
    from services import copy_polisher as cp
    monkeypatch.setattr(cp, "OPENAI_API_KEY", None)
    r = generate_campaign("Vest", "Etsy", "Comparison", price="$45")
    assert "Etsy" in r["body"]


def test_promo_angle_type(monkeypatch):
    from services import copy_polisher as cp
    monkeypatch.setattr(cp, "OPENAI_API_KEY", None)
    r = generate_campaign("Vest", "Etsy", "Promo")
    assert r["type"] == "Direct Promotion"


def test_neutral_description_label():
    """Label must be neutral: descriptions mix extracted seller text AND
    owner-seeded notes, so 'What it is' is truthful for both."""
    r = generate_campaign(
        "Debt Guide", "Payhip", "Review",
        description="A 40-page plan covering budgeting and snowball payoff.", price="$7",
    )
    assert "What it is: A 40-page plan" in r["body"]
    assert "own words" not in r["body"]
    # Label applies across every angle, not just Review.
    for angle in ("Comparison", "Promo", "Story", "General"):
        assert "What it is:" in generate_campaign("X", "Payhip", angle, description="d")["body"]