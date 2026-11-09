"""Medium publisher tests: uniform with the devto/bluesky publisher tests."""
from services.medium_publisher import build_medium_article, publish_to_medium


def test_build_medium_article_keeps_link_and_locks_headline():
    article = build_medium_article("Debt Guide Review", "Body text.",
                                   "https://example.com/campaign-x.html")
    assert article["title"] == "Debt Guide Review"
    assert article["contentFormat"] == "markdown"
    assert article["canonicalUrl"] == "https://example.com/campaign-x.html"
    assert "https://example.com/campaign-x.html" in article["content"]
    assert article["publishStatus"] == "public"


def test_headline_truncated_to_medium_limit():
    article = build_medium_article("H" * 300, "b", "https://example.com/x.html")
    assert len(article["title"]) <= 100


def test_publish_skips_when_key_missing(monkeypatch):
    monkeypatch.setattr("services.medium_publisher.MEDIUM_API_KEY", None)
    assert publish_to_medium("T", "B", "https://example.com/x.html") is False


def test_publish_returns_false_on_http_error(monkeypatch):
    monkeypatch.setattr("services.medium_publisher.MEDIUM_API_KEY", "fake-key")

    class FakeResp:
        status_code = 403
        text = "forbidden"

        def json(self):
            return {"data": {"id": "author-1"}}

    class FakeRequests:
        @staticmethod
        def get(*a, **k):
            return FakeResp()

    monkeypatch.setattr("services.medium_publisher.requests", FakeRequests)
    assert publish_to_medium("T", "B", "https://example.com/x.html") is False
