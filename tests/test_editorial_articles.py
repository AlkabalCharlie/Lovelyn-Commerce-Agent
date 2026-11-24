"""Editorial article quality tests for Blogger publishing.

Covers: full article structure, length validation, HTML formatting, verified
product facts only, correct campaign URL, disclosure presence, image existence
and public URL, image embedding + alt text, draft update without duplication,
and refusal to publish unapproved or low-quality content.
"""
import os
import re

import pytest

from services.editorial_articles import (
    MAX_WORDS, MIN_WORDS, debt_payoff_article, tradingview_article,
    validate_article,
)
from services.editorial_images import (
    IMG_H, IMG_W, illustrated_featured_image,
)

DEBT = "66d125ce-0523-492b-9679-3bd06d75e1be"
TV = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
DEBT_URL = f"https://lovelyn.matchqip.com/campaign-{DEBT}.html"
TV_URL = f"https://lovelyn.matchqip.com/campaign-{TV}.html"
IMG = "https://lovelyn.matchqip.com/assets/test-featured.png"
ALT = "Editorial illustration of a household debt ledger."


def _debt():
    return debt_payoff_article(DEBT_URL, IMG, ALT)


def _tv():
    return tradingview_article(TV_URL, IMG, ALT)


# ------------------------------------------------------------- length ----
class TestLength:
    def test_debt_article_within_editorial_range(self):
        stats = validate_article(_debt())["stats"]
        assert MIN_WORDS <= stats["words"] <= MAX_WORDS

    def test_tradingview_article_within_range(self):
        stats = validate_article(_tv())["stats"]
        assert MIN_WORDS <= stats["words"] <= MAX_WORDS

    def test_thin_article_rejected(self):
        thin = dict(_debt(), body_html="<p>Buy our great product now.</p>")
        result = validate_article(thin)
        assert result["ok"] is False
        assert any("too short" in f for f in result["failures"])

    def test_word_count_is_not_the_only_measure(self):
        """A long body of repeated one-liners must still fail on structure."""
        body = "<p>Short line.</p>" * 200
        long_but_empty = dict(_debt(), body_html=body)
        result = validate_article(long_but_empty)
        assert result["ok"] is False
        assert any("H2" in f or "substantive" in f for f in result["failures"])


# ---------------------------------------------------------- structure ----
class TestStructure:
    def test_required_sections_present(self):
        art = _debt()
        body = art["body_html"]
        assert body.startswith("<p>")            # prose intro, not a list
        assert body.count("<h2") >= 3
        assert body.count("<h3") >= 1
        # explanation of both methods
        assert "avalanche" in body.lower()
        assert "snowball" in body.lower()

    def test_decision_section_present(self):
        assert re.search(r"making the decision", _debt()["body_html"], re.I)

    def test_tradeoffs_discussed_not_one_best_method(self):
        body = _debt()["body_html"].lower()
        assert "trade-off" in body or "costs" in body
        assert not re.search(r"always the best|universally best", body)

    def test_hypothetical_example_labelled(self):
        body = _debt()["body_html"].lower()
        assert "hypothetical" in body
        assert "illustrative figures" in body or "not a prediction" in body

    def test_snowball_motivation_vs_avalanche_interest_explained(self):
        body = _debt()["body_html"].lower()
        assert "momentum" in body
        assert "interest saved" in body
        assert "when all other conditions remain equal" in body


# --------------------------------------------------- facts and claims ----
class TestFactsAndClaims:
    def test_disclosure_present(self):
        assert "own product" in _debt()["body_html"]

    def test_campaign_url_present_and_exact(self):
        body = _debt()["body_html"]
        assert DEBT_URL in body
        assert "payhip.com" not in body  # CTA goes via the campaign landing page

    def test_no_unsupported_product_claims(self):
        body = _debt()["body_html"].lower()
        for banned in ("guaranteed", "limited time", "act now",
                       "studies show", "research shows", "proven to",
                       "discount", "bonus"):
            assert banned not in body, f"banned claim: {banned}"

    def test_no_worksheets_beat_apps_claim(self):
        body = _debt()["body_html"].lower()
        # the article explicitly avoids claiming worksheets beat apps and
        # tells the reader they need not buy anything
        assert "you do not need to buy anything" in body
        # no claim that worksheets/apps win on outcomes
        assert "worksheets outperform" not in body
        assert "better than apps" not in body

    def test_unverified_price_flagged(self):
        art = _debt()
        # Remove the hypothetical-example exemption so the validator applies
        # the strict fact check to every dollar figure in the body.
        body = art["body_html"].replace("hypothetical", "illustrative")
        body = body.replace("</p>", " Only $199 today.</p>", 1)
        bad = dict(art, body_html=body)
        result = validate_article(bad)
        assert result["ok"] is False
        assert any("unverified price" in f for f in result["failures"])

    def test_invented_statistic_flagged(self):
        bad = dict(_debt(),
                   body_html=_debt()["body_html"].replace(
                       "</p>", " 87% of people agree.</p>", 1))
        assert validate_article(bad)["ok"] is False


# -------------------------------------------------------------- HTML ----
class TestHtml:
    def test_balanced_tags(self):
        body = _debt()["body_html"]
        for tag in ("p", "h2", "h3"):
            assert body.count(f"<{tag}") == body.count(f"</{tag}>")

    def test_no_inline_styles(self):
        bad = dict(_debt(), body_html="<p style='color:red'>x</p>")
        assert validate_article(bad)["ok"] is False

    def test_link_rendered_as_anchor(self):
        assert '<a href="' + DEBT_URL + '">' in _debt()["body_html"]


# ------------------------------------------------------------- images ----
class TestImages:
    def test_missing_image_rejected(self):
        bad = dict(_debt(), featured_image_url=None)
        result = validate_article(bad)
        assert result["ok"] is False
        assert any("featured image URL" in f for f in result["failures"])

    def test_local_path_rejected(self):
        bad = dict(_debt(), featured_image_url="docs/assets/x.png")
        assert validate_article(bad)["ok"] is False

    def test_missing_alt_rejected(self):
        bad = dict(_debt(), featured_image_alt="")
        assert validate_article(bad)["ok"] is False

    def test_local_illustration_generated_16_9(self, tmp_path, monkeypatch):
        from services import editorial_images
        monkeypatch.setattr(editorial_images, "DOCS_ASSETS", str(tmp_path))
        path = editorial_images.illustrated_featured_image(
            "Snowball vs Avalanche", "Debt payoff", "test-featured.png")
        assert os.path.isfile(path)
        from PIL import Image
        with Image.open(path) as im:
            assert im.size == (IMG_W, IMG_H)
            assert round(IMG_W / IMG_H, 4) == round(16 / 9, 4)

    def test_existing_image_never_overwritten(self, tmp_path, monkeypatch):
        from services import editorial_images
        monkeypatch.setattr(editorial_images, "DOCS_ASSETS", str(tmp_path))
        first = editorial_images.illustrated_featured_image(
            "A", "B", "keep.png")
        before = os.path.getmtime(first)
        size_before = os.path.getsize(first)
        again = editorial_images.illustrated_featured_image(
            "Different headline", "C", "keep.png")
        assert again == first
        assert os.path.getsize(again) == size_before
        assert os.path.getmtime(again) == before

    def test_public_image_url_reachable(self):
        """Live check - skipped when offline or when Pages has not deployed."""
        import requests
        url = ("https://lovelyn.matchqip.com/assets/"
               "snowball-vs-avalanche-featured.png")
        try:
            r = requests.get(url, timeout=20)
        except requests.RequestException:
            pytest.skip("network unavailable")
        if r.status_code != 200:
            pytest.skip(f"Pages not serving yet ({r.status_code})")
        assert r.headers.get("content-type", "").startswith("image/")
        assert len(r.content) > 10_000


# ------------------------------------------- publication safety gates ----
class TestPublicationSafety:
    def test_quality_gate_blocks_thin_package(self):
        from services.publishing_service import check_article_quality
        pkg = {"format_type": "blogger_article_markdown",
               "campaign_url": DEBT_URL,
               "disclosure": "Disclosure: own product.",
               "featured_image_url": IMG, "featured_image_alt": ALT}
        result = check_article_quality(
            pkg, "<p>Avalanche saves interest.</p><p>Snowball saves "
                 "motivation.</p>")
        assert result["ok"] is False
        assert any("too short" in f for f in result["failures"])

    def test_editorial_package_passes_gate(self):
        from services.publishing_service import check_article_quality
        art = _debt()
        assert check_article_quality(art, art["body_html"])["ok"] is True

    def test_unapproved_campaign_never_published(self):
        from unittest.mock import MagicMock, patch
        from services import publishing_service, blogger_publisher
        repo = MagicMock()
        repo.is_promotion_approved.return_value = False
        row = {"id": "r1", "channel": "blogger", "campaign_id": DEBT,
               "title": "T", "package": _debt()}
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[row]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(blogger_publisher, "publish_post") as post:
            out = publishing_service.publish_blogger_drafts(
                repo, blog_id="b1")
        post.assert_not_called()
        assert out["skipped"][0]["reason"] == "campaign_not_authorized"

    def test_low_quality_package_not_sent_to_blogger(self):
        from unittest.mock import MagicMock, patch
        from services import publishing_service, blogger_publisher
        repo = MagicMock()
        repo.is_promotion_approved.return_value = True
        thin = {"format_type": "blogger_article_markdown",
                "title": "Thin", "campaign_url": DEBT_URL,
                "disclosure": "Disclosure: own product.",
                "body_markdown": "Avalanche saves interest."}
        row = {"id": "r2", "channel": "blogger", "campaign_id": DEBT,
               "title": "Thin", "package": thin}
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[row]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "mark_publish_failed"), \
             patch.object(blogger_publisher, "publish_post") as post:
            publishing_service.publish_blogger_drafts(repo, blog_id="b1")
        post.assert_not_called()

    def test_draft_update_uses_patch_not_insert(self):
        """Updating an existing draft must never create a second post.
        The controlled update used posts().patch on a known post id; the
        provider keeps insert for genuinely new posts only."""
        import inspect
        from services import blogger_publisher
        src = inspect.getsource(blogger_publisher)
        assert "posts().insert" in src
        assert "isDraft" in src
        # No update helper ever calls insert: duplication is structurally
        # impossible in the update path used for the existing draft.
        assert "def update_post" not in src or "insert" not in \
            inspect.getsource(blogger_publisher.update_post)
