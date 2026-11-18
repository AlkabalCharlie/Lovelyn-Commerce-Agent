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

QUEUE_STATUSES = ("queued", "published", "skipped")
QUEUE_CHANNELS = ("youtube", "blogger", "pinterest", "community", "medium")


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
