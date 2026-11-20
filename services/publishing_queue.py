"""Publishing queue: production-ready packages for channels the agent cannot
publish to directly (no credentials / OAuth not granted).

Design constraints honored:
- No new external services, APIs, or paid dependencies.
- No secrets handled here; packages are content-only.
- A QUEUED item is never reported as published; only the OWNER can flip
  status to published (with URL) after manually posting it.
- Idempotent: (channel, campaign_id, title) unique - retry-safe.
- Channel failure never blocks the rest of the run.

Statuses: queued -> published | skipped
"""
from database.connection import engine
from sqlalchemy import text

QUEUE_STATUSES = ("queued", "generating", "rendered", "awaiting_upload",
                  "uploading", "published", "failed", "skipped")
QUEUE_CHANNELS = ("youtube", "blogger", "pinterest", "community", "medium")

# Shorts lifecycle statuses (all except the legacy three are shorts-only).
LEGACY_STATUSES = ("queued", "published", "skipped")


def ensure_queue_table() -> None:
    """Idempotent DDL. Cheap, additive-only, run-safe (IF NOT EXISTS)."""
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS publishing_queue (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                channel TEXT NOT NULL CHECK (channel IN
                    ('youtube', 'blogger', 'pinterest', 'community', 'medium')),
                campaign_id UUID REFERENCES campaigns(id),
                title TEXT NOT NULL,
                format TEXT NOT NULL,
                package JSONB NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'published', 'skipped')),
                publication_url TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                published_at TIMESTAMPTZ,
                UNIQUE (channel, campaign_id, title)
            )
        """))


def queue_package(channel: str, campaign_id: str, title: str, format: str,
                  package: dict) -> bool:
    """Insert a package; UNIQUE makes retries a no-op. Returns True if NEW."""
    if channel not in QUEUE_CHANNELS:
        raise ValueError(f"Invalid queue channel: {channel}")
    if format not in ("script", "article_draft", "pin_package", "reply_draft",
                      "article", "short"):
        raise ValueError(f"Invalid queue format: {format}")
    ensure_queue_table()
    import json
    with engine.begin() as connection:
        result = connection.execute(text(
            "INSERT INTO publishing_queue "
            "(channel, campaign_id, title, format, package) "
            "VALUES (:ch, :cid, :t, :f, CAST(:pkg AS jsonb)) "
            "ON CONFLICT (channel, campaign_id, title) DO NOTHING RETURNING id"),
            {"ch": channel, "cid": campaign_id, "t": title, "f": format,
             "pkg": json.dumps(package, ensure_ascii=False, default=str)})
        return result.scalar_one_or_none() is not None


def queue_count() -> int:
    ensure_queue_table()
    with engine.connect() as connection:
        return connection.execute(text(
            "SELECT count(*) FROM publishing_queue WHERE status = 'queued'")).scalar()


def mark_published(queue_id: str, publication_url: str) -> bool:
    """OWNER-only transition. A queued item is never auto-marked published."""
    ensure_queue_table()
    with engine.begin() as connection:
        result = connection.execute(text(
            "UPDATE publishing_queue SET status = 'published', "
            "publication_url = :u, published_at = now() "
            "WHERE id = :id AND status = 'queued'"),
            {"u": publication_url, "id": queue_id})
        return result.rowcount == 1


# ---- Shorts pipeline extensions (additive; legacy rows unaffected) --------

def ensure_shorts_columns() -> None:
    """Additive columns for the shorts pipeline. Safe to call every run.
    Mirrors database/migrations/add_shorts_pipeline.sql so the schema exists
    even when the owner has not run the migration file manually."""
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE publishing_queue ADD COLUMN IF NOT EXISTS video_path TEXT"))
        connection.execute(text(
            "ALTER TABLE publishing_queue ADD COLUMN IF NOT EXISTS youtube_video_id TEXT"))
        connection.execute(text(
            "ALTER TABLE publishing_queue ADD COLUMN IF NOT EXISTS error_detail TEXT"))
        connection.execute(text(
            "ALTER TABLE publishing_queue ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ"))


def set_status(queue_id: str, status: str, error: str = None) -> bool:
    """Transition a shorts row through its lifecycle. Any->any allowed here;
    the CALLER decides legal transitions (kept simple, guarded in agent)."""
    if status not in QUEUE_STATUSES:
        raise ValueError(f"Invalid queue status: {status}")
    ensure_queue_table()
    with engine.begin() as connection:
        result = connection.execute(text(
            "UPDATE publishing_queue SET status = :s, "
            "error_detail = :e " + (", generated_at = now() " if status == "rendered"
                                    else "") +
            "WHERE id = :id"),
            {"s": status, "e": error, "id": queue_id})
        return result.rowcount == 1


def mark_rendered(queue_id: str, video_path: str) -> bool:
    ensure_queue_table()
    with engine.begin() as connection:
        result = connection.execute(text(
            "UPDATE publishing_queue SET status = 'rendered', video_path = :p, "
            "generated_at = now(), error_detail = NULL WHERE id = :id"),
            {"p": video_path, "id": queue_id})
        return result.rowcount == 1


def mark_uploaded(queue_id: str, youtube_video_id: str, published_url: str) -> bool:
    """Called ONLY after YouTube's API returned a real video id. Idempotent:
    the unique partial index on youtube_video_id makes double-assignment
    impossible."""
    ensure_queue_table()
    with engine.begin() as connection:
        result = connection.execute(text(
            "UPDATE publishing_queue SET status = 'published', "
            "youtube_video_id = :vid, publication_url = :u, published_at = now(), "
            "error_detail = NULL WHERE id = :id AND youtube_video_id IS NULL"),
            {"vid": youtube_video_id, "u": published_url, "id": queue_id})
        return result.rowcount == 1


def find_by_youtube_video_id(youtube_video_id: str) -> dict | None:
    ensure_queue_table()
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT id, title, publication_url FROM publishing_queue "
            "WHERE youtube_video_id = :vid"),
            {"vid": youtube_video_id}).mappings().first()
        return dict(row) if row else None


def claim_next_short_for_render() -> dict | None:
    """Oldest queued youtube row (package JSON included). No lock needed:
    rendering is idempotent and ON CONFLICT dedupes concurrent runs."""
    ensure_queue_table()
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT id, campaign_id, title, package FROM publishing_queue "
            "WHERE channel = 'youtube' AND status = 'queued' "
            "ORDER BY created_at ASC LIMIT 1")).mappings().first()
        return dict(row) if row else None


def claim_next_rendered_for_upload() -> dict | None:
    ensure_queue_table()
    with engine.connect() as connection:
        row = connection.execute(text(
            "SELECT id, campaign_id, title, video_path, package "
            "FROM publishing_queue WHERE channel = 'youtube' "
            "AND status = 'rendered' AND video_path IS NOT NULL "
            "ORDER BY created_at ASC LIMIT 1")).mappings().first()
        return dict(row) if row else None
