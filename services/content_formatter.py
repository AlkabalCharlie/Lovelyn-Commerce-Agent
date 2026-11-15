"""Formats campaign drafts into final, publishable assets.

Distribution reality check: external platforms (Medium, Dev.to) penalize
bare product promos and search engines ignore them. Every exported asset
therefore LEADS with useful, standalone niche content and only then
mentions the product as one recommendation among the advice. That is both
more compliant and more likely to actually earn clicks.
"""

def format_campaign(campaign_type: str, headline: str, body: str, target_format: str,
                    niche_tip: str = None) -> str:
    """
    niche_tip: one or two sentences of genuinely useful, non-promotional
    advice for the niche. It becomes the opening of the asset so the piece
    reads as content first, promotion second. Falls back to a generic
    buyer-protection tip when unset.
    """
    tip = (niche_tip or "Before buying anything online, check the seller's own "
           "product page for exact deliverables, the update/refund policy, and "
           "at least three recent reviews mentioning real usage.").strip()
    if target_format == "Blog Post":
        return f"""# {headline}

**Meta Description:** {headline} - Read our honest take on this {campaign_type} before you buy.

## Worth knowing before you spend a dollar
{tip}

## The Breakdown
{body}

## Final Verdict
If you are looking for a solution that delivers on its promises, this {campaign_type} is worth considering. 

---
*Published by Lovelyn Commerce Intelligence*
"""

    elif target_format == "Social Thread":
        return f"""THREAD: {headline} 🧵

1/ {tip}

2/ Most people overlook the details of {campaign_type}s like this. Here is why it matters.

3/ Verdict: If this solves your problem, it's a solid pick. Link in bio! 👇
#Review #Productivity #Commerce
"""

    elif target_format == "Newsletter":
        return f"""Subject: {headline}

Preview: We tested the popular {campaign_type} so you don't have to.

Hi Reader,

{tip}

{body}

If you found this helpful, reply and let us know!

Best,
The Lovelyn Team
"""
    
    else:
        return f"Headline: {headline}\n\nBody: {body}"