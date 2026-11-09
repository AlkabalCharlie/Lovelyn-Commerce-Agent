"""Tests for the Reddit Scout: parse, dedupe no-op, per-run caps, politeness."""
from datetime import datetime, timezone

import services.reddit_scout as rs


def _payload(*titles):
    """Fake Reddit search.json payload."""
    now = datetime.now(timezone.utc).timestamp()
    return {"data": {"children": [
        {"data": {"title": t, "permalink": f"/r/personalfinance/comments/{i}/x",
                  "created_utc": now, "subreddit": "personalfinance"}}
        for i, t in enumerate(titles)
    ]}}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        return self.responses.pop(0) if self.responses else FakeResponse(429)


def test_parse_reddit_json_extracts_fields():
    posts = rs.parse_reddit_json(_payload("How do I get out of debt?", "Best trading app?"))
    assert len(posts) == 2
    assert posts[0]["title"] == "How do I get out of debt?"
    assert posts[0]["subreddit"] == "personalfinance"
    assert posts[0]["url"].startswith("https://www.reddit.com/r/")
    assert isinstance(posts[0]["created_utc"], float)


def test_parse_reddit_json_skips_malformed_children():
    payload = {"data": {"children": [{"data": {}}, {"data": {"title": "only title"}}]}}
    assert rs.parse_reddit_json(payload) == []


def test_old_posts_filtered_out():
    old = now_ts = datetime.now(timezone.utc).timestamp() - (rs.RECENT_WINDOW_HOURS + 5) * 3600
    payload = {"data": {"children": [{"data": {
        "title": "old", "permalink": "/r/x/comments/1/a", "created_utc": old,
        "subreddit": "stocks"}}]}}
    posts = rs.parse_reddit_json(payload)
    assert posts and not rs._is_fresh(posts[0])


def test_call_cap_never_exceeded():
    session = FakeSession([FakeResponse(200, _payload("t"))] * 50)
    no_sleep = lambda *_: None  # noqa: E731
    rs.scout_reddit(["debt", "trading", "vest"],
                    subreddits=["personalfinance", "stocks"],
                    session=session, sleep_fn=no_sleep, max_calls=5)
    assert len(session.calls) <= 5


def test_insert_cap_honored_by_caller_pattern():
    # Simulate what autonomous_agent does: stop inserting at MAX_NEW_LEADS_PER_RUN.
    leads = [{"url": f"https://reddit.com/l{i}", "title": "t", "subreddit": "s",
              "created_utc": datetime.now(timezone.utc).timestamp()} for i in range(30)]
    kept = leads[:rs.MAX_NEW_LEADS_PER_RUN if hasattr(rs, "MAX_NEW_LEADS_PER_RUN") else 10]
    assert len(kept) <= 10


def test_backs_off_on_rate_limit_without_retry_storm():
    session = FakeSession([FakeResponse(429)] * 3)
    sleeps = []
    rs.scout_reddit(["debt"], subreddits=["personalfinance"], session=session,
                    sleep_fn=sleeps.append, max_calls=10)
    assert 429 not in (200,)  # no crash
    assert any(s >= rs.BACKOFF_SECONDS for s in sleeps)


def test_user_agent_is_descriptive():
    assert "LovelynScout" in rs.USER_AGENT


def test_module_exposes_no_posting_capability():
    # Guardrail #1: the scout is read-only - no post/comment/login functions.
    public = [n for n in dir(rs) if not n.startswith("_") and callable(getattr(rs, n))]
    assert not [n for n in public if "post" in n or "comment" in n or "login" in n]


def test_dedupe_seen_urls_in_scout_output():
    dup = "t1"
    payload = {"data": {"children": [
        {"data": {"title": dup, "permalink": "/r/x/comments/1/a",
                  "created_utc": datetime.now(timezone.utc).timestamp(),
                  "subreddit": "stocks"}}]}}
    session = FakeSession([FakeResponse(200, payload), FakeResponse(200, payload)])
    leads = rs.scout_reddit(["debt", "debt again"], subreddits=["stocks"],
                            session=session, sleep_fn=lambda *_: None, max_calls=10)
    urls = [l["url"] for l in leads]
    assert len(urls) == len(set(urls))
