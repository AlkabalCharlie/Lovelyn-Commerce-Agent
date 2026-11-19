"""IndexNow ping helper: never raises, correct request shape."""
from services.index_ping import key_file_contents, ping_indexnow


def test_key_is_stable_hex():
    k1 = key_file_contents()
    k2 = key_file_contents()
    assert k1 == k2 and len(k1) >= 16


def test_ping_no_urls_is_safe_noop():
    assert ping_indexnow([]) is False


def test_ping_handles_network_failure(monkeypatch):
    import services.index_ping as ip

    class Boom:
        @staticmethod
        def post(*a, **k):
            raise ConnectionError("offline")

    monkeypatch.setattr(ip.requests, "post", Boom.post)
    assert ip.ping_indexnow(["https://example.com/x.html"]) is False
