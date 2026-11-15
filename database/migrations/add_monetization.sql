-- Monetization wiring: affiliate links + owned product checkout.
-- Run once in the Supabase SQL editor (or via psql).

-- 1) Real tracked affiliate link per product (NULL until the owner pastes one).
ALTER TABLE products ADD COLUMN IF NOT EXISTS affiliate_url text;

-- 2) Owned-product stream settings are env-based, nothing needed here.
-- RLS note: products already have RLS; nullable column additions do not
-- change policies.
