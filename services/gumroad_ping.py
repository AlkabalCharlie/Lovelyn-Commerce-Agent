"""Gumroad Ping normalization - the Python mirror of the gumroad-ping Edge
Function, so parsing rules are unit-testable without network calls.

CONTRACT (verified against Gumroad's Ping docs, gumroad.com/ping + /api):
- POST, x-www-form-urlencoded; any 2xx acknowledges.
- Delivery is AT LEAST ONCE -> dedupe. Ordering NOT guaranteed -> a refund
  ping can arrive BEFORE its sale ping.
- Payload is UNSIGNED. The ping is a TRIGGER, not trusted data: we gate on a
  long shared token in the endpoint URL (like the affiliate postback) and
  verify seller_id matches ours. Periodic re-reconciliation via the Gumroad
  API (sale read-back) is the documented hardening step; recorded here as a
  limitation, not silently skipped.
- Refund ping carries the SAME sale_id as the sale it reverses -> dedupe key
  MUST be (sale_id, resource_name), never sale_id alone.
- price/gumroad_fee/shipping are integer CENTS already. 'test' purchases must
  never be recorded as money. resource_name in ('sale','refund','cancellation').
- campaign_id/product_id attribution comes ONLY from a uuid present in the
  ping params (in production the Edge Function reads it from url_params, the
  URL params the buyer's product link carried); non-uuid values are dropped,
  never guessed.
"""
import re

SELLER_KEYS = ("seller_id",)
SALE_ID_KEYS = ("sale_id", "order_id", "transaction_id")
RESOURCE_KEYS = ("resource_name", "resource")
PRICE_KEYS = ("price", "sale_price", "amount")
FEE_KEYS = ("gumroad_fee", "fee")
SHIPPING_KEYS = ("shipping_rate_cents", "shipping")
PRODUCT_ID_KEYS = ("product_id", "pid")
PRODUCT_NAME_KEYS = ("product_name", "product", "permalink")
EMAIL_KEYS = ("email", "email_address")
CURRENCY_KEYS = ("currency", "cur")
REFUND_KEYS = ("refunded", "is_refunded", "refund")
TEST_KEYS = ("test", "is_test")
CAMPAIGN_ID_KEYS = ("campaign_id", "cid", "url_params_campaign_id")
ORDER_NUMBER_KEYS = ("order_number", "order")

VALID_RESOURCE_NAMES = ("sale", "purchase", "cancellation", "refund", "refunded")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def pick(params: dict, keys) -> str | None:
    for key in keys:
        value = params.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "y", "t")


def _uuid_or_none(raw: str | None) -> str | None:
    if raw and UUID_RE.fullmatch(raw):
        return raw.lower()
    return None


def _int_cents(raw: str | None) -> int | None:
    """Gumroad cents fields are integers already; tolerate stray whitespace.
    Returns None when absent/not a plain non-negative integer."""
    if raw is None:
        return None
    if not re.fullmatch(r"\d+", raw.strip()):
        return None
    return int(raw)


def normalize_ping(params: dict) -> dict | None:
    """params in -> normalized owned-stream event dict out, or None if unusable.

    Rules:
    - missing sale_id or seller mismatch handled by the CALLER (needs config).
    - 'test' purchases return None (never recorded as money).
    - refund/decision: resource_name or refunded flag flips the event into a
      reversal with NEGATIVE cost effect handled downstream (we record the
      refund as its OWN row: stream=owned, status=reversed, amount=price).
    """
    sale_id = pick(params, SALE_ID_KEYS)
    if not sale_id:
        return None
    resource = (pick(params, RESOURCE_KEYS) or "").strip().lower()
    refunded_flag = _truthy(pick(params, REFUND_KEYS))
    is_refund = refunded_flag or resource in ("cancellation", "refund", "refunded")

    if _truthy(pick(params, TEST_KEYS)):
        return None  # Gumroad test purchases are not money

    price = _int_cents(pick(params, PRICE_KEYS))
    if price is None or price <= 0:
        return None
    fees = _int_cents(pick(params, FEE_KEYS)) or 0
    shipping = _int_cents(pick(params, SHIPPING_KEYS)) or 0

    currency = (pick(params, CURRENCY_KEYS) or "USD").upper()[:3]
    product_name = pick(params, PRODUCT_NAME_KEYS) or ""
    campaign_id = _uuid_or_none(pick(params, CAMPAIGN_ID_KEYS))
    product_id = _uuid_or_none(pick(params, PRODUCT_ID_KEYS))
    order_number = pick(params, ORDER_NUMBER_KEYS) or ""

    # Dedupe key: sale_id + event kind (refund shares sale_id with its sale).
    tx_id = f"gumroad-{sale_id}-{'refund' if is_refund else 'sale'}"

    kind = "refund" if is_refund else "sale"
    return {
        "stream": "owned",
        "amount_cents": price,
        "currency": currency,
        "source": "gumroad",
        "source_type": "gumroad_ping",
        "tx_id": tx_id,
        "campaign_id": campaign_id,
        "product_id": product_id,
        "fees_cents": fees,
        # shipping recovered on the sale; a refund carries no shipping
        "cost_cents": shipping if not is_refund else 0,
        "status": "reversed" if is_refund else "verified",
        # the amount this row reverses; net-profit sums it ONCE. The original
        # sale row (tx sale-<id>) keeps its amount for the GROSS figure and is
        # NOT reduced. Order-independent: refund may precede its sale ping.
        "refunded_cents": price if is_refund else None,
        "note": f"gumroad ping {kind}"
                f"{(' product=' + product_name) if product_name else ''}"
                f"{(' order=' + order_number) if order_number else ''}"[:200],
    }


# ---- url_params attribution (what the Edge Function actually receives) ----

def extract_campaign_id_from_url_params(params: dict) -> str | None:
    """Gumroad passes buyer-link URL params through in url_params (a JSON
    dict). Lovelyn campaign Buy links append ?campaign_id=<uuid>; only a
    well-formed uuid is accepted - anything else is dropped, never guessed."""
    import json
    raw = params.get("url_params")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return _uuid_or_none(str(parsed.get("campaign_id") or parsed.get("cid") or ""))
