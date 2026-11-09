"""Reddit Scout: surface live humans asking to buy. The HUMAN replies by hand;
the bot NEVER posts or comments anywhere (guardrail #1).

Uses ONLY Reddit's public JSON endpoints, GET only, no login, no posting.
Be polite: descriptive User-Agent, sleep between calls, hard call cap,
back off (never retry-storm) on 429/403.
"""
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests

USER_AGENT = "LovelynScout/1.0 (commerce research; contact owner)"

DEFAULT_SUBREDDITS = [
    "personalfinance",
    "debtfree",
    "povertyfinance",
    "Daytrading",
    "trading",
    "stocks",
    "Forex",
]

MAX_CALLS_PER_RUN = 20          # hard cap on Reddit API calls per run
MAX_NEW_LEADS_PER_RUN = 10      # insert cap enforced by the caller in the agent
SECONDS_BETWEEN_CALLS = 2
RECENT_WINDOW_HOURS = 48
BACKOFF_SECONDS = 30


def build_search_url(subreddit, term, limit=25):
    """Public search endpoint for one subreddit; subreddit=None => site-wide."""
    q = quote_plus(term)
    if subreddit:
        return (f"https://www.reddit.com/r/{subreddit}/search.json"
                f"?q={q}&sort=new&limit={limit}&restrict_sr=1")
    return f"https://www.reddit.com/search.json?q={q}&sort=new&limit={limit}"


def parse_reddit_json(payload):
    """Extract (subreddit, title, permalink, created_utc) from a Reddit search payload."""
    posts = []
    children = (payload.get("data") or {}).get("children") or []
    for child in children:
        d = child.get("data") or {}
        title = d.get("title")
        permalink = d.get("permalink")
        created = d.get("created_utc")
        if not (title and permalink and created):
            continue
        posts.append({
            "subreddit": d.get("subreddit") or "",
            "title": title,
            "url": "https://www.reddit.com" + permalink,
            "created_utc": float(created),
        })
    return posts


def _is_fresh(post, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=RECENT_WINDOW_HOURS)
    created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
    return created >= cutoff


def scout_reddit(search_terms, subreddits=None, session=None, sleep_fn=time.sleep,
                 max_calls=MAX_CALLS_PER_RUN):
    """Search Reddit for live buyer questions. Returns deduped, fresh lead dicts.

    Pure-read helper: never posts, never comments, never logs in.
    """
    do_sleep = sleep_fn or (lambda *_: None)
    session = session or requests
    headers = {"User-Agent": USER_AGENT}
    subreddits = subreddits if subreddits is not None else DEFAULT_SUBREDDITS

    calls = 0
    seen_urls = set()
    leads = []
    for term in search_terms:
        for sub in ([None] + list(subreddits)):
            if calls >= max_calls:
                return leads
            url = build_search_url(sub, term)
            try:
                resp = session.get(url, headers=headers, timeout=15)
            except requests.RequestException:
                calls += 1
                do_sleep(SECONDS_BETWEEN_CALLS)
                continue
            calls += 1
            if resp.status_code in (403, 429):
                # Back off and skip - never retry-storm.
                do_sleep(BACKOFF_SECONDS)
                continue
            if resp.status_code != 200:
                do_sleep(SECONDS_BETWEEN_CALLS)
                continue
            try:
                posts = parse_reddit_json(resp.json())
            except ValueError:
                posts = []
            for post in posts:
                if not _is_fresh(post):
                    continue
                if post["url"] in seen_urls:
                    continue
                seen_urls.add(post["url"])
                leads.append(post)
            do_sleep(SECONDS_BETWEEN_CALLS)
    return leads


def scout_from_products(products):
    """Turn active products into scout terms: name + merchant per product."""
    terms = []
    for p in products:
        for field in ("name", "merchant"):
            value = (getattr(p, field, "") or "").strip()
            if value and value.lower() != "unknown":
                terms.append(value)
    # dedupe, keep order
    seen = set()
    return [t for t in terms if not (t in seen or seen.add(t))]
