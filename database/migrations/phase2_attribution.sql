-- PHASE 2 migration (run once in Supabase SQL editor, AFTER add_monetization.sql)
-- Adds campaign/product attribution, net-profit fields, webhook verification
-- status, and a companion rpc. Additive only: no existing column changes,
-- no RLS policy changes (new nullable columns inherit existing policies).

-- 1) Attribution + net-profit fields on financial_events.
--    tx_id/source_type/external_id/currency already exist from earlier migrations.
ALTER TABLE financial_events ADD COLUMN IF NOT EXISTS campaign_id uuid;
ALTER TABLE financial_events ADD COLUMN IF NOT EXISTS product_id uuid;
ALTER TABLE financial_events ADD COLUMN IF NOT EXISTS fees_cents integer;
ALTER TABLE financial_events ADD COLUMN IF NOT EXISTS cost_cents integer;
ALTER TABLE financial_events ADD COLUMN IF NOT EXISTS status text
    DEFAULT 'verified'
    CHECK (status IN ('verified', 'pending', 'reversed'));

-- Money-path reporting joins (read speed; safe additive indexes).
CREATE INDEX IF NOT EXISTS ix_financial_events_campaign
    ON financial_events (campaign_id) WHERE campaign_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_financial_events_product
    ON financial_events (product_id) WHERE product_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_financial_events_status
    ON financial_events (status);

-- Refund reconciliation (P0-5 companion): a refund row carries the amount it
-- reverses here, NOT as a positive sale. Refunds that arrive BEFORE their
-- sale ping (ordering is not guaranteed) reconcile at read time: every
-- report joins refunded_cents back to the original sale by tx_id, and the
-- net-profit view never double-counts a refunded sale as revenue plus loss --
-- the refunded sale row stays status='verified' for the GROSS number, and
-- the refund subtracts once, via refunded_cents.
ALTER TABLE financial_events ADD COLUMN IF NOT EXISTS refunded_cents integer;

-- 2) Integration health: one row per external integration, updated by the
--    agent/webhooks. Enables the dashboard "is anything silently broken?"
--    view required by Phase 2 (P0-3). Column names match
--    IntegrationHealthRepository (integration, status, detail, checked_at);
--    last_ok_at/last_error_at are additive extras used by the finance page.
CREATE TABLE IF NOT EXISTS integration_health (
    integration    text PRIMARY KEY,          -- 'gumroad', 'payhip', 'devto', ...
    status         text NOT NULL DEFAULT 'configuration_missing'
                   CHECK (status IN ('connected', 'authorization_expired',
                                     'configuration_missing', 'quota_exceeded',
                                     'failed', 'awaiting_verification')),
    detail         text,
    last_ok_at     timestamptz,
    last_error_at  timestamptz,
    checked_at     timestamptz NOT NULL DEFAULT now()
);

-- 3) Health upsert rpc (service-role writable from Edge Functions;
--    SECURITY DEFINER keeps the table itself under RLS).
CREATE OR REPLACE FUNCTION upsert_integration_health(
    p_integration text,
    p_status text,
    p_detail text DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF p_status NOT IN ('connected', 'authorization_expired', 'configuration_missing',
                        'quota_exceeded', 'failed', 'awaiting_verification') THEN
        RAISE EXCEPTION 'invalid integration status %', p_status;
    END IF;
    INSERT INTO integration_health (integration, status, detail, checked_at,
                                    last_ok_at, last_error_at)
    VALUES (p_integration, p_status, p_detail, now(),
            CASE WHEN p_status = 'connected' THEN now() END,
            CASE WHEN p_status IN ('failed', 'authorization_expired') THEN now() END)
    ON CONFLICT (integration) DO UPDATE SET
        status = EXCLUDED.status,
        detail = EXCLUDED.detail,
        checked_at = now(),
        last_ok_at = COALESCE(EXCLUDED.last_ok_at, integration_health.last_ok_at),
        last_error_at = COALESCE(EXCLUDED.last_error_at, integration_health.last_error_at);
END;
$$;

-- RLS: match the existing single-owner model (owner does everything,
-- anon/webhook traffic goes through service-role Edge Functions).
ALTER TABLE integration_health ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'integration_health' AND policyname = 'owner_all_integration_health'
    ) THEN
        CREATE POLICY owner_all_integration_health ON integration_health
            FOR ALL TO authenticated USING (true) WITH CHECK (true);
    END IF;
END $$;
