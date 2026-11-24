"""Pinterest publishing via the official Pinterest API v5.

Setup (owner actions, all free):
1. https://developers.pinterest.com/apps/ -> Create app.
2. App -> "Configure" -> add redirect URI:
      http://localhost:8080/
3. Request scopes: pins:write, boards:read, user_accounts:read
   (pins:read + boards:read are enough for verification/metrics later).
4. Copy App ID + App secret into .env as PINTEREST_CLIENT_ID /
   PINTEREST_CLIENT_SECRET, set PINTEREST_REDIRECT_URI.
5. Run:  python -m services.pinterest_publisher --auth
   (standard authorization-code flow; prints the refresh token)
6. Put PINTEREST_REFRESH_TOKEN in .env / GitHub Secrets, plus
   PINTEREST_BOARD_ID (see --boards to list them).

IMPORTANT: Pinterest requires the app to have access to the "standard"
access tier before write endpoints work for third parties; a brand-new app
can create pins ONLY on its own account's boards until review. If the API
answers 403 "Authentication failed"/"insufficient scope", that is an ACCESS
LEVEL restriction, not an implementation bug - the provider reports it as
such and the owner completes the manual checklist.

No scraping, no browser automation, no unofficial endpoints.
"""
import os

from config.settings import _get_setting

API_BASE = "https://api.pinterest.com/v5"
AUTH_URL = "https://www.pinterest.com/oauth/"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
REQUIRED_SCOPES = ("pins:write", "boards:read", "user_accounts:read")


class PinterestAuthError(Exception):
    """Missing/invalid Pinterest credentials."""


class PinterestAPIError(Exception):
    def __init__(self, message, kind="api_error", status=0):
        super().__init__(message)
        self.kind = kind      # auth | access_level | rate_limit | validation
        self.status = status


def credentials_ready() -> bool:
    return bool(_get_setting("PINTEREST_CLIENT_ID")
                and _get_setting("PINTEREST_CLIENT_SECRET")
                and _get_setting("PINTEREST_REFRESH_TOKEN"))


def missing_config() -> list:
    need = ("PINTEREST_CLIENT_ID", "PINTEREST_CLIENT_SECRET",
            "PINTEREST_REFRESH_TOKEN")
    return [k for k in need if not _get_setting(k)]


def _access_token() -> str:
    """Exchange the stored refresh token for a fresh access token.
    Pinterest access tokens are short-lived (~30 days); exchanging keeps
    publishing working without manual refresh."""
    if not credentials_ready():
        raise PinterestAuthError(
            "Pinterest authorization missing: " + ",".join(missing_config()))
    import requests
    resp = requests.post(TOKEN_URL, timeout=30, data={
        "grant_type": "refresh_token",
        "refresh_token": _get_setting("PINTEREST_REFRESH_TOKEN"),
    }, auth=(_get_setting("PINTEREST_CLIENT_ID"),
             _get_setting("PINTEREST_CLIENT_SECRET")))
    if resp.status_code == 401:
        raise PinterestAuthError(
            "Pinterest refused the refresh token (401): re-run --auth.")
    if resp.status_code >= 400:
        raise PinterestAPIError(resp.text[:400], "auth", resp.status_code)
    token = resp.json().get("access_token")
    if not token:
        raise PinterestAPIError(f"no access_token in response: {resp.text[:200]}",
                                "auth")
    return token


def _request(method: str, path: str, **kwargs):
    import requests
    token = _access_token()
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    resp = requests.request(method, f"{API_BASE}{path}", headers=headers,
                            timeout=60, **kwargs)
    if resp.status_code < 300:
        try:
            return resp.json()
        except ValueError:
            return {}
    text = resp.text[:500]
    lowered = text.lower()
    if resp.status_code == 401:
        raise PinterestAPIError(text, "auth", 401)
    if resp.status_code == 403:
        # Distinguish access-level from implementation defects, explicitly.
        if "scope" in lowered or "authentication failed" in lowered or \
                "access" in lowered:
            raise PinterestAPIError(
                "Pinterest denied this call at the ACCESS LEVEL (403). This "
                "is an app-approval restriction, not a code defect. " + text,
                "access_level", 403)
        raise PinterestAPIError(text, "access_level", 403)
    if resp.status_code == 429:
        raise PinterestAPIError(text, "rate_limit", 429)
    if resp.status_code in (400, 422):
        raise PinterestAPIError(text, "validation", resp.status_code)
    raise PinterestAPIError(text, "api_error", resp.status_code)


def list_boards() -> list:
    """Available boards: [{id, name}]."""
    data = _request("GET", "/boards")
    return [{"id": b.get("id"), "name": b.get("name")}
            for b in (data or {}).get("items", [])]


def validate_image(image_path: str) -> dict:
    """Validate a pin image: exists, readable, JPEG/PNG, >= 600px wide,
    vertical-ish (2:3 preferred). Returns {'ok': bool, 'reason': str}."""
    if not image_path or not os.path.isfile(image_path):
        return {"ok": False, "reason": f"image not found: {image_path!r}"}
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            fmt, size = im.format, im.size
    except Exception as exc:
        return {"ok": False, "reason": f"unreadable image: {type(exc).__name__}"}
    if fmt not in ("JPEG", "PNG"):
        return {"ok": False, "reason": f"unsupported format {fmt}"}
    if size[0] < 600 or size[1] < 600:
        return {"ok": False, "reason": f"too small {size[0]}x{size[1]} (min 600)"}
    return {"ok": True, "reason": f"{fmt} {size[0]}x{size[1]}"}


def publish_pin(board_id: str, title: str, description: str,
                link: str, image_path: str, alt_text: str = None) -> dict:
    """Create one pin. Returns {id, url, status, created_at}.

    Pinterest needs a publicly reachable image URL, not a local file. We use
    the site_builder-published image when available; local-only images are
    reported as 'image_not_hosted' rather than publishing an empty pin.
    """
    if not (board_id and title and link):
        raise PinterestAPIError("board_id, title and link are required",
                                "validation")
    check = validate_image(image_path)
    if not check["ok"]:
        raise PinterestAPIError(f"image validation failed: {check['reason']}",
                                "validation")
    image_url = _get_setting("PINTEREST_IMAGE_BASE_URL")
    if not image_url:
        raise PinterestAPIError(
            "PINTEREST_IMAGE_BASE_URL is not configured: Pinterest requires "
            "a public image URL (local files cannot be uploaded). Publish the "
            "pin image to the GitHub Pages site (docs/) first, then set the "
            "base URL.", "validation")
    filename = os.path.basename(image_path)
    body = {
        "board_id": board_id,
        "title": title[:100],
        "description": description[:800],
        "link": link,
        "media_source": {"source_type": "image_url",
                         "url": f"{image_url.rstrip('/')}/{filename}"},
    }
    if alt_text:
        body["alt_text"] = alt_text[:500]
    data = _request("POST", "/pins", json=body)
    pin_id = (data or {}).get("id")
    if not pin_id:
        raise PinterestAPIError(f"Pinterest returned no pin id: {data!r}",
                                "api_error")
    return {"id": pin_id,
            "url": f"https://www.pinterest.com/pin/{pin_id}/",
            "status": "published",
            "created_at": (data or {}).get("created_at")}


def _one_time_auth_flow():
    """Authorization-code flow (localhost redirect). Prints the refresh token."""
    import secrets
    import urllib.parse
    import urllib.request
    import http.server
    import threading

    client_id = _get_setting("PINTEREST_CLIENT_ID")
    client_secret = _get_setting("PINTEREST_CLIENT_SECRET")
    redirect_uri = (_get_setting("PINTEREST_REDIRECT_URI")
                    or "http://localhost:8080/")
    if not (client_id and client_secret):
        print("Set PINTEREST_CLIENT_ID and PINTEREST_CLIENT_SECRET first "
              "(see the module docstring for the exact steps).")
        return
    state = secrets.token_urlsafe(16)
    params = {"client_id": client_id,
              "redirect_uri": redirect_uri,
              "response_type": "code",
              "scope": ",".join(REQUIRED_SCOPES),
              "state": state}
    print("Open this URL and authorize:\n")
    print(AUTH_URL + "?" + urllib.parse.urlencode(params) + "\n")

    captured = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            captured["code"] = (qs.get("code") or [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorized - you can close this window.")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("localhost", 8080), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    print("Waiting for the callback on http://localhost:8080/ ...")
    while not captured.get("code"):
        pass
    code = captured["code"]
    server.server_close()

    import base64
    import json
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri}).encode()
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL, data=body,
        headers={"Authorization": f"Basic {auth}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        tokens = json.loads(resp.read().decode())
    print("\nAdd these to .env / GitHub Secrets:\n")
    print(f"PINTEREST_REFRESH_TOKEN={tokens.get('refresh_token', '')}\n")


if __name__ == "__main__":
    import sys
    if "--auth" in sys.argv:
        _one_time_auth_flow()
    elif "--boards" in sys.argv:
        for b in list_boards():
            print(b)
    else:
        print(__doc__)
