from services.opportunity_scorer import calculate_opportunity_score

def test_high_score_etsy_owned():
    score, reasoning = calculate_opportunity_score("Etsy", "owned", True)
    assert score == 100  # 40 + 30 + 30
    assert "Marketplace Traffic" in reasoning
    assert "Owned Product" in reasoning
    assert "Rich Data" in reasoning

def test_low_score_independent_affiliate():
    score, reasoning = calculate_opportunity_score("Independent / Other", "affiliate", False)
    assert score == 35  # 10 + 15 + 10
    assert "Independent Store" in reasoning
    assert "Affiliate Only" in reasoning
    assert "Limited Data" in reasoning

def test_medium_score_jvzoo_both():
    score, _ = calculate_opportunity_score("JVZoo", "both", True)
    assert score == 75  # 25 + 20 + 30