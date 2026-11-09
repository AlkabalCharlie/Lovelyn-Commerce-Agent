-- Reddit Scout leads: humans asking questions the OWNER will answer by hand.
-- The bot NEVER posts to Reddit (guardrail #1) - this table only stores links.
CREATE TABLE IF NOT EXISTS leads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid REFERENCES products(id) ON DELETE SET NULL,
    subreddit text NOT NULL,
    title text NOT NULL,
    url text NOT NULL UNIQUE,
    found_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'new',
    notes text
);

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

CREATE POLICY leads_all_auth ON leads
    FOR ALL TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status, found_at DESC);
