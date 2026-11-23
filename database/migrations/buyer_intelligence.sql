-- BUYER INTELLIGENCE ENGINE (AIDA)
-- Run once in the Supabase SQL editor. Additive only: creates new tables,
-- does not modify existing tables, policies, or the publishing pipeline.
--
-- Data-flow invariant: the daily email is a COPY of what is stored here.
-- No research insight exists only in an email.

-- 1) Evidence records: one raw observed discussion/post with provenance.
--    dedupe_key (sha256 of normalized source url + author + title) prevents
--    duplicate records; source_url is always preserved.
CREATE TABLE IF NOT EXISTS buyer_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dedupe_key text NOT NULL UNIQUE,
    source text NOT NULL,                 -- 'reddit', 'youtube_comments', ...
    source_url text NOT NULL,
    author text,                          -- for independent-discussion counting
    title text NOT NULL,
    body text,
    context text,                         -- subreddit / comment thread context
    retrieved_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,             -- when the discussion happened
    aida_stage text NOT NULL DEFAULT 'attention'
        CHECK (aida_stage IN ('attention','interest','desire','action','none')),
    raw_scores jsonb                      -- per-signal evidence from the scorer
);
ALTER TABLE buyer_evidence ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies
                   WHERE tablename = 'buyer_evidence'
                     AND policyname = 'owner_all_buyer_evidence') THEN
        CREATE POLICY owner_all_buyer_evidence ON buyer_evidence
            FOR ALL TO authenticated USING (true) WITH CHECK (true);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_buyer_evidence_stage
    ON buyer_evidence (aida_stage, retrieved_at DESC);

-- 2) Buyer-need clusters: recurring demand grouped from evidence.
--    evidence_count counts DISTINCT authors (independent discussions), not
--    raw rows, so one loud person never inflates demand.
CREATE TABLE IF NOT EXISTS buyer_needs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_key text NOT NULL UNIQUE,     -- stable slug for dedupe
    title text NOT NULL,
    problem_description text NOT NULL,
    target_audience text,
    aida_stage text NOT NULL
        CHECK (aida_stage IN ('attention','interest','desire','action')),
    intent_score integer NOT NULL CHECK (intent_score BETWEEN 0 AND 100),
    score_reasoning text NOT NULL,        -- why the score was assigned
    observed_vs_inferred jsonb NOT NULL DEFAULT '{}',
        -- {"observed": [...], "inferred": [...]} separates fact from inference
    confidence text NOT NULL DEFAULT 'low'
        CHECK (confidence IN ('high','medium','low')),
    evidence_count integer NOT NULL DEFAULT 0,   -- distinct independent authors
    source_urls jsonb NOT NULL DEFAULT '[]',
    latest_evidence_at timestamptz,
    desired_features jsonb NOT NULL DEFAULT '[]',
    price_sensitivity text,
    common_objections jsonb NOT NULL DEFAULT '[]',
    unmet_aspects jsonb NOT NULL DEFAULT '[]',
    suggested_categories jsonb NOT NULL DEFAULT '[]',
    first_seen date NOT NULL DEFAULT current_date,
    last_updated date NOT NULL DEFAULT current_date
);
ALTER TABLE buyer_needs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies
                   WHERE tablename = 'buyer_needs'
                     AND policyname = 'owner_all_buyer_needs') THEN
        CREATE POLICY owner_all_buyer_needs ON buyer_needs
            FOR ALL TO authenticated USING (true) WITH CHECK (true);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_buyer_needs_score
    ON buyer_needs (intent_score DESC, last_updated DESC);

-- 3) Product matches: candidates evaluated against a buyer need.
--    NO campaign is created here and promotion_approved is never touched.
CREATE TABLE IF NOT EXISTS buyer_product_matches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    need_id uuid NOT NULL REFERENCES buyer_needs(id) ON DELETE CASCADE,
    product_url text NOT NULL,
    product_name text NOT NULL,
    merchant text,
    verified_features jsonb NOT NULL DEFAULT '[]',  -- only observed claims
    price_cents integer,                            -- NULL = price unverified
    commission_cents integer,                       -- NULL = unverified
    commission_note text,                           -- provenance of commission
    match_score integer NOT NULL CHECK (match_score BETWEEN 0 AND 100),
    match_reasoning text NOT NULL,
    missing_info jsonb NOT NULL DEFAULT '[]',
    is_existing_campaign boolean NOT NULL DEFAULT false,
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (need_id, product_url)
);
ALTER TABLE buyer_product_matches ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies
                   WHERE tablename = 'buyer_product_matches'
                     AND policyname = 'owner_all_buyer_product_matches') THEN
        CREATE POLICY owner_all_buyer_product_matches ON buyer_product_matches
            FOR ALL TO authenticated USING (true) WITH CHECK (true);
    END IF;
END $$;

-- 4) Daily run ledger: research status + email idempotency.
--    report_email_sent_at UNIQUE-per-day sentinel prevents duplicate emails
--    even across concurrent cloud + local runs.
CREATE TABLE IF NOT EXISTS buyer_intel_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date date NOT NULL UNIQUE,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    sources_ok jsonb NOT NULL DEFAULT '[]',
    sources_failed jsonb NOT NULL DEFAULT '[]',
    evidence_collected integer NOT NULL DEFAULT 0,
    needs_upserted integer NOT NULL DEFAULT 0,
    products_matched integer NOT NULL DEFAULT 0,
    unmet_opportunities integer NOT NULL DEFAULT 0,
    report_email_sent_at timestamptz,     -- set once; UNIQUE(run_date) guards it
    report_error text
);
ALTER TABLE buyer_intel_runs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies
                   WHERE tablename = 'buyer_intel_runs'
                     AND policyname = 'owner_all_buyer_intel_runs') THEN
        CREATE POLICY owner_all_buyer_intel_runs ON buyer_intel_runs
            FOR ALL TO authenticated USING (true) WITH CHECK (true);
    END IF;
END $$;

-- v2 (relevance gate): store the gate verdict with every match.
ALTER TABLE buyer_product_matches ADD COLUMN IF NOT EXISTS classification text
    NOT NULL DEFAULT 'weak_match'
    CHECK (classification IN ('direct_match','partial_match','weak_match','unrelated'));
ALTER TABLE buyer_product_matches ADD COLUMN IF NOT EXISTS gate_explanation text;
ALTER TABLE buyer_product_matches ADD COLUMN IF NOT EXISTS gate_reasons jsonb
    NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_buyer_matches_classification
    ON buyer_product_matches (need_id, classification);
