"""Calculates an explainable opportunity score for a product."""

def calculate_opportunity_score(merchant: str, revenue_model: str, has_extracted_data: bool) -> tuple:
    """
    Returns a tuple of (score: int, reasoning: str).
    The score is out of 100, based on marketplace traffic, revenue model, and data confidence.
    """
    score = 0
    reasoning = []
    
    # 1. Marketplace Traffic Potential (Max 40 points)
    high_traffic = ["Etsy", "eBay", "Amazon", "Shopify"]
    medium_traffic = ["JVZoo", "Payhip", "Print-on-Demand"]
    
    if merchant in high_traffic:
        score += 40
        reasoning.append(f"✅ Marketplace Traffic: {merchant} has a massive built-in audience (+40).")
    elif merchant in medium_traffic:
        score += 25
        reasoning.append(f"🟡 Niche Marketplace: {merchant} has a targeted audience (+25).")
    else:
        score += 10
        reasoning.append(f"⚪ Independent Store: Requires building your own traffic (+10).")
        
    # 2. Revenue Model Potential (Max 30 points)
    if revenue_model == "owned":
        score += 30
        reasoning.append("✅ Owned Product: Highest profit margins and control (+30).")
    elif revenue_model == "both":
        score += 20
        reasoning.append("🟡 Hybrid Model: Mix of owned and affiliate potential (+20).")
    else:
        score += 15
        reasoning.append("⚪ Affiliate Only: Lower margins, relies on volume (+15).")
        
    # 3. Data Confidence (Max 30 points)
    if has_extracted_data:
        score += 30
        reasoning.append("✅ Rich Data: Title and image successfully extracted (+30).")
    else:
        score += 10
        reasoning.append("⚠️ Limited Data: Manual entry or extraction failed (+10).")
        
    reasoning_text = "\n".join(reasoning)
    return score, reasoning_text