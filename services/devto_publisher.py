"""Publishes articles to Dev.to; prints the server's exact refusal on failure."""
import requests

from config.settings import DEVTO_API_KEY


def publish_to_devto(headline: str, body: str, campaign_url: str) -> bool:
    if not DEVTO_API_KEY:
        return False
    try:
        r = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": DEVTO_API_KEY},
            json={
                "article": {
                    "title": headline[:120],
                    "body_markdown": body + f"\n\n[Read the full page here]({campaign_url})",
                    "tags": ["finance", "money", "productivity"],
                    "canonical_url": campaign_url,
                }
            },
            timeout=20,
        )
        if r.status_code == 201:
            return True
        print(f"Dev.to refused: HTTP {r.status_code} {r.text[:300]}")
        return False
    except Exception as e:
        print(f"Dev.to error: {e}")
        return False