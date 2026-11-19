"""Publishes articles to Dev.to; prints the server's exact refusal on failure."""
import requests

from config.settings import DEVTO_API_KEY


def publish_to_devto(headline: str, body: str, campaign_url: str) -> str | None:
    """Returns the published article URL on success, None on failure."""
    if not DEVTO_API_KEY:
        return None
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
            # Dev.to returns the live article URL in Location on create.
            return r.headers.get("Location") or r.json().get("url") or ""
        print(f"Dev.to refused: HTTP {r.status_code} {r.text[:300]}")
        return None
    except Exception as e:
        print(f"Dev.to error: {e}")
        return None