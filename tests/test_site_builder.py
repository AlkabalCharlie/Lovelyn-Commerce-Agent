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


from services.site_builder import _md_to_html, render_campaign_page


def test_markdown_never_leaks_raw_hashes():
    """Regression: '## What we checked' must render as <h2>, not literal '##'."""
    camp = dict(CAMP)
    camp["body"] = ("Intro paragraph.\n\n## What we checked\n\n### Pricing\n"
                    "- Fact one\n- Fact two\n\nClosing line.")
    page = render_campaign_page(camp, "ANONKEY", "https://ref.supabase.co", BASE)
    assert "##" not in page
    assert "<h2>What we checked</h2>" in page
    assert "<h3>Pricing</h3>" in page


def test_markdown_escapes_before_converting():
    """Escaping happens FIRST: a malicious body can't inject HTML via headings."""
    camp = dict(CAMP)
    camp["body"] = "## <script>alert(1)</script>\n\n- <img src=x onerror=alert(2)>"
    page = render_campaign_page(camp, "ANONKEY", "https://ref.supabase.co", BASE)
    assert "<script>alert(1)</script>" not in page
    assert "<img src=x" not in page
    assert "<h2>&lt;script&gt;" in page
    assert "<li>&lt;img src=x onerror=alert(2)&gt;</li>" in page


def test_md_to_html_lists_wrap_consecutive_items():
    html = _md_to_html("- a\n- b\nplain line")
    assert "<ul><li>a</li><li>b</li></ul>" in html
    assert "<p>plain line</p>" in html


def test_md_to_html_blank_lines_split_paragraphs():
    html = _md_to_html("first\n\nsecond")
    assert "<p>first</p>" in html and "<p>second</p>" in html
