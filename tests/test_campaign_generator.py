from services.campaign_generator import generate_campaign


def test_uses_real_price_and_description():
    r = generate_campaign(
        "Debt Guide", "Payhip", "Review",
        description="A 40-page plan covering budgeting and snowball payoff.", price="$7",
    )
    assert "$7" in r["body"]
    assert "snowball payoff" in r["body"]


def test_falls_back_without_facts():
    r = generate_campaign("Mystery Item", "Etsy", "Review")
    assert "Mystery Item" in r["headline"]
    assert "not listed" in r["body"]


def test_comparison_angle_mentions_merchant():
    r = generate_campaign("Vest", "Etsy", "Comparison", price="$45")
    assert "Etsy" in r["body"]


def test_promo_angle_type():
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