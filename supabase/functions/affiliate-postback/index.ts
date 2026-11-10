// Generic affiliate postback endpoint (mirrors payhip-sales).
//
// PURPOSE: let non-Payhip networks (JVZoo, ClickBank, CJ, ShareASale,
// TradingView) auto-log commissions into financial_events exactly like
// Payhip does, so the optimizer and Finance page see affiliate money.
//
// THE OWNER pastes this endpoint URL (with ?token=...) into each network's
// own "payment notification / postback URL" settings. Each network substitutes
// ITS OWN macros into the query string; we do NOT hardcode guessed macro
// names - we just normalize whatever arrives.
//
// REUSES the payhip-sales structure: shared-token gate, idempotent dedupe
// on a unique transaction id, parameterized SQL via rpc.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ALLOWED_SOURCES = new Set([
  "payhip", "jvzoo", "clickbank", "cj", "shareasale", "tradingview", "other",
]);

// A network may send the amount with many field names; map tolerantly.
const AMOUNT_KEYS = ["amount", "amt", "total", "sale_amount", "commission", "value"];
// Same for the transaction/order identifier.
const TX_KEYS = ["transaction_id", "txn_id", "trans_id", "order_id", "txid", "receipt", "oid"];
// Product/reference identifiers (best-effort, for the note only).
const PRODUCT_KEYS = ["product_id", "product", "item", "sku", "campaign_id"];
const CURRENCY_KEYS = ["currency", "cur", "curr"];

function pick(params: Record<string, string>, keys: string[]): string | null {
  for (const k of keys) {
    const v = params[k];
    if (v !== undefined && v !== null && String(v).trim() !== "") return String(v).trim();
  }
  return null;
}

function normalize_cents(raw: string): number | null {
  // Tolerant: accepts "12.34", "$12.34", "12", "1,234.56", "1234" (bare cents
  // ambiguity resolved as DOLLARS unless a decimal point exists and value < 1? -> NO.
  // Rule: anything with a '.' is dollars; anything integer-looking and small
  // (< 10000, i.e. could plausibly be dollars) is dollars; large bare integers
  // are treated as cents to avoid mislogging huge sums as $0 outcomes... but
  // safer contract: REQUIRE a decimal form or a whole dollar number.
  const cleaned = raw.replace(/[$,\s]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  let cents: number;
  if (cleaned.includes(".")) {
    const [d, frac = ""] = cleaned.split(".");
    cents = parseInt(d, 10) * 100 + parseInt((frac + "00").slice(0, 2), 10);
  } else {
    cents = parseInt(cleaned, 10) * 100;
  }
  return cents > 0 ? cents : null;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "GET" && req.method !== "POST") {
    return new Response("method not allowed", { status: 405 });
  }

  const url = new URL(req.url);
  const token = url.searchParams.get("token");
  const expected = Deno.env.get("AFFILIATE_POSTBACK_TOKEN");
  if (!expected || !token || token.length < 24 || token !== expected) {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401, headers: { "Content-Type": "application/json" },
    });
  }

  // Merge query params and (if present) form-encoded or JSON body params.
  const params: Record<string, string> = {};
  url.searchParams.forEach((v, k) => { params[k] = v; });
  if (req.method === "POST") {
    const ctype = req.headers.get("content-type") || "";
    try {
      if (ctype.includes("application/json")) {
        const body = await req.json();
        for (const [k, v] of Object.entries(body)) params[k] = String(v);
      } else if (ctype.includes("form")) {
        const form = await req.formData();
        form.forEach((v, k) => { params[k] = String(v); });
      }
    } catch {
      // tolerate empty bodies - networks GET-postback all the time
    }
  }

  const source = (pick(params, ["source", "network"]) || "other").toLowerCase();
  if (!ALLOWED_SOURCES.has(source)) {
    return new Response(JSON.stringify({ error: "unknown source" }), {
      status: 400, headers: { "Content-Type": "application/json" },
    });
  }

  const amount_raw = pick(params, AMOUNT_KEYS);
  if (!amount_raw) {
    return new Response(JSON.stringify({ error: "missing amount" }), {
      status: 400, headers: { "Content-Type": "application/json" },
    });
  }
  const cents = normalize_cents(amount_raw);
  if (cents === null) {
    return new Response(JSON.stringify({ error: "bad amount" }), {
      status: 400, headers: { "Content-Type": "application/json" },
    });
  }

  // Dedupe id: network's transaction id, else fall back to a content hash so
  // accidental double-hits of the SAME url still no-op.
  const tx = pick(params, TX_KEYS)
    || `auto-${source}-${cents}-${Date.parse(url.searchParams.get("t") || "") || Date.now()}`;

  const currency = (pick(params, CURRENCY_KEYS) || "USD").toUpperCase().slice(0, 3);
  const product = pick(params, PRODUCT_KEYS) || "";
  const note = `affiliate postback ${source}${product ? ` product=${product}` : ""}`.slice(0, 200);

  const supabase = createClient(
    Deno.env.get("SB_URL")!,
    Deno.env.get("SB_SERVICE_ROLE")!,
  );

  const { data, error } = await supabase.rpc("record_financial_event", {
    p_stream: "affiliate",
    p_amount_cents: cents,
    p_currency: currency,
    p_source: source,
    p_note: note,
    p_external_id: tx,
    p_source_type: source,
    p_tx_id: tx,
  });

  if (error) {
    return new Response(JSON.stringify({ error: "db", detail: error.message }), {
      status: 500, headers: { "Content-Type": "application/json" },
    });
  }

  // rpc returns [{ recorded: bool }] - false means duplicate tx id (no-op).
  const recorded = Array.isArray(data) ? !!data[0]?.recorded : !!data;
  return new Response(JSON.stringify(recorded ? { ok: true, recorded: true }
                                            : { ok: true, recorded: false, dedupe: true }), {
    status: 200, headers: { "Content-Type": "application/json" },
  });
});
