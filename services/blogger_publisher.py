"""Blogger publishing via the official Google Blogger API v3.

Reuses the existing Google OAuth client (same Cloud project as YouTube/Gmail)
with an ADDITIONAL scope - existing scopes and refresh tokens are untouched.

Contract:
- publication state lives in the publishing_queue row (status + blog_post_id
  + publication_url). A queued row is only ever moved to 'published' after
  Blogger returns a real post id+url => retries can never double-publish.
- promotion_approved remains the sole promotion authorization; this module
  only acts on queue rows the agent already authorized.
- Blogger API errors are classified (auth / rate limit / not found / generic)
  so the caller can decide; nothing is silently swallowed.
"""
import os

from config.settings import _get_setting

BLOGGER_SCOPE = "https://www.googleapis.com/auth/blogger"
SCOPES = [BLOGGER_SCOPE]


class BloggerAuthError(Exception):
    """Missing/invalid Blogger OAuth credentials."""


class BloggerAPIError(Exception):
    """Blogger API failure, with a classification for the caller."""

    def __init__(self, message: str, kind: str = "api_error", status: int = 0):
        super().__init__(message)
        self.kind = kind          # auth | rate_limit | not_found | api_error
        self.status = status


def credentials_ready() -> bool:
    return bool(_get_setting("BLOGGER_CLIENT_ID")
                and _get_setting("BLOGGER_CLIENT_SECRET")
                and _get_setting("BLOGGER_REFRESH_TOKEN"))


def missing_config() -> list:
    need = ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET",
            "BLOGGER_REFRESH_TOKEN")
    return [k for k in need if not _get_setting(k)]


def _build_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=_get_setting("BLOGGER_REFRESH_TOKEN"),
        client_id=_get_setting("BLOGGER_CLIENT_ID"),
        client_secret=_get_setting("BLOGGER_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES)
    return build("blogger", "v3", credentials=creds)


def _classify(exc: Exception) -> BloggerAPIError:
    if isinstance(exc, BloggerAPIError):
        return exc
    text = f"{type(exc).__name__}: {exc}".lower()
    status = 0
    try:
        resp = getattr(exc, "resp", None)
        status = int(getattr(resp, "status", 0) or 0)
    except Exception:
        status = 0
    if "invalid_grant" in text or "unauthorized" in text or status == 401:
        return BloggerAPIError(str(exc), "auth", status)
    if status == 403 and ("quota" in text or "rate" in text):
        return BloggerAPIError(str(exc), "rate_limit", status)
    if status == 404:
        return BloggerAPIError(str(exc), "not_found", status)
    if status == 429:
        return BloggerAPIError(str(exc), "rate_limit", status)
    return BloggerAPIError(str(exc), "api_error", status)


def list_blogs() -> list:
    """Discover the user's Blogger blogs: [{id, name, url}]."""
    if not credentials_ready():
        raise BloggerAuthError("Blogger authorization missing: "
                               + ",".join(missing_config()))
    try:
        service = _build_service()
        result = service.blogs().listByUser(userId="self").execute()
    except Exception as exc:
        raise _classify(exc) from exc
    return [{"id": b.get("id"), "name": b.get("name"), "url": b.get("url")}
            for b in (result or {}).get("items", [])]


def publish_post(blog_id: str, title: str, html_body: str, labels=None,
                 is_draft: bool = True) -> dict:
    """Create a post. is_draft=True creates a DRAFT (owner publishes by hand);
    is_draft=False publishes immediately.

    Returns: {id, url, status, published_at}
    """
    if not credentials_ready():
        raise BloggerAuthError("Blogger authorization missing: "
                               + ",".join(missing_config()))
    if not (blog_id and title and html_body):
        raise BloggerAPIError("blog_id, title and html_body are required",
                              "validation")
    body = {"kind": "blogger#post",
            "title": title[:150],
            "content": html_body,
            "labels": list(labels or [])[:20]}
    try:
        service = _build_service()
        result = service.posts().insert(
            blogId=blog_id, body=body, isDraft=bool(is_draft)).execute()
    except Exception as exc:
        raise _classify(exc) from exc
    post_id = (result or {}).get("id")
    if not post_id:
        raise BloggerAPIError(f"Blogger returned no post id: {result!r}",
                              "api_error")
    return {"id": post_id,
            "url": (result or {}).get("url") or "",
            "status": (result or {}).get("status")
                      or ("draft" if is_draft else "live"),
            "published_at": (result or {}).get("published")}


def markdown_to_html(markdown_text: str) -> str:
    """Minimal, dependency-free markdown -> HTML for Blogger bodies.
    Handles paragraphs, **bold**, *italic*, bullet lists and links so the
    existing article packages render as real HTML articles."""
    import html as _html
    import re

    def inline(text):
        text = _html.escape(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
                      r"<em>\1</em>", text)
        text = re.sub(r"\[(.+?)\]\((https?://[^\)]+)\)", r'<a href="\2">\1</a>',
                      text)
        return text

    blocks, current_list = [], []
    for raw in (markdown_text or "").split("\n"):
        line = raw.rstrip()
        if line.startswith(("- ", "* ")):
            current_list.append(line[2:].strip())
            continue
        if current_list:
            blocks.append("<ul>" + "".join(
                f"<li>{inline(i)}</li>" for i in current_list) + "</ul>")
            current_list = []
        if not line.strip():
            continue
        if line.startswith("### "):
            blocks.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            blocks.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            blocks.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("*") and line.endswith("*") and len(line) > 2:
            blocks.append(f"<p><em>{inline(line.strip('*'))}</em></p>")
        else:
            blocks.append(f"<p>{inline(line)}</p>")
    if current_list:
        blocks.append("<ul>" + "".join(
            f"<li>{inline(i)}</li>" for i in current_list) + "</ul>")
    return "\n".join(blocks)


def _one_time_auth_flow():
    """python -m services.blogger_publisher --auth
    Requests ONLY the blogger scope; prints the refresh token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret = (_get_setting("BLOGGER_CLIENT_SECRET_FILE")
                     or _get_setting("GMAIL_CLIENT_SECRET_FILE")
                     or "client_secret.json")
    flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
    creds = flow.run_local_server(port=0)
    print("\nAdd these to .env / GitHub Secrets:\n")
    print(f"BLOGGER_CLIENT_ID={creds.client_id}")
    print(f"BLOGGER_CLIENT_SECRET={creds.client_secret}")
    print(f"BLOGGER_REFRESH_TOKEN={creds.refresh_token}\n")


if __name__ == "__main__":
    import sys
    if "--auth" in sys.argv:
        _one_time_auth_flow()
    else:
        print(__doc__)
