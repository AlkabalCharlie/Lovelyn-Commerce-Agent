"""Generates specific, fact-based campaign copy from real product data.

Only uses facts we actually have (merchant, price, seller description).
Opinions are clearly labeled as opinions. Nothing is invented.
"""


def _facts_line(product_name: str, merchant: str, description, price) -> str:
    line = f"{product_name} is listed on {merchant}"
    if price:
        line += f" at {price}"
    line += "."
    if description:
        line += f" What it is: {description}"
    return line


def generate_campaign(product_name: str, merchant: str, angle: str,
                      description=None, price=None) -> dict:
    facts = _facts_line(product_name, merchant, description, price)
    price_note = price or "not listed (check the live page)"

    if angle == "Review":
        return {
            "type": "Review Article",
            "headline": f"{product_name} Review ({merchant}): What You Actually Get",
            "body": (
                f"{facts}\n\n"
                "## What we checked\n"
                f"- Where it is sold: {merchant}.\n"
                f"- Price point: {price_note}.\n"
                "- Whether the listing explains who it is for.\n\n"
                "Our take: judge it on whether it solves the exact problem described above — "
                "nothing more, nothing less.\n\n"
                "## Verdict\n"
                f"If your situation matches the listing description, {product_name} at {price_note} "
                "is worth a direct look."
            ),
        }
    if angle == "Comparison":
        return {
            "type": "Versus Comparison",
            "headline": f"{product_name} vs Alternatives on {merchant}: The Specifics",
            "body": (
                f"{facts}\n\n"
                "## How to compare it fairly\n"
                f"- Start with price: {price_note}. Anything pricier must prove why.\n"
                "- Compare the actual deliverables named in the description above.\n"
                f"- Check the seller's own page on {merchant} for updates and terms.\n\n"
                "Our take: compare on the specifics above, not on marketing vibes. "
                "The listing that names concrete deliverables usually wins."
            ),
        }
    if angle == "Promo":
        return {
            "type": "Direct Promotion",
            "headline": f"{product_name}: The Direct Route ({price_note})",
            "body": (
                f"{facts}\n\n"
                "## Why it exists\n"
                "It targets the exact problem named in the description above — no detours.\n\n"
                f"## What it costs\n"
                f"{price_note}, sold via {merchant}.\n\n"
                "Our take: if the problem described is yours right now, this is a direct route "
                "to a fix rather than another research loop."
            ),
        }
    if angle == "Story":
        return {
            "type": "Case Study / Story",
            "headline": f"How {product_name} Fits a Real Debt-or-Clutter Plan",
            "body": (
                f"{facts}\n\n"
                "## The pattern\n"
                "People stall not from lack of options but from unclear next steps. "
                f"A listing like {product_name} works when it converts 'someday' into a checklist.\n\n"
                "## The honest part\n"
                f"At {price_note}, the risk is small; the real cost is following through.\n\n"
                "Our take: stories like this matter only if the steps are real — "
                "the description above is where you verify them."
            ),
        }
    return {
        "type": "General Awareness",
        "headline": f"Discover {product_name} on {merchant}",
        "body": (
            f"{facts}\n\n"
            f"Currently listed at {price_note} on {merchant}. "
            "Our take: read the seller's description first, then decide."
        ),
    }