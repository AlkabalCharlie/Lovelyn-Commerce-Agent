-- P1-8: record where each campaign was actually published, so the
-- Publication -> Click -> Conversion attribution chain can close.
-- The agent writes the URL returned by the publisher API on success.
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS devto_publication_url text;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS medium_publication_url text;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS bluesky_publication_url text;
