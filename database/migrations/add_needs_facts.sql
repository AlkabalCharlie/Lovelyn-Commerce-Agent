-- Tiered extraction support: flag products whose extraction came back thin
-- across all tiers so the owner knows to seed facts manually.
ALTER TABLE products ADD COLUMN IF NOT EXISTS needs_facts boolean NOT NULL DEFAULT FALSE;

-- RLS on products is untouched: ADD COLUMN never changes policies.
