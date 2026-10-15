"""Generates rule-based campaign ideas based on product data."""

def generate_campaign(product_name: str, merchant: str, angle: str) -> dict:
    """
    Generates a campaign headline and body based on the selected angle.
    Returns a dictionary with 'type', 'headline', and 'body'.
    """
    if angle == "Review":
        return {
            "type": "Review Article",
            "headline": f"Is {product_name} Worth It? An Honest {merchant} Review",
            "body": f"In this review, we break down the pros, cons, and pricing of {product_name} available on {merchant}. We help you decide if it solves your specific problem or if you should look at alternatives."
        }
    elif angle == "Comparison":
        return {
            "type": "Versus Comparison",
            "headline": f"{product_name} vs. The Competition: Which is Best?",
            "body": f"A side-by-side feature and price comparison of {product_name} against the top 3 alternatives on the market. Spoiler: {product_name} wins for users who prioritize ease of use."
        }
    elif angle == "Promo":
        return {
            "type": "Direct Promotion",
            "headline": f"Unlock Your Potential with {product_name}",
            "body": f"Stop struggling with the status quo. {product_name} is designed to deliver immediate results. Grab it today on {merchant} and take the first step toward your goal."
        }
    elif angle == "Story":
        return {
            "type": "Case Study / Story",
            "headline": f"How {product_name} Changed the Game",
            "body": f"Read the story of how a complete beginner used {product_name} to overcome their biggest hurdle. It's not just a product; it's a proven system."
        }
    else:
        return {
            "type": "General Awareness",
            "headline": f"Discover {product_name}",
            "body": f"An introduction to {product_name} and why it is trending on {merchant} right now."
        }