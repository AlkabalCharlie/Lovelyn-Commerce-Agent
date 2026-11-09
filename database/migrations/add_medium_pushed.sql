-- Medium distribution flag on campaigns (mirrors devto_pushed / bluesky_pushed).
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS medium_pushed boolean NOT NULL DEFAULT FALSE;

-- RLS on campaigns is untouched: ALTER ADD COLUMN never changes policies.
