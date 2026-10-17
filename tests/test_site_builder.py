from services.site_builder import render_campaign_page, render_index

CAMP = {
    "id": "abc-123",
    "headline": "<script>alert(1)</script> Test Headline",
    "body": "Line one\nLine & two",
    "campaign_type": "Review",
    "product_name": "Cool Product",
    "product_url": "https://example.com/p",
    "merchant": "Etsy",
}


def test_campaign_page_escapes_html():
    page = render_campaign_page(CAMP, "ANONKEY", "https://ref.supabase.co")
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_campaign_page_has_beacon_and_utm():
    page = render_campaign_page(CAMP, "ANONKEY", "https://ref.supabase.co")
    assert "ANONKEY" in page
    assert "page_events" in page
    assert "utm_source=lovelyn" in page
    assert 'data-track="1"' in page


def test_index_links_to_campaign_pages():
    idx = render_index([CAMP])
    assert "campaign-abc-123.html" in idx
    assert "Test Headline" in idx