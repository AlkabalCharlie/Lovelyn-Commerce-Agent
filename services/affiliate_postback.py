"""Affiliate postback normalization - the Python mirror of the
affiliate-postback Edge Function, so the exact same parsing/normalization
rules are unit-testable without network calls.

Endpoint receives whatever the network sends (GET query or POST form/JSON),
maps fields tolerantly, normalizes to cents, tags the source, and dedupes
on the transaction id. The OWNER pastes the endpoint URL into each network's
own postback settings - we never hardcode guessed macro names.
"""
import re
from decimal import Decimal, ROUND_HALF_UP

ALLOWED_SOURCES = ("payhip", "jvzoo", "clickbank", "cj", "shareasale",
                   "tradingview", "other")

AMOUNT_KEYS = ("amount", "amt", "total", "sale_amount", "commission", "value")
TX_KEYS = ("transaction_id", "txn_id", "trans_id", "order_id", "txid", "receipt", "oid")
PRODUCT_KEYS = ("product_id", "product", "item", "sku", "campaign_id")
CURRENCY_KEYS = ("currency", "cur", "curr")


def pick_param(params: dict, keys) -> str | None:
    """Tolerant field lookup: first non-empty hit among common key names."""
    for key in keys:
        value = params.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


def normalize_cents(raw: str) -> int | None:
    """'12.34'/'$12.34'/'1,234.56'/'7' -> cents. Returns None if unparseable or <= 0."""
    if raw is None:
        return None
    cleaned = str(raw).replace("$", "").replace(",", "").strip()
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        return None
    cents = int((Decimal(cleaned) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return cents if cents > 0 else None


def normalize_source(raw: str | None) -> str:
    source = (raw or "").strip().lower()
    return source if source in ALLOWED_SOURCES else "other"


def normalize_postback(params: dict) -> dict | None:
    """Full pipeline: params in -> normalized event dict out, or None if unusable."""
    amount_raw = pick_param(params, AMOUNT_KEYS)
    cents = normalize_cents(amount_raw)
    if cents is None:
        return None
    source = normalize_source(pick_param(params, ("source", "network")))
    tx = pick_param(params, TX_KEYS)
    if not tx:
        return None  # dedupe REQUIRES a stable transaction id
    currency = (pick_param(params, CURRENCY_KEYS) or "USD").upper()[:3]
    product = pick_param(params, PRODUCT_KEYS) or ""
    return {
        "stream": "affiliate",
        "amount_cents": cents,
        "currency": currency,
        "source": source,
        "source_type": source,
        "tx_id": tx,
        "note": f"affiliate postback {source}{(' product=' + product) if product else ''}"[:200],
    }
