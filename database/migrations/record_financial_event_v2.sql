-- PHASE 2: attribution-aware, idempotent financial event insert.
-- Replaces the Phase-1 rpc additively: same signature works, new optional
-- params let the postback chain carry campaign/product attribution.
CREATE OR REPLACE FUNCTION record_financial_event(
    p_stream text,
    p_amount_cents integer,
    p_currency text,
    p_source text,
    p_note text,
    p_external_id text,
    p_source_type text,
    p_tx_id text,
    p_campaign_id uuid DEFAULT NULL,
    p_product_id uuid DEFAULT NULL,
    p_fees_cents integer DEFAULT NULL,
    p_cost_cents integer DEFAULT NULL,
    p_status text DEFAULT 'verified',
    p_refunded_cents integer DEFAULT NULL
) RETURNS TABLE (recorded boolean)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    landed boolean := false;
BEGIN
    BEGIN
        INSERT INTO financial_events
            (stream, amount_cents, currency, source, note, external_id,
             source_type, tx_id, campaign_id, product_id, fees_cents,
             cost_cents, status, refunded_cents)
        VALUES
            (p_stream, p_amount_cents, p_currency, p_source, p_note, p_external_id,
             p_source_type, p_tx_id, p_campaign_id, p_product_id, p_fees_cents,
             p_cost_cents, p_status, p_refunded_cents);
        landed := true;
    EXCEPTION WHEN unique_violation THEN
        landed := false;  -- duplicate postback: no-op
    END;
    RETURN QUERY SELECT landed;
END;
$$;
