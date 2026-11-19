"""Pings search engines that a rebuilt sitemap exists (P1-11).

IndexNow (Bing/Yandex/Naver/Seznam + others) needs a key file hosted on the
site to prove ownership; Google uses the Search Console sitemap ping instead,
which the owner performs once manually (see HUMAN_TASKS.md).

Zero-cost: plain HTTPS requests, no API keys, silent failures never crash
the agent run.
"""
import hashlib
import os

import requests

from config.settings import SITE_BASE_URL

INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
# Key can be any hex string; persisted per-install so it stays stable.
_KEY_FILE_NAME = "indexnow-key.txt"


def _key() -> str | None:
    key = os.getenv("INDEXNOW_KEY")
    if key:
        return key.strip()
    # Stable fallback: derive from SITE_BASE_URL so the key file on the site
    # never changes between runs unless the domain changes.
    return hashlib.sha256(SITE_BASE_URL.encode()).hexdigest()[:32]


def key_file_contents() -> str:
    return _key() or ""


def ping_indexnow(urls: list) -> bool:
    """Submit up to 10k URLs to the IndexNow shared endpoint.
    Returns True only on an acknowledged 2xx."""
    key = _key()
    if not key or not urls:
        return False
    try:
        r = requests.post(
            INDEXNOW_ENDPOINT,
            json={
                "host": SITE_BASE_URL.replace("https://", "").replace("http://", "").rstrip("/"),
                "key": key,
                "keyLocation": f"{SITE_BASE_URL}{key}.txt",
                "urlList": [u if u.startswith("http") else f"{SITE_BASE_URL}{u}" for u in urls[:10000]],
            },
            timeout=20,
        )
        if r.status_code in (200, 202):
            print(f"IndexNow accepted {len(urls)} URL(s).")
            return True
        print(f"IndexNow refused: HTTP {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        print(f"IndexNow error: {e}")
        return False


def ping_sitemap_urls(urls: list) -> None:
    """Best-effort: never raises, never blocks the agent."""
    if urls:
        ping_indexnow(urls)
