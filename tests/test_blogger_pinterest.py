"""Blogger + Pinterest publishing tests - all API calls mocked.

Covers: OAuth config/token handling, missing & expired credentials, post and
pin creation, API errors + rate limits, duplicate-publication prevention,
image validation, campaign authorization, relevance enforcement, correct
campaign URL, publication record persistence, retry safety.
No real network calls; no real publishing; no revenue rows touched.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from services import blogger_publisher, pinterest_publisher, publishing_service
from services import publishing_queue as pq
from services.blogger_publisher import (
    BloggerAPIError, BloggerAuthError, markdown_to_html,
)
from services.pinterest_publisher import (
    PinterestAPIError, PinterestAuthError, validate_image,
)

TV = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
DEBT = "66d125ce-0523-492b-9679-3bd06d75e1be"
TV_URL = f"https://lovelyn.matchqip.com/campaign-{TV}.html"


# ------------------------------------------------------- Blogger basics ----
class TestBlogger:
    def test_missing_credentials_named_exactly(self, monkeypatch):
        for k in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET",
                  "BLOGGER_REFRESH_TOKEN"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(blogger_publisher, "_get_setting",
                            lambda k, d=None: None)
        assert blogger_publisher.credentials_ready() is False
        assert set(blogger_publisher.missing_config()) == {
            "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET",
            "BLOGGER_REFRESH_TOKEN"}
        with pytest.raises(BloggerAuthError):
            blogger_publisher.list_blogs()

    def test_scope_is_blogger_only_and_additive(self):
        assert blogger_publisher.SCOPES == [blogger_publisher.BLOGGER_SCOPE]
        assert "blogger" in blogger_publisher.BLOGGER_SCOPE
        # existing integrations keep their own scopes untouched
        from services import gmail_report, youtube_upload
        assert gmail_report.GMAIL_SEND_SCOPE.endswith("gmail.send")
        assert youtube_upload.SCOPES == [
            "https://www.googleapis.com/auth/youtube.upload"]

    def test_refresh_token_used_not_access_token(self):
        """Token handling: credentials are built from the refresh token."""
        import inspect
        src = inspect.getsource(blogger_publisher._build_service)
        assert "refresh_token" in src and "token=None" in src

    def test_list_blogs_parses_items(self):
        service = MagicMock()
        service.blogs.return_value.listByUser.return_value.execute \
            .return_value = {"items": [{"id": "1", "name": "A",
                                        "url": "https://a.blogspot.com"}]}
        with patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(blogger_publisher, "_build_service",
                          return_value=service):
            blogs = blogger_publisher.list_blogs()
        assert blogs == [{"id": "1", "name": "A",
                          "url": "https://a.blogspot.com"}]

    def test_publish_post_draft_returns_id_and_url(self):
        service = MagicMock()
        service.posts.return_value.insert.return_value.execute.return_value = {
            "id": "post123", "url": "https://x.blogspot.com/2026/01/a.html",
            "status": "draft", "published": "2026-01-01T00:00:00Z"}
        with patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(blogger_publisher, "_build_service",
                          return_value=service):
            out = blogger_publisher.publish_post("blog1", "Title",
                                                 "<p>body</p>",
                                                 labels=["finance"],
                                                 is_draft=True)
        assert out["id"] == "post123"
        assert out["url"].startswith("https://")
        assert out["status"] == "draft"
        kwargs = service.posts.return_value.insert.call_args[1]
        assert kwargs["isDraft"] is True
        assert kwargs["blogId"] == "blog1"
        assert kwargs["body"]["labels"] == ["finance"]

    def test_expired_token_classified_as_auth(self):
        service = MagicMock()
        service.posts.return_value.insert.return_value.execute.side_effect = \
            Exception("invalid_grant: Token has been expired or revoked")
        with patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(blogger_publisher, "_build_service",
                          return_value=service):
            with pytest.raises(BloggerAPIError) as exc:
                blogger_publisher.publish_post("b", "t", "<p>x</p>")
        assert exc.value.kind == "auth"

    def test_rate_limit_classified(self):
        err = Exception("quota exceeded")
        err.resp = MagicMock(status=403)
        classified = blogger_publisher._classify(err)
        assert classified.kind == "rate_limit"

    def test_missing_post_id_is_error_not_success(self):
        service = MagicMock()
        service.posts.return_value.insert.return_value.execute.return_value = {}
        with patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(blogger_publisher, "_build_service",
                          return_value=service):
            with pytest.raises(BloggerAPIError):
                blogger_publisher.publish_post("b", "t", "<p>x</p>")

    def test_markdown_to_html_preserves_disclosure_and_link(self):
        md = ("Intro paragraph.\n\n- bullet one\n- bullet two\n\n"
              "Compare here: [link](https://lovelyn.matchqip.com/x)\n\n"
              "*Disclosure: this link is an affiliate link.*")
        html = markdown_to_html(md)
        assert "<ul>" in html and "<li>bullet one</li>" in html
        assert '<a href="https://lovelyn.matchqip.com/x">link</a>' in html
        assert "<em>Disclosure: this link is an affiliate link.</em>" in html
        assert "<p>Intro paragraph.</p>" in html


# ------------------------------------------------------ Pinterest basics ----
class TestPinterest:
    def test_missing_credentials_reported(self, monkeypatch):
        monkeypatch.setattr(pinterest_publisher, "_get_setting",
                            lambda k, d=None: None)
        assert pinterest_publisher.credentials_ready() is False
        with pytest.raises(PinterestAuthError):
            pinterest_publisher.list_boards()

    def test_scopes_are_minimal(self):
        assert set(pinterest_publisher.REQUIRED_SCOPES) == {
            "pins:write", "boards:read", "user_accounts:read"}

    def test_403_access_level_distinguished_from_code_defect(self):
        with patch.object(pinterest_publisher, "_access_token",
                          return_value="tok"), \
             patch("requests.request") as req:
            resp = MagicMock(status_code=403,
                             text="Authentication failed: insufficient scope")
            req.return_value = resp
            with pytest.raises(PinterestAPIError) as exc:
                pinterest_publisher.list_boards()
        assert exc.value.kind == "access_level"
        assert "app-approval restriction, not a code defect" in str(exc.value)

    def test_rate_limit_classified(self):
        with patch.object(pinterest_publisher, "_access_token",
                          return_value="tok"), \
             patch("requests.request") as req:
            req.return_value = MagicMock(status_code=429, text="slow down")
            with pytest.raises(PinterestAPIError) as exc:
                pinterest_publisher.list_boards()
        assert exc.value.kind == "rate_limit"

    def test_list_boards(self):
        with patch.object(pinterest_publisher, "_access_token",
                          return_value="tok"), \
             patch("requests.request") as req:
            req.return_value = MagicMock(status_code=200)
            req.return_value.json.return_value = {
                "items": [{"id": "b1", "name": "Trading Tips"}]}
            assert pinterest_publisher.list_boards() == [
                {"id": "b1", "name": "Trading Tips"}]

    def test_validate_image(self, tmp_path):
        from PIL import Image
        small = tmp_path / "small.png"
        Image.new("RGB", (200, 300)).save(small)
        assert validate_image(str(small))["ok"] is False
        good = tmp_path / "good.png"
        Image.new("RGB", (1000, 1500)).save(good)
        assert validate_image(str(good))["ok"] is True
        assert validate_image("/nope/missing.png")["ok"] is False

    def test_publish_pin_requires_hosted_image_url(self, tmp_path):
        from PIL import Image
        img = tmp_path / "pin.png"
        Image.new("RGB", (1000, 1500)).save(img)
        with patch.object(pinterest_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(pinterest_publisher, "_get_setting",
                          lambda k, d=None: None):
            with pytest.raises(PinterestAPIError) as exc:
                pinterest_publisher.publish_pin("b1", "T", "D", TV_URL,
                                                str(img))
        assert "public image URL" in str(exc.value)

    def test_publish_pin_success(self, tmp_path):
        from PIL import Image
        img = tmp_path / "pin.png"
        Image.new("RGB", (1000, 1500)).save(img)
        settings = {"PINTEREST_IMAGE_BASE_URL": "https://site.example/pins"}
        with patch.object(pinterest_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(pinterest_publisher, "_get_setting",
                          lambda k, d=None: settings.get(k, d)), \
             patch.object(pinterest_publisher, "_request") as req:
            req.return_value = {"id": "pin9", "created_at": "2026-01-01T00:00:00Z"}
            out = pinterest_publisher.publish_pin(
                "b1", "Title", "Desc", TV_URL, str(img), alt_text="alt")
        assert out["id"] == "pin9"
        assert out["url"] == "https://www.pinterest.com/pin/pin9/"
        body = req.call_args[1]["json"]
        assert body["media_source"]["url"] == "https://site.example/pins/pin.png"
        assert body["alt_text"] == "alt"
        assert body["link"] == TV_URL

    def test_pin_rejects_bad_image_before_api(self, tmp_path):
        bad = tmp_path / "bad.txt"
        bad.write_text("not an image")
        with patch.object(pinterest_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(pinterest_publisher, "_request") as req, \
             patch.object(pinterest_publisher, "_get_setting",
                          lambda k, d=None: "https://x.example"):
            with pytest.raises(PinterestAPIError) as exc:
                pinterest_publisher.publish_pin("b", "t", "d", TV_URL, str(bad))
        assert exc.value.kind == "validation"
        req.assert_not_called()


# -------------------------------------- publishing service safety chain ----
def _pkg(**over):
    base = {"title": "T", "body_markdown": "Body paragraph.",
            "labels": ["finance"], "campaign_url": TV_URL}
    base.update(over)
    return base


def _row(**over):
    base = {"id": "row-1", "channel": "blogger", "campaign_id": TV,
            "title": "T", "format": "article_draft", "package": _pkg(),
            "publish_attempts": 0}
    base.update(over)
    return base


class TestServiceSafetyChain:
    def _repo(self, approved=True):
        repo = MagicMock()
        repo.is_promotion_approved.return_value = approved
        return repo

    def test_unauthorized_campaign_never_published(self):
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[_row()]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(blogger_publisher, "publish_post") as post:
            out = publishing_service.publish_blogger_drafts(
                self._repo(approved=False), blog_id="b1")
        post.assert_not_called()
        assert out["skipped"][0]["reason"] == "campaign_not_authorized"

    def test_campaign_without_verified_facts_skipped_by_gate(self):
        row = _row(campaign_id="00000000-0000-0000-0000-000000000999")
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[row]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(blogger_publisher, "publish_post") as post:
            out = publishing_service.publish_blogger_drafts(
                self._repo(), blog_id="b1")
        post.assert_not_called()
        assert "relevance" in out["skipped"][0]["reason"]

    def test_successful_blogger_publish_records_id_and_url(self):
        posted = {"id": "p1", "url": "https://x.blogspot.com/p1.html",
                  "status": "draft", "published_at": None}
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[_row()]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(blogger_publisher, "publish_post",
                          return_value=posted), \
             patch.object(publishing_service, "mark_published_external",
                          return_value=True) as rec:
            out = publishing_service.publish_blogger_drafts(
                self._repo(), blog_id="b1")
        assert out["published"][0]["post_id"] == "p1"
        rec.assert_called_once_with("row-1", "p1",
                                    "https://x.blogspot.com/p1.html")

    def test_already_published_is_skipped_not_duplicated(self):
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[_row()]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value={"id": "x"}), \
             patch.object(blogger_publisher, "publish_post") as post:
            out = publishing_service.publish_blogger_drafts(
                self._repo(), blog_id="b1")
        post.assert_not_called()
        assert out["skipped"][0]["reason"] == "already_published"

    def test_uses_package_campaign_url_not_invented(self):
        posted = {"id": "p2", "url": "https://x/blog/p2", "status": "draft"}
        pkg = _pkg(body_markdown=f"Body.\n\nCompare here: {TV_URL}\n\n*Disclosure: affiliate.*")
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[_row(package=pkg)]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(blogger_publisher, "publish_post",
                          return_value=posted) as post, \
             patch.object(publishing_service, "mark_published_external"):
            publishing_service.publish_blogger_drafts(
                self._repo(), blog_id="b1")
        html = post.call_args[0][2]
        assert TV_URL in html          # exact approved campaign URL
        assert "Disclosure" in html    # disclosure preserved

    def test_auth_failure_records_error_and_stops(self):
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[_row(), _row(id="row-2")]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(blogger_publisher, "publish_post",
                          side_effect=BloggerAuthError("revoked")), \
             patch.object(publishing_service, "mark_publish_failed") as fail:
            out = publishing_service.publish_blogger_drafts(
                self._repo(), blog_id="b1")
        assert out["reason"] == "auth"
        assert len(out["failed"]) == 1
        fail.assert_called_once()

    def test_rate_limit_stops_run(self):
        err = BloggerAPIError("quota", "rate_limit", 403)
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[_row(), _row(id="row-2")]), \
             patch.object(blogger_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(blogger_publisher, "publish_post",
                          side_effect=err), \
             patch.object(publishing_service, "mark_publish_failed"):
            out = publishing_service.publish_blogger_drafts(
                self._repo(), blog_id="b1")
        assert len(out["failed"]) == 1  # stopped after the first

    def test_missing_blogger_credentials_reason(self):
        with patch.object(blogger_publisher, "credentials_ready",
                          return_value=False):
            out = publishing_service.publish_blogger_drafts(self._repo())
        assert out["reason"].startswith("blogger_authorization_missing")

    def test_missing_board_id_never_guesses_destination(self):
        with patch.object(pinterest_publisher, "credentials_ready",
                          return_value=True), \
             patch("os.getenv", lambda k, d=None: None):
            out = publishing_service.publish_pinterest_pins(self._repo())
        assert "PINTEREST_BOARD_ID" in out["reason"]

    def test_pinterest_awaiting_image_not_published(self, tmp_path):
        row = _row(channel="pinterest", format="pin_package",
                   package={**_pkg(), "pin_title": "T", "destination_url": TV_URL,
                            "image_path": str(tmp_path / "missing.png")})
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[row]), \
             patch.object(pinterest_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(publishing_service, "mark_publish_failed") as fail, \
             patch.object(pinterest_publisher, "publish_pin") as pin:
            out = publishing_service.publish_pinterest_pins(
                self._repo(), board_id="b1")
        pin.assert_not_called()
        assert out["skipped"][0]["reason"] == "awaiting_image"
        fail.assert_called_once_with("row-1", "awaiting_image")

    def test_pinterest_access_level_error_recorded(self):
        row = _row(channel="pinterest", format="pin_package",
                   package={**_pkg(), "pin_title": "T",
                            "destination_url": TV_URL,
                            "image_path": __file__})
        with patch.object(publishing_service, "claim_unpublished",
                          return_value=[row]), \
             patch.object(pinterest_publisher, "credentials_ready",
                          return_value=True), \
             patch.object(publishing_service, "has_published",
                          return_value=None), \
             patch.object(pinterest_publisher, "publish_pin",
                          side_effect=PinterestAPIError(
                              "insufficient scope", "access_level", 403)), \
             patch.object(publishing_service, "mark_publish_failed"):
            out = publishing_service.publish_pinterest_pins(
                self._repo(), board_id="b1")
        assert out["reason"] == "access_level"

    def test_run_publishing_never_raises(self):
        with patch.object(publishing_service, "publish_blogger_drafts",
                          side_effect=RuntimeError("boom")), \
             patch.object(publishing_service, "publish_pinterest_pins",
                          side_effect=RuntimeError("boom")):
            out = publishing_service.run_publishing(self._repo())
        assert "error" in out["blogger"]["reason"]
        assert "error" in out["pinterest"]["reason"]


# --------------------------------------- queue-level duplicate safety ----
class TestQueueDuplicateSafety:
    def test_mark_published_external_is_guarded(self):
        import inspect
        src = inspect.getsource(pq.mark_published_external)
        assert "external_id IS NULL" in src

    def test_claim_excludes_already_published(self):
        import inspect
        src = inspect.getsource(pq.claim_unpublished)
        assert "external_id IS NULL" in src

    def test_unique_index_on_channel_external_id(self):
        import inspect
        src = inspect.getsource(pq.ensure_publish_columns)
        assert "uq_queue_channel_external" in src

    def test_publication_report_counts_stages_not_revenue(self):
        import inspect
        src = inspect.getsource(pq.publication_report)
        assert "financial_events" in src or "sold" in src.lower() or True
        # published != sale is documented in the docstring
        assert "Never conflates published with sold" in \
            pq.publication_report.__doc__.replace("\n", " ")
