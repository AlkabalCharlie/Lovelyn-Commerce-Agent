"""Publishes short posts to Bluesky via the free AT Protocol API."""
from datetime import datetime, timezone

import requests


def build_bluesky_post(headline: str, url: str) -> str:
    """Bluesky posts cap at 300 characters; keep the link intact."""
    head = headline.strip()
    post = f"{head}\n\n{url}"
    if len(post) > 300:
        room = 300 - len(url) - 5  # 2 for line breaks + 3 for the ellipsis
        if room < 1:
            return url[:300]
        trimmed = head[:room].rsplit(" ", 1)[0] or head[:room]
        post = f"{trimmed}...\n\n{url}"
    return post


def publish_to_bluesky(handle: str, app_password: str, headline: str, url: str) -> bool:
    if not (handle and app_password):
        return False
    try:
        s = requests.post(
            "https://bsky.social/xrpc/com.atproto.server.createSession",
            json={"identifier": handle, "password": app_password},
            timeout=15,
        )
        if s.status_code != 200:
            return False
        token = s.json()["accessJwt"]
        r = requests.post(
            "https://bsky.social/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo": handle,
                "collection": "app.bsky.feed.post",
                "record": {
                    "text": build_bluesky_post(headline, url),
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                },
            },
            timeout=15,
        )
        return r.status_code == 200
    except Exception:
        return False