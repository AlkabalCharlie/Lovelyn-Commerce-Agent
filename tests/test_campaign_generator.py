from services.campaign_generator import generate_campaign

def test_generates_review():
    result = generate_campaign("Test Product", "Etsy", "Review")
    assert result["type"] == "Review Article"
    assert "Test Product" in result["headline"]

def test_generates_promo():
    result = generate_campaign("Test Product", "Shopify", "Promo")
    assert result["type"] == "Direct Promotion"

def test_handles_unknown_angle():
    result = generate_campaign("Test Product", "eBay", "SomethingWeird")
    assert result["type"] == "General Awareness"