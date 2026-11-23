"""Gmail report sender - official Gmail API with OAuth 2.0.

Contract (per spec section 9):
- Scope is EXPLICITLY https://www.googleapis.com/auth/gmail.send. Existing
  YouTube refresh tokens carry youtube.upload ONLY; this module never
  assumes they grant Gmail. Each integration is refreshed independently.
- Sends ONLY to the configured recipient (default chuka.cokafor@gmail.com).
  No third-party recipients, ever.
- Tokens/secrets stay in env / Streamlit secrets via config.settings; never
  logged, never committed.
- Missing or expired authorization returns (False, reason) - a failed send
  never throws into the daily grind.
"""
import base64
from email.message import EmailMessage

from config.settings import _get_setting

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
DEFAULT_RECIPIENT = "chuka.cokafor@gmail.com"


def credentials_ready() -> bool:
    return bool(_get_setting("GMAIL_CLIENT_ID")
                and _get_setting("GMAIL_CLIENT_SECRET")
                and _get_setting("GMAIL_REFRESH_TOKEN"))


def missing_config() -> list:
    need = ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")
    return [k for k in need if not _get_setting(k)]


def _build_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=_get_setting("GMAIL_REFRESH_TOKEN"),
        client_id=_get_setting("GMAIL_CLIENT_ID"),
        client_secret=_get_setting("GMAIL_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=[GMAIL_SEND_SCOPE])
    return build("gmail", "v1", credentials=creds)


def send_report(subject: str, body_text: str,
                recipient: str = None) -> tuple:
    """Send one plain-text email. Returns (ok, message_id_or_reason).

    Recipient is pinned to the configured REPORT_RECIPIENT (default
    chuka.cokafor@gmail.com); a caller-supplied recipient that differs is
    IGNORED - research findings never go to third parties."""
    pinned = _get_setting("REPORT_RECIPIENT") or DEFAULT_RECIPIENT
    if not credentials_ready():
        return False, ("gmail_authorization_missing: "
                       + ",".join(missing_config()))
    try:
        message = EmailMessage()
        message["To"] = pinned
        message["Subject"] = subject[:200]
        message.set_content(body_text)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        service = _build_service()
        sent = service.users().messages().send(
            userId="me", body={"raw": raw}).execute()
        msg_id = (sent or {}).get("id")
        if not msg_id:
            return False, f"send finished without message id: {sent}"
        return True, msg_id
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _one_time_auth_flow():
    """CLI helper: python -m services.gmail_report --auth
    Prints the refresh token for the owner to store as GMAIL_REFRESH_TOKEN.
    Requests ONLY gmail.send - YouTube access is untouched."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret = _get_setting("GMAIL_CLIENT_SECRET_FILE") or "client_secret.json"
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret, [GMAIL_SEND_SCOPE])
    creds = flow.run_local_server(port=0)
    print("\nAdd these to .env / GitHub Secrets:\n")
    print(f"GMAIL_CLIENT_ID={creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET={creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}\n")


if __name__ == "__main__":
    import sys
    if "--auth" in sys.argv:
        _one_time_auth_flow()
    else:
        print(__doc__)
