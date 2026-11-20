"""YouTube Data API v3 uploader for Lovelyn Shorts.

Contract:
- Only uploads videos tied to an AUTHORISED campaign (caller checks
  promotion_approved; this module never bypasses it).
- Idempotent: queue row's youtube_video_id unique index + explicit
  find_by_youtube_video_id check mean a repeated run can never upload twice.
- NEVER reports success unless YouTube returned a real video ID.
- Missing credentials -> returns (False, reason) and the queue row stays
  'rendered' (awaiting credentials), never failed - the owner can add the
  refresh token later and the next run uploads it.
- No retry loops: one attempt per queue row per run; failures are recorded
  with error_detail so the owner sees them on the dashboard.
- Tokens stay in env/Streamlit secrets; never logged.

Owner setup (milestone D) - Google Cloud Console:
1. Create project -> enable "YouTube Data API v3".
2. OAuth consent screen -> External -> add yourself as test user.
3. Credentials -> OAuth client ID -> Desktop app -> download JSON as
   client_secret.json (NEVER commit it; keep it out of git).
4. One-time local run:  python -m services.youtube_upload --auth
   Browser opens -> Google account -> allow (warning: unverified app ->
   Advanced -> continue; it's your own app).
   The script prints a refresh token; put it in .env / GitHub Secrets as
   YOUTUBE_REFRESH_TOKEN, plus YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET.
"""
import os

from config.settings import _get_setting

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# Module-level so tests can monkeypatch the media factory.
MediaFileUpload = None  # imported lazily in upload_short


def credentials_ready() -> bool:
    return bool(_get_setting("YOUTUBE_CLIENT_ID")
                and _get_setting("YOUTUBE_CLIENT_SECRET")
                and _get_setting("YOUTUBE_REFRESH_TOKEN"))


def missing_config() -> list:
    need = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    return [k for k in need if not _get_setting(k)]


def _build_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=_get_setting("YOUTUBE_REFRESH_TOKEN"),
        client_id=_get_setting("YOUTUBE_CLIENT_ID"),
        client_secret=_get_setting("YOUTUBE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES)
    return build(API_SERVICE_NAME, API_VERSION, credentials=creds)


def upload_short(video_path: str, title: str, description: str,
                 tags: list) -> tuple[bool, str]:
    """Resumable upload of one vertical Short. Returns (ok, video_id_or_reason).

    Privacy is the owner's YOUTUBE_VISIBILITY setting (default 'public')."""
    global MediaFileUpload
    if not credentials_ready():
        return False, "missing_config: " + ",".join(missing_config())
    if not os.path.isfile(video_path):
        return False, f"video file not found: {video_path}"
    visibility = (_get_setting("YOUTUBE_VISIBILITY") or "public").lower()
    if visibility not in ("public", "unlisted", "private"):
        visibility = "public"
    try:
        from googleapiclient.http import MediaFileUpload as _MFU
        if MediaFileUpload is None:
            MediaFileUpload = _MFU
        service = _build_service()
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:4900],
                "tags": (tags or [])[:15],
                "categoryId": "27",  # Howto & Style: education-adjacent
            },
            "status": {
                "privacyStatus": visibility,
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True,
                                mimetype="video/mp4")
        request = service.videos().insert(
            part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:  # resumable protocol; bounded by file size
            status, response = request.next_chunk()
            if status:
                print(f"upload progress: {int(status.progress() * 100)}%")
        vid = (response or {}).get("id")
        if not vid:
            return False, f"upload finished without video id: {response}"
        url = f"https://www.youtube.com/shorts/{vid}"
        return True, url
    except Exception as exc:
        # One attempt per run. No retry loop (quota + policy compliance).
        return False, f"{type(exc).__name__}: {exc}"


def _one_time_auth_flow():
    """CLI helper (python -m services.youtube_upload --auth): prints a
    refresh token for the owner to store as YOUTUBE_REFRESH_TOKEN."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret = _get_setting("YOUTUBE_CLIENT_SECRET_FILE") or "client_secret.json"
    flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
    creds = flow.run_local_server(port=0)
    print("\nAdd these to .env / GitHub Secrets:\n")
    print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}\n")


if __name__ == "__main__":
    import sys
    if "--auth" in sys.argv:
        _one_time_auth_flow()
    else:
        print(__doc__)
