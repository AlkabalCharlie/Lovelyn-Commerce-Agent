-- Atomic, token-verified insert for the affiliate-postback Edge Function.
-- Dedupe on tx_id: re-sending the same network postback is a NO-OP.
CREATE OR REPLACE FUNCTION record_financial_event(
    p_stream text,
    p_amount_cents integer,
    p_currency text,
    p_source text,
    p_note text,
    p_external_id text,
    p_source_type text,
    p_tx_id text
) RETURNS TABLE (recorded boolean)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    landed boolean := false;
BEGIN
    -- Idempotency: one commission per network transaction id. Uses a nested
    -- transaction so a conflict rolls back cleanly without aborting us.
    BEGIN
        INSERT INTO financial_events
            (stream, amount_cents, currency, source, note, external_id, source_type, tx_id)
        VALUES
            (p_stream, p_amount_cents, p_currency, p_source, p_note, p_external_id, p_source_type, p_tx_id);
        landed := true;
    EXCEPTION WHEN unique_violation THEN
        landed := false;  -- duplicate postback: no-op
    END;

    RETURN QUERY SELECT landed;
END;
$$;
