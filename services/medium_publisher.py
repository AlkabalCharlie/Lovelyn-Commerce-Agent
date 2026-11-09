"""Publishes articles to Medium via the free Medium API; prints the server's
exact refusal on failure. Medium flags automation faster than Bluesky, so the
agent paces this channel at ONE post per run (wired in autonomous_agent.py)."""
import requests

from config.settings import MEDIUM_API_KEY


def build_medium_article(headline: str, body: str, campaign_url: str) -> dict:
    """Medium API payload: markdown content + canonical URL back to our page."""
    content = body + f"\n\n[Read the full page here]({campaign_url})"
    return {
        "title": headline[:100],
        "contentFormat": "markdown",
        "content": content,
        "canonicalUrl": campaign_url,
        "publishStatus": "public",
    }


def publish_to_medium(headline: str, body: str, campaign_url: str) -> bool:
    if not MEDIUM_API_KEY:
        return False
    try:
        # Medium's API needs the author id: fetch it with the same token first.
        me = requests.get(
            "https://api.medium.com/v1/me",
            headers={"Authorization": f"Bearer {MEDIUM_API_KEY}"},
            timeout=20,
        )
        if me.status_code != 200:
            print(f"Medium refused /me: HTTP {me.status_code} {me.text[:300]}")
            return False
        author_id = me.json()["data"]["id"]
        r = requests.post(
            f"https://api.medium.com/v1/users/{author_id}/posts",
            headers={"Authorization": f"Bearer {MEDIUM_API_KEY}"},
            json=build_medium_article(headline, body, campaign_url),
            timeout=20,
        )
        if r.status_code in (200, 201):
            return True
        print(f"Medium refused: HTTP {r.status_code} {r.text[:300]}")
        return False
    except Exception as e:
        print(f"Medium error: {e}")
        return False
