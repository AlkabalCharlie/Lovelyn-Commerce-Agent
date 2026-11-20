-- YouTube Shorts pipeline: extend publishing_queue with render/upload states
-- and persisted media fields. Additive only; existing statuses untouched.
-- Backward compatible: old rows read as status 'queued' / format 'script'.

ALTER TABLE publishing_queue ADD COLUMN IF NOT EXISTS video_path TEXT;
ALTER TABLE publishing_queue ADD COLUMN IF NOT EXISTS youtube_video_id TEXT;
ALTER TABLE publishing_queue ADD COLUMN IF NOT EXISTS error_detail TEXT;
ALTER TABLE publishing_queue ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ;

-- Status lifecycle for shorts:
-- queued -> generating -> rendered -> awaiting_upload -> uploading -> published
-- plus failed / skipped. Keep legacy values valid.
ALTER TABLE publishing_queue DROP CONSTRAINT IF EXISTS publishing_queue_status_check;
ALTER TABLE publishing_queue ADD CONSTRAINT publishing_queue_status_check
    CHECK (status IN ('queued', 'generating', 'rendered', 'awaiting_upload',
                      'uploading', 'published', 'failed', 'skipped'));

-- Idempotency: a YouTube video id must never be assigned to two queue rows.
CREATE UNIQUE INDEX IF NOT EXISTS publishing_queue_yt_video_id_uidx
    ON publishing_queue (youtube_video_id) WHERE youtube_video_id IS NOT NULL;
