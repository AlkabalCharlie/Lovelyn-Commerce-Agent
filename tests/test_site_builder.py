from services.site_builder import render_campaign_page, render_index, render_sitemap

CAMP = {
    "id": "abc-123",
    "headline": "<script>alert(1)</script> Test Headline",
    "body": "Line one\nLine & two",
    "campaign_type": "Review",
    "product_name": "Cool Product",
    "product_url": "https://example.com/p",
    "merchant": "Etsy",
}
BASE = "https://example.github.io/site/"


def test_campaign_page_escapes_html():
    page = render_campaign_page(CAMP, "ANONKEY", "https://ref.supabase.co", BASE)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_campaign_page_has_beacon_and_utm():
    page = render_campaign_page(CAMP, "ANONKEY", "https://ref.supabase.co", BASE)
    assert "ANONKEY" in page
    assert "utm_source=lovelyn" in page
    assert 'data-track="1"' in page


def test_campaign_page_has_disclosure_and_seo():
    page = render_campaign_page(CAMP, "ANONKEY", "https://ref.supabase.co", BASE)
    assert "Disclosure" in page
    assert 'name="robots" content="index, follow"' in page
    assert f"{BASE}campaign-abc-123.html" in page


def test_index_links_to_campaign_pages():
    idx = render_index([CAMP])
    assert "campaign-abc-123.html" in idx


def test_sitemap_lists_pages():
    sm = render_sitemap([CAMP], BASE)
    assert f"{BASE}campaign-abc-123.html" in sm
    assert "urlset" in sm