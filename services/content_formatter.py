"""Formats campaign drafts into final, publishable assets."""

def format_campaign(campaign_type: str, headline: str, body: str, target_format: str) -> str:
    """
    Converts a raw campaign draft into a formatted string for export.
    """
    if target_format == "Blog Post":
        return f"""# {headline}

**Meta Description:** {headline} - Read our honest take on this {campaign_type} before you buy.

## The Breakdown
{body}

## Final Verdict
If you are looking for a solution that delivers on its promises, this {campaign_type} is worth considering. 

---
*Published by Lovelyn Commerce Intelligence*
"""

    elif target_format == "Social Thread":
        return f"""THREAD: {headline} 🧵

1/ {body}

2/ Most people overlook the details of {campaign_type}s like this. Here is why it matters.

3/ Verdict: If this solves your problem, it's a solid pick. Link in bio! 👇
#Review #Productivity #Commerce
"""

    elif target_format == "Newsletter":
        return f"""Subject: {headline}

Preview: We tested the popular {campaign_type} so you don't have to.

Hi Reader,

{body}

If you found this helpful, reply and let us know!

Best,
The Lovelyn Team
"""
    
    else:
        return f"Headline: {headline}\n\nBody: {body}"