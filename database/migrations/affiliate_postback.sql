-- Generic affiliate postback support.
-- 1) Discriminate where money came from. Existing rows keep their meaning.
ALTER TABLE financial_events ADD COLUMN IF NOT EXISTS source_type text;

-- 2) Strong idempotence: one commission per network transaction id.
ALTER TABLE financial_events ADD COLUMN IF NOT EXISTS tx_id text;
CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_events_tx_id
    ON financial_events (tx_id) WHERE tx_id IS NOT NULL;

-- RLS is already enabled on financial_events; adding nullable columns
-- never changes policies.
