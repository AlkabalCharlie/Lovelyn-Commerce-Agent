// Gumroad Ping receiver - dedicated Edge Function (NOT the affiliate postback).
//
// CONTRACT VERIFIED FROM GUMROAD'S OWN DOCS (gumroad.com/ping, /api):
// - POST, x-www-form-urlencoded, any 2xx acknowledges; body of response unread.
// - At-least-once delivery -> dedupe REQUIRED. Ordering NOT guaranteed: a
//   refund ping can arrive before its sale ping.
// - The payload is UNSIGNED. Doc guidance: "treat a ping as a trigger rather
//   than as data" and reconcile by reading the sale back through the API.
//   We therefore: (1) gate on a long shared token in the URL, (2) verify
//   seller_id matches the configured owner, (3) dedupe on sale_id + event
//   kind (refund shares sale_id with its sale), and (4) record limitation:
//   periodic API read-back reconciliation is the follow-up hardening step.
// - price/gumroad_fee/shipping_rate_cents are integer CENTS already.
// - 'test' purchases must never be recorded as money.
// - Refund: SAME sale_id as the sale -> stored as its own reversed row.
//
// OWNER SETUP (manual, one time):
//   1. supabase secrets set GUMROAD_PING_TOKEN=<random >=24 chars>
//                          GUMROAD_SELLER_ID=<your gumroad seller id>
//   2. Gumroad Settings -> Advanced -> Ping endpoint:
//      https://<project>.supabase.co/functions/v1/gumroad-sales?token=<same token>
//   3. "Send test ping to URL" -> check integration_health row flips connected.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

function pick(params: Record<string, string>, keys: string[]): string | null {
  for (const k of keys) {
    const v = params[k];
    if (v !== undefined && v !== null && String(v).trim() !== "") return String(v).trim();
  }
  return null;
}

function truthy(raw: string | null): boolean {
  return ["1", "true", "yes", "y", "t"].includes((raw || "").toLowerCase());
}

function uuid_or_none(raw: string | null): string | null {
  return raw && UUID_RE.test(raw) ? raw.toLowerCase() : null;
}

function int_cents(raw: string | null): number | null {
  if (raw === null || !/^\d+$/.test(raw)) return null;
  return parseInt(raw, 10);
}

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

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("method not allowed", { status: 405 });
  }

  const url = new URL(req.url);
  const token = url.searchParams.get("token");
  const expected = Deno.env.get("GUMROAD_PING_TOKEN");
  if (!expected || !token || token.length < 24 || token !== expected) {
    return new Response("unauthorized", { status: 401 });
  }

  // Gumroad sends form-urlencoded (JSON is not part of the Ping contract).
  const params: Record<string, string> = {};
  try {
    const form = await req.formData();
    form.forEach((v, k) => { params[k] = String(v); });
  } catch {
    // tolerate empty bodies; validation below will reject
  }

  const supabase = createClient(
    Deno.env.get("SB_URL")!,
    Deno.env.get("SB_SERVICE_ROLE")!,
  );

  const sellerId = pick(params, ["seller_id"]);
  const expectedSeller = Deno.env.get("GUMROAD_SELLER_ID");
  if (!expectedSeller || sellerId !== expectedSeller) {
    await set_health(supabase, "failed", `seller_id mismatch: ${sellerId}`);
    // 2xx anyway: do not burn Gumroad's retries on a config error we can see.
    return new Response(JSON.stringify({ ok: false, reason: "seller_mismatch" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }

  const saleId = pick(params, ["sale_id"]);
  if (!saleId) {
    await set_health(supabase, "failed", "ping without sale_id");
    return new Response(JSON.stringify({ ok: false, reason: "missing_sale_id" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }

  const resource = (pick(params, ["resource_name", "resource"]) || "").toLowerCase();
  const isRefund = truthy(pick(params, ["refunded", "is_refunded"]))
    || ["cancellation", "refund", "refunded"].includes(resource);

  if (truthy(pick(params, ["test", "is_test"]))) {
    // A test ping proves the pipe works: healthy, but NOT money.
    await set_health(supabase, "connected", "test ping received (not recorded)");
    return new Response(JSON.stringify({ ok: true, recorded: false, test: true }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }

  const price = int_cents(pick(params, ["price", "sale_price", "amount"]));
  if (price === null || price <= 0) {
    await set_health(supabase, "failed", `bad price for sale ${saleId}`);
    return new Response(JSON.stringify({ ok: false, reason: "bad_price" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }
  const fees = int_cents(pick(params, ["gumroad_fee", "fee"])) || 0;
  const shipping = int_cents(pick(params, ["shipping_rate_cents", "shipping"])) || 0;
  const currency = (pick(params, ["currency", "cur"]) || "USD").toUpperCase().slice(0, 3);
  const productName = pick(params, ["product_name", "product", "permalink"]) || "";
  const orderNumber = pick(params, ["order_number", "order"]) || "";
  const campaignId = uuid_or_none(pick(params, ["campaign_id", "cid", "utm_campaign"]));
  const productId = uuid_or_none(pick(params, ["product_id", "pid"]));

  // Dedupe key: sale_id + kind. A refund REUSES the sale's sale_id.
  const tx = `gumroad-${saleId}-${isRefund ? "refund" : "sale"}`;
  const note = `gumroad ping ${isRefund ? "refund" : "sale"}`
    + (productName ? ` product=${productName}` : "")
    + (orderNumber ? ` order=${orderNumber}` : "");

  const { data, error } = await supabase.rpc("record_financial_event", {
    p_stream: "owned",
    p_amount_cents: price,
    p_currency: currency,
    p_source: "gumroad",
    p_note: note.slice(0, 200),
    p_external_id: tx,
    p_source_type: "gumroad_ping",
    p_tx_id: tx,
    p_campaign_id: campaignId,
    p_product_id: productId,
    p_fees_cents: fees,
    p_cost_cents: isRefund ? -shipping : shipping,
    p_status: isRefund ? "reversed" : "verified",
  });

  if (error) {
    await set_health(supabase, "failed", `db: ${error.message}`);
    return new Response(JSON.stringify({ error: "db", detail: error.message }),
      { status: 500, headers: { "Content-Type": "application/json" } });
  }

  await set_health(supabase, "connected", `last ping: ${tx}`);
  const recorded = Array.isArray(data) ? !!data[0]?.recorded : !!data;
  return new Response(JSON.stringify(recorded ? { ok: true, recorded: true }
    : { ok: true, recorded: false, dedupe: true }),
    { status: 200, headers: { "Content-Type": "application/json" } });
});
