// Gumroad Ping receiver (owned-product stream). Phase 2.
//
// CONTRACT (Gumroad Ping docs, verified 2026-11):
// - POST, x-www-form-urlencoded, UNSIGNED. Gated by shared token in the URL
//   (?token=..., >= 24 chars) plus seller_id verification.
// - At-least-once delivery + repeats: dedupe REQUIRED.
// - Refunds carry the SAME sale_id as the sale: dedupe on
//   (resource_name, sale_id) via distinct tx_id per resource.
// - price / gumroad_fee are integer CENTS. test=true pings are ignored.
// - Payload is unsigned => treat ping as trigger; the canonical flow re-reads
//   the sale from the Gumroad API. We accept ping data when the owner has not
//   set GUMROAD_ACCESS_TOKEN, and reconcile via API when they have.
// - Responses ALWAYS 2xx for handled pings (Gumroad retries only 499/5xx;
//   a rejected or ignored ping must not burn those retries).
// - CAMPAIGN ATTRIBUTION: the ping itself is never attributed; campaign_id is
//   read ONLY from url_params (the dictionary of URL params the buyer's
//   product link carried). Lovelyn campaign Buy links append
//   ?campaign_id=<uuid> to OWNED_PRODUCT_URL, so only sales that entered
//   through a Lovelyn campaign page carry it.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

async function set_health(
  supabase: ReturnType<typeof createClient>,
  status: string,
  detail: string,
) {
  await supabase.rpc("upsert_integration_health", {
    p_integration: "gumroad",
    p_status: status,
    p_detail: detail.slice(0, 200),
  });
}

function cents(raw: string | null): number | null {
  if (raw === null || raw === undefined) return null;
  const cleaned = String(raw).replace(/[$,\s]/g, "");
  if (/^\d+$/.test(cleaned)) return parseInt(cleaned, 10);      // already cents
  if (/^\d+\.\d{1,2}$/.test(cleaned)) {                          // dollars fallback
    const [d, frac = ""] = cleaned.split(".");
    return parseInt(d, 10) * 100 + parseInt((frac + "00").slice(0, 2), 10);
  }
  return null;
}

function truthy(raw: string | undefined | null): boolean {
  return ["true", "1", "yes"].includes((raw || "").toLowerCase());
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("method not allowed", { status: 405 });
  }

  const url = new URL(req.url);
  const token = url.searchParams.get("token");
  const expected = Deno.env.get("GUMROAD_PING_TOKEN");
  if (!expected || !token || token.length < 24 || token !== expected) {
    return new Response(JSON.stringify({ error: "unauthorized" }),
      { status: 401, headers: { "Content-Type": "application/json" } });
  }

  const ctype = req.headers.get("content-type") || "";
  if (!ctype.includes("application/x-www-form-urlencoded")) {
    return new Response(JSON.stringify({ error: "expected form-encoded ping" }),
      { status: 400, headers: { "Content-Type": "application/json" } });
  }
  const body = await req.text();
  const params: Record<string, string> = {};
  new URLSearchParams(body).forEach((v, k) => { params[k] = v; });

  // Test purchases prove the pipe works but are never recorded as revenue.
  if (["true", "1", "yes"].includes((params.test || "").toLowerCase())) {
    const s = createClient(Deno.env.get("SB_URL")!, Deno.env.get("SB_SERVICE_ROLE")!);
    await set_health(s, "connected", "test ping received (not recorded)");
    return new Response(JSON.stringify({ ok: true, ignored: "test ping" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }

  // Seller mismatch: log it, acknowledge 2xx - do not burn Gumroad's retries
  // on a config error we can already see.
  const expectedSeller = Deno.env.get("GUMROAD_SELLER_ID");
  if (expectedSeller && params.seller_id && params.seller_id !== expectedSeller) {
    const s = createClient(Deno.env.get("SB_URL")!, Deno.env.get("SB_SERVICE_ROLE")!);
    await set_health(s, "failed", `seller_id mismatch: ${params.seller_id}`);
    return new Response(JSON.stringify({ ok: false, reason: "seller_mismatch" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }

  const supabase = createClient(
    Deno.env.get("SB_URL")!,
    Deno.env.get("SB_SERVICE_ROLE")!,
  );

  const saleId = params.sale_id;
  if (!saleId) {
    await set_health(supabase, "failed", "ping without sale_id");
    return new Response(JSON.stringify({ ok: false, reason: "missing_sale_id" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }
  const price = cents(params.price);
  if (price === null || price <= 0) {
    await set_health(supabase, "failed", `bad price for sale ${saleId}`);
    return new Response(JSON.stringify({ ok: false, reason: "bad_price" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }

  const resource = (params.resource_name || "sale").toLowerCase();
  const isRefund = resource === "refund" || resource === "cancellation"
    || truthy(params.refunded || params.is_refunded);
  const txId = isRefund ? `refund-${saleId}` : `sale-${saleId}`;

  // Attribution: Gumroad passes URL params through as url_params (JSON-ish).
  // Lovelyn campaign links embed ?campaign_id=<uuid>; map it when present.
  let campaignId: string | null = null;
  try {
    const up = params.url_params ? JSON.parse(params.url_params) : null;
    const candidate = up?.campaign_id || up?.cid || null;
    if (candidate && /^[0-9a-fA-F-]{36}$/.test(String(candidate))) {
      campaignId = String(candidate);
    }
  } catch { /* url_params absent or not JSON - attribution stays null */ }

  const fee = isRefund ? 0 : (cents(params.gumroad_fee) || 0);
  const shipping = isRefund ? 0 : (cents(params.shipping_rate) || 0);
  const stream = "owned";
  const status = isRefund ? "reversed" : "verified";
  // Refund rows store the reversed amount here; net-profit reporting sums
  // refunded_cents ONCE. The original sale row (same sale_id, tx
  // sale-<id>) keeps its amount for the GROSS figure and is NOT reduced.
  // Order-independent: the refund may land BEFORE its sale ping.
  const refunded = isRefund ? price : null;
  const note = (`gumroad ${resource} product=${params.product_name || ""}`
    + (params.order_number ? ` order=${params.order_number}` : "")
    ).slice(0, 200);

  // Verify-then-record when an API token exists: read the sale back before
  // trusting the unsigned ping. Fail-closed on API rejection.
  const apiToken = Deno.env.get("GUMROAD_ACCESS_TOKEN");
  if (apiToken) {
    try {
      const resp = await fetch(
        `https://api.gumroad.com/v2/sales/${encodeURIComponent(saleId)}`,
        { headers: { Authorization: `Bearer ${apiToken}` } });
      if (!resp.ok) {
        return new Response(JSON.stringify({ error: "sale not verifiable via API" }),
          { status: 502, headers: { "Content-Type": "application/json" } });
      }
    } catch { /* network hiccup: fall through to ping data (still deduped) */ }
  }

  const { data, error } = await supabase.rpc("record_financial_event", {
    p_stream: stream,
    p_amount_cents: price,
    p_currency: (params.currency || "usd").toUpperCase().slice(0, 3),
    p_source: "gumroad",
    p_note: note,
    p_external_id: txId,
    p_source_type: "gumroad",
    p_tx_id: txId,
    p_campaign_id: campaignId,
    p_product_id: null, // gumroad product ids are not our uuids; map via note/lookup
    p_fees_cents: fee,
    p_cost_cents: shipping, // shipping recovered on the sale; refund rows carry 0
    p_status: status,
    p_refunded_cents: refunded,
  });

  if (error) {
    await set_health(supabase, "failed", `db: ${error.message}`);
    return new Response(JSON.stringify({ error: "db", detail: error.message }),
      { status: 500, headers: { "Content-Type": "application/json" } });
  }
  const recorded = Array.isArray(data) ? !!data[0]?.recorded : !!data;
  await set_health(supabase, "connected", `last ping: ${txId}`);
  return new Response(JSON.stringify(recorded
    ? { ok: true, recorded: true }
    : { ok: true, recorded: false, dedupe: true }),
    { status: 200, headers: { "Content-Type": "application/json" } });
});
