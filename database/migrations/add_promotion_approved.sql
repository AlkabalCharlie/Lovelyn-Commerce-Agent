-- Promotion authorization: separate owner-controlled permission to publish
-- and distribute a campaign, independent of content approval (status).
--
-- Conventions mirror add_medium_pushed.sql: idempotent ADD COLUMN IF NOT
-- EXISTS, no status/content/attribution changes, RLS untouched (ALTER ADD
-- COLUMN never changes policies).
--
-- NOTE: this migration was ALREADY APPLIED to the production database by the
-- owner before the application code shipped; this file records the exact SQL
-- for reproducibility and for fresh environments.

-- 1) Permission column. New campaigns default to unauthorized.
ALTER TABLE campaigns
    ADD COLUMN IF NOT EXISTS promotion_approved boolean NOT NULL DEFAULT FALSE;

-- 2) Authorize ONLY the four verified launch campaigns. Idempotent by ID;
--    if an ID does not exist the UPDATE simply matches zero rows for it.
UPDATE campaigns SET promotion_approved = TRUE WHERE id = 'b8d56c20-c801-4c97-ac8f-936bb5c36cba';  -- TradingView
UPDATE campaigns SET promotion_approved = TRUE WHERE id = '495a7cc2-6861-4818-b2c2-1729bf6955cc';  -- Click Action AI
UPDATE campaigns SET promotion_approved = TRUE WHERE id = '66d125ce-0523-492b-9679-3bd06d75e1be';  -- Be Free from Debt
UPDATE campaigns SET promotion_approved = TRUE WHERE id = '2b6fb996-c048-435b-82d8-9a64d196a1b8';  -- HTML5 Games

-- 3) Explicitly keep held campaigns unauthorized (defense in depth; they are
--    already FALSE via the column default). Run only if the rows exist.
UPDATE campaigns SET promotion_approved = FALSE WHERE id IN (
    '36f0f37b-2e81-49c7-874b-285317abee7c',   -- Etsy held 1
    'b3a66faa-77bf-45ba-9630-8cb9a66cf373',   -- Etsy held 2
    'f74e3f29-6693-40e4-afc3-e0408aea5689',   -- Etsy held 3
    '90edc596-8575-4328-8cae-ac639d97fc62'    -- Gumroad Discover (held)
) AND promotion_approved = TRUE;

-- 4) Post-conditions (manual verification queries; not part of the update):
--   SELECT count(*) FROM campaigns WHERE promotion_approved;            -- expect 4
--   SELECT id, headline, promotion_approved FROM campaigns
--     WHERE id IN ('b8d56c20-...','495a7cc2-...','66d125ce-...','2b6fb996-...',
--                  '36f0f37b-...','b3a66faa-...','f74e3f29-...','90edc596-...');
-- Report any missing IDs rather than assuming authorization succeeded.
