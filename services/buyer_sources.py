"""Buyer-intelligence research sources.

READ-ONLY research using polite public endpoints, in the same spirit as
reddit_scout.py: descriptive User-Agent, sleeps between calls, hard call
caps, backoff (never retry storms) on 429/403, no login, no posting.

Every returned evidence record carries provenance:
  source, source_url, author, title, body, context, published_at.

Sources (first supported, more can be added):
  - reddit: search + post bodies via public JSON endpoints
  - hacker_news: Algolia HN Search API (public, documented, no key)
"""
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

USER_AGENT = "LovelynBuyerIntel/1.0 (commerce research; contact owner)"

MAX_CALLS_PER_SOURCE = 15
SECONDS_BETWEEN_CALLS = 2
BACKOFF_SECONDS = 30
TIMEOUT = 15


def _session_get(session, url, params=None):
    """GET with politeness backoff. Returns (ok, json_or_reason)."""
    try:
        resp = session.get(url, params=params, headers={"User-Agent": USER_AGENT},
                           timeout=TIMEOUT)
    except requests.RequestException as exc:
        return False, f"request_error: {type(exc).__name__}"
    if resp.status_code in (403, 429):
        time.sleep(BACKOFF_SECONDS)
        return False, f"http_{resp.status_code}_backoff"
    if resp.status_code != 200:
        return False, f"http_{resp.status_code}"
    try:
        return True, resp.json()
    except ValueError:
        return False, "invalid_json"


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def search_reddit(search_terms, subreddits=None, session=None,
                  max_calls=MAX_CALLS_PER_SOURCE, sleep_fn=time.sleep):
    """Reddit public JSON search INCLUDING selftext bodies.

    Read-only, no login, no posting. Same politeness rules as
    reddit_scout.py (which this module deliberately mirrors)."""
    session = session or requests
    subreddits = subreddits if subreddits is not None else [
        "personalfinance", "debtfree", "povertyfinance", "Daytrading",
        "trading", "stocks", "Forex", "SideProject", "SaaS", "smallbusiness",
    ]
    evidence = []
    calls = 0
    seen = set()
    for term in search_terms:
        for sub in ([None] + list(subreddits)):
            if calls >= max_calls:
                return evidence
            q = quote_plus(term)
            if sub:
                url = (f"https://www.reddit.com/r/{sub}/search.json?q={q}"
                       f"&sort=new&limit=25&restrict_sr=1")
            else:
                url = f"https://www.reddit.com/search.json?q={q}&sort=new&limit=25"
            ok, payload = _session_get(session, url)
            calls += 1
            if not ok:
                evidence.append({"_failed": True, "source": "reddit",
                                 "reason": payload})
                time.sleep(SECONDS_BETWEEN_CALLS)
                continue
            for child in (payload.get("data") or {}).get("children") or []:
                d = child.get("data") or {}
                permalink = d.get("permalink")
                title = d.get("title")
                if not (permalink and title):
                    continue
                full_url = "https://www.reddit.com" + permalink
                if full_url in seen:
                    continue
                seen.add(full_url)
                evidence.append({
                    "source": "reddit",
                    "source_url": full_url,
                    "author": d.get("author") or "",
                    "title": title,
                    "body": (d.get("selftext") or "")[:2000],
                    "context": f"r/{d.get('subreddit')}",
                    "published_at": _iso(d.get("created_utc")),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                })
            time.sleep(SECONDS_BETWEEN_CALLS)
    return evidence


def search_hacker_news(search_terms, session=None,
                       max_calls=MAX_CALLS_PER_SOURCE, sleep_fn=time.sleep):
    """Algolia HN Search API - public, documented, no auth required.
    Ask HN / Show HN threads carry genuine buyer questions and product
    feedback. Respectful call caps and sleeps."""
    session = session or requests
    evidence = []
    seen = set()
    calls = 0
    for term in search_terms:
        if calls >= max_calls:
            return evidence
        ok, payload = _session_get(
            session, "https://hn.algolia.com/api/v1/search",
            params={"query": term, "tags": "story", "hitsPerPage": 20})
        calls += 1
        if not ok:
            evidence.append({"_failed": True, "source": "hacker_news",
                             "reason": payload})
            time.sleep(SECONDS_BETWEEN_CALLS)
            continue
        for hit in payload.get("hits") or []:
            object_id = hit.get("objectID")
            title = hit.get("title") or hit.get("story_title")
            if not (object_id and title):
                continue
            url = f"https://news.ycombinator.com/item?id={object_id}"
            if url in seen:
                continue
            seen.add(url)
            evidence.append({
                "source": "hacker_news",
                "source_url": url,
                "author": hit.get("author") or "",
                "title": title,
                "body": (hit.get("story_text") or hit.get("comment_text")
                         or "")[:2000],
                "context": "Hacker News",
                "published_at": _iso(hit.get("created_at_i")),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            })
        time.sleep(SECONDS_BETWEEN_CALLS)
    return evidence


def collect_all(search_terms, session=None, sleep_fn=time.sleep):
    """Run every enabled source; return (evidence_list, sources_ok, sources_failed).

    A source that throws NEVER aborts the run: it is recorded as failed and
    the remaining sources still contribute."""
    sources_ok, sources_failed = [], []
    all_evidence = []

    for name, fn in (("reddit", search_reddit),
                     ("hacker_news", search_hacker_news)):
        try:
            result = fn(search_terms, session=session, sleep_fn=sleep_fn)
        except Exception as exc:  # absolute non-fatal guarantee
            sources_failed.append(f"{name}: {type(exc).__name__}")
            continue
        failures = [r for r in result if r.get("_failed")]
        good = [r for r in result if not r.get("_failed")]
        if good:
            sources_ok.append(name)
        if failures:
            reasons = sorted({f["reason"] for f in failures})
            sources_failed.append(f"{name}: {', '.join(reasons)}")
        all_evidence.extend(good)
    return all_evidence, sources_ok, sources_failed
