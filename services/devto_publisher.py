"""Pushes published campaigns to Dev.to for free SEO traffic."""
import requests
from config.settings import DEVTO_API_KEY

def publish_to_devto(headline: str, body: str, campaign_url: str) -> bool:
    """Publishes an article to Dev.to. Returns True if successful."""
    if not DEVTO_API_KEY:
        return False

    # Format the body to look like a high-value article, with the link at the bottom
    markdown_body = f"""
{body}

---

**Want the complete, step-by-step framework?** 
I put together a comprehensive, no-fluff guide that breaks down exactly how to execute this. 
[Read the full guide here]({campaign_url})
"""

    url = "https://dev.to/api/articles"
    headers = {"api-key": DEVTO_API_KEY, "Content-Type": "application/json"}
    payload = {
        "article": {
            "title": headline,
            "body_markdown": markdown_body,
            "published": True,
            "tags": ["finance", "money", "career", "productivity"],
            "canonical_url": campaign_url # Tells Google your GitHub page is the original source
        }
    }
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        return r.status_code == 201
    except Exception:
        return False