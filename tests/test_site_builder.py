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


# ---- stale-page pruning (sitemap consistency guarantee) ----

def test_build_site_prunes_stale_campaign_pages(tmp_path, monkeypatch):
    """A campaign-*.html left over from a no-longer-published campaign must be
    deleted on rebuild, so the published sitemap can never list a stale URL."""
    from services import site_builder

    class FakeRepo:
        def list_published_campaigns(self):
            return [{"id": "22222222-2222-2222-2222-222222222222", "headline": "Live"}]

    monkeypatch.setattr(site_builder, "CampaignRepository", FakeRepo)
    monkeypatch.setattr(site_builder, "SUPABASE_ANON_KEY", "ANONKEY")
    monkeypatch.setattr(site_builder, "render_campaign_page", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(site_builder, "_rest_url", lambda: "https://fake.supabase.co")

    out = tmp_path / "docs"
    out.mkdir()
    (out / "campaign-11111111-1111-1111-1111-111111111111.html").write_text("stale")

    site_builder.build_site(output_dir=str(out))

    assert not (out / "campaign-11111111-1111-1111-1111-111111111111.html").exists()
    assert (out / "campaign-22222222-2222-2222-2222-222222222222.html").exists()


def test_build_site_publishes_only_authorized_campaigns(tmp_path, monkeypatch):
    """DB-driven authorization: list_published_campaigns() already filters on
    promotion_approved=TRUE, so the builder renders exactly what the DB says
    is published AND authorized - and nothing else."""
    from services import site_builder

    authorized_id = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
    unauthorized_id = "36f0f37b-2e81-49c7-874b-285317abee7c"

    class FakeRepo:
        def list_published_campaigns(self):
            # Simulates the SQL WHERE promotion_approved = TRUE: the
            # unauthorized row never comes back from the database at all.
            return [
                {"id": authorized_id, "headline": "Authorized"},
            ]

    monkeypatch.setattr(site_builder, "CampaignRepository", FakeRepo)
    monkeypatch.setattr(site_builder, "SUPABASE_ANON_KEY", "ANONKEY")
    monkeypatch.setattr(site_builder, "render_campaign_page", lambda *a, **k: "<html></html>")
    monkeypatch.setattr(site_builder, "_rest_url", lambda: "https://fake.supabase.co")

    out = tmp_path / "docs"
    out.mkdir()
    (out / f"campaign-{unauthorized_id}.html").write_text("stale")

    assert site_builder.build_site(output_dir=str(out)) == 1
    assert (out / f"campaign-{authorized_id}.html").exists()
    assert not (out / f"campaign-{unauthorized_id}.html").exists()
    assert f"campaign-{authorized_id}.html" in (out / "index.html").read_text()
    assert f"campaign-{unauthorized_id}.html" not in (out / "index.html").read_text()
    assert f"campaign-{authorized_id}.html" in (out / "sitemap.xml").read_text()
    assert f"campaign-{unauthorized_id}.html" not in (out / "sitemap.xml").read_text()


def test_build_site_never_touches_non_campaign_files(tmp_path, monkeypatch):
    from services import site_builder

    class EmptyRepo:
        def list_published_campaigns(self):
            return []

    monkeypatch.setattr(site_builder, "CampaignRepository", EmptyRepo)
    monkeypatch.setattr(site_builder, "_rest_url", lambda: "https://fake.supabase.co")

    out = tmp_path / "docs"
    out.mkdir()
    (out / "campaign-deadbeef.html").write_text("looks like a stale real-id page")
    (out / "notes.txt").write_text("keep me")

    site_builder.build_site(output_dir=str(out))

    assert not (out / "campaign-deadbeef.html").exists()  # real-id-shaped: pruned
    assert (out / "notes.txt").exists()                   # non-campaign files kept

def test_owned_checkout_carries_campaign_id_for_attribution():
    """The gumroad-ping Edge Function attributes a sale by reading campaign_id
    from the buyer's URL params. Owned checkouts MUST carry it."""
    owned = dict(CAMP, product_url="https://chukafor.gumroad.com/l/baqctc")
    page = render_campaign_page(owned, "ANONKEY", "https://ref.supabase.co", BASE)
    assert "campaign_id=abc-123" in page


def test_affiliate_links_do_not_carry_campaign_id():
    """Affiliate URLs must not be altered beyond UTM params (directive rule)."""
    affiliate = dict(CAMP, product_url="https://example.com/p",
                     affiliate_url="https://www.tradingview.com/black-friday/?aff_id=170584")
    page = render_campaign_page(affiliate, "ANONKEY", "https://ref.supabase.co", BASE)
    assert "campaign_id=" not in page.split('data-track="1"')[1].split("</a>")[0]
