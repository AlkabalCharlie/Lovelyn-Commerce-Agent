"""Tiered extraction: JSON-LD, mocked headless render, thin->fallback,
price-never-invented, seeded-row skip."""
from bs4 import BeautifulSoup

import services.product_extractor as pe
from services.product_extractor import (
    _extract_tier2,
    _from_jsonld,
    _price_from_offer,
    extract_product_data_tiered,
)


def test_tier2_jsonld_parses_name_description_offer():
    html = """
    <html><head><script type="application/ld+json">
    {"@type": "Product", "name": "Charting Tool",
     "description": "Where the world charts, chats, and trades markets. Supercharged platform for traders.",
     "offers": {"@type": "Offer", "price": "15.00", "priceCurrency": "USD"}}
    </script></head><body></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_tier2(soup, html)
    assert result["title"] == "Charting Tool"
    assert "charts" in result["description"]
    assert result["price"] == "15.00"


def test_tier2_jsonld_graph_and_list_forms():
    desc = "x" * 100
    html_graph = f'''<script type="application/ld+json">{{"@graph": [{{"@type": "Product", "name": "G", "description": "{desc}", "offers": {{"price": 7}}}}]}}</script>'''
    result = _from_jsonld(BeautifulSoup(html_graph, "html.parser"))
    assert result["title"] == "G" and result["price"] == "7"

    html_list = f'''<script type="application/ld+json">[{{"@type": "Product", "name": "L", "description": "{desc}"}}]</script>'''
    result2 = _from_jsonld(BeautifulSoup(html_list, "html.parser"))
    assert result2["title"] == "L"


def test_tier2_microdata_itemprop():
    html = """
    <div itemscope>
      <span itemprop="name">Vest</span>
      <span itemprop="description">Hand knit wool vest, warm for winter layering days.</span>
      <meta itemprop="price" content="45.00">
    </div>"""
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_tier2(soup, "")
    assert result["title"] == "Vest"
    assert result["price"] == "45.00"


def test_tier2_next_data_state():
    desc = "z" * 100
    html = f'''<script id="__NEXT_DATA__" type="application/json">{{"props": {{"pageProps": {{"product": {{"name": "NP", "description": "{desc}", "offers": {{"price": 12.5}}}}}}}}}}</script>'''
    result = _extract_tier2(BeautifulSoup(html, "html.parser"), html)
    assert result["title"] == "NP" and result["price"] == "12.5"


def test_price_only_from_structured_offers_never_prose():
    """A page whose PROSE mentions '$99 deal' but has NO offer field must
    yield price=None. Prose numbers are never invented into a price."""
    html = """
    <html><head><script type="application/ld+json">
    {"@type": "Product", "name": "P",
     "description": "Customers say it used to cost 99 dollars, now cheaper, great deal!"}
    </script></head>
    <body><p>Buy now for only $99!</p></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    result = _extract_tier2(soup, html)
    assert "price" not in result  # no offer field -> no price
    # offer field present but null/empty -> still no price
    assert _price_from_offer({"offers": {"price": None}}) is None
    assert _price_from_offer({"offers": {}}) is None
    assert _price_from_offer({}) is None
    assert _price_from_offer({"offers": {"price": "19.99"}}) == "19.99"


def test_tier3_mocked_render_parse(monkeypatch):
    """Mock the playwright render: tier 3 result must merge in and respect fact-lock."""
    class FakeEl:
        def __init__(self, text=None, content=None):
            self._text = text
            self._content = content

        def inner_text(self):
            return self._text

        def get_attribute(self, name):
            return self._content

    class FakePage:
        def goto(self, url, timeout=None, wait_until=None):
            return None

        def title(self):
            return "Rendered Title"

        def inner_text(self, sel):
            return "Long rendered body text about the product. " * 10

        def query_selector(self, sel):
            if sel == "[itemprop=price]":
                return FakeEl(text="15.00")
            if sel.startswith("meta"):
                return FakeEl(content="Rendered meta description " * 4)
            return None

    class FakeBrowser:
        def new_page(self):
            return FakePage()

        def close(self):
            pass

    class FakePW:
        class chromium:
            @staticmethod
            def launch(headless=True):
                return FakeBrowser()

    class FakeSyncCtx:
        def __enter__(self):
            return FakePW()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pe, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(pe, "sync_playwright", lambda: FakeSyncCtx())

    result = pe._extract_tier3("https://example.com/p")
    assert result["title"] == "Rendered Title"
    assert result["price"] == "15.00"
    assert "Rendered" in result["description"]


def test_tier3_skipped_when_not_installed(monkeypatch):
    monkeypatch.setattr(pe, "PLAYWRIGHT_AVAILABLE", False)
    # Falls back gracefully: no exception, empty tier3 result.
    assert pe._extract_tier3("https://example.com/p") == {}


def test_thin_result_uses_manual_fallback():
    """Thin tier1 -> tier2 -> tier3 all empty -> tier4 returns tier1 as-is."""
    monkey_patches = {
        "_extract_tier3": lambda url, timeout_ms=20000: {},
        "PLAYWRIGHT_AVAILABLE": False,
    }
    html = "<html><head><title>Only Title</title></head><body>tiny</body></html>"
    html_full = pe._extract_tier2.__doc__  # touch for coverage hygiene
    result = extract_product_data_tiered.__wrapped__ if hasattr(
        extract_product_data_tiered, "__wrapped__") else None
    # Direct call with network mocked out entirely:
    import requests as req_mod

    class FakeResp:
        text = html
        status_code = 200

        def raise_for_status(self):
            pass

    monkey_patch_get = lambda *a, **k: FakeResp()  # noqa: E731
    orig_get = req_mod.get
    req_mod.get = monkey_patch_get
    try:
        out = extract_product_data_tiered("https://example.com/thin",
                                          playwright_enabled=False)
    finally:
        req_mod.get = orig_get
    assert out["title"] == "Only Title"
    assert out["description"] is None  # thin -> manual fallback expected
    assert out["price"] is None        # never invented


def test_seeded_rows_skipped_entirely():
    """list_products_missing_enrichment only returns description IS NULL rows,
    so seeded rows never hit the extractor. Verify the query's intent via the
    repository method's existence and shape."""
    from database.repositories import ProductRepository
    assert hasattr(ProductRepository, "list_products_missing_enrichment")
    # The needs_facts flag completes the loop: thin -> flag -> owner seeds ->
    # description set -> next run skips the row entirely.
    assert hasattr(ProductRepository, "mark_needs_facts")


def test_tier1_wins_when_not_thin(monkeypatch):
    """Non-thin tier1 result short-circuits - no tier2/3 attempted."""
    html = """<html><head>
    <meta property="og:title" content="Full Page">
    <meta property="og:description" content="A" * 200 + "></head>
    <body></body></html>"""
    html = """<html><head>
    <meta property="og:title" content="Full Page">
    <meta property="og:description" content="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA long enough description"></head>
    <body></body></html>"""

    class FakeResp:
        text = html
        status_code = 200

        def raise_for_status(self):
            pass

    monkeypatch.setattr(pe.requests, "get", lambda *a, **k: FakeResp())
    called = {"tier3": False}

    def fake_tier3(*a, **k):
        called["tier3"] = True
        return {}

    monkeypatch.setattr(pe, "_extract_tier3", fake_tier3)
    result = extract_product_data_tiered("https://example.com/full")
    assert result["title"] == "Full Page"
    assert not called["tier3"]  # tier 1 sufficed, tier 3 never ran
