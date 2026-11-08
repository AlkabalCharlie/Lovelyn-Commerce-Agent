from services.bluesky_publisher import build_bluesky_post


def test_post_within_limit():
    post = build_bluesky_post("X" * 400, "https://example.com/a")
    assert len(post) <= 300
    assert post.endswith("https://example.com/a")


def test_post_keeps_short_headline():
    post = build_bluesky_post("Short headline", "https://example.com/b")
    assert "Short headline" in post