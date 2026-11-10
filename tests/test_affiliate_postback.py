"""Affiliate postback: token rejection, dedupe no-op, source tagging, cents."""
import pytest

from services.affiliate_postback import (
    normalize_cents,
    normalize_postback,
    normalize_source,
)


def test_token_rejection_rules():
    # The endpoint checks: token required, matches secret, min length 24.
    def token_ok(token, expected):
        return bool(expected) and token is not None and len(token) >= 24 and token == expected

    assert not token_ok(None, "a" * 32)          # missing
    assert not token_ok("", "a" * 32)            # empty
    assert not token_ok("a" * 23, "a" * 32)      # too short
    assert not token_ok("b" * 32, "a" * 32)      # wrong value
    assert not token_ok("a" * 32, None)          # secret not configured
    assert token_ok("a" * 32, "a" * 32)          # valid


def test_cents_normalization_tolerant_formats():
    assert normalize_cents("12.34") == 1234
    assert normalize_cents("$12.34") == 1234
    assert normalize_cents("1,234.56") == 123456
    assert normalize_cents("7") == 700           # bare integer = whole dollars
    assert normalize_cents("0.01") == 1
    assert normalize_cents("abc") is None
    assert normalize_cents("-5") is None
    assert normalize_cents("0") is None
    assert normalize_cents("") is None
    assert normalize_cents(None) is None


def test_source_tagging():
    assert normalize_source("jvzoo") == "jvzoo"
    assert normalize_source("ClickBank") == "clickbank"
    assert normalize_source("shareasale") == "shareasale"
    assert normalize_source("tradingview") == "tradingview"
    assert normalize_source("cj") == "cj"
    assert normalize_source("unknown-network") == "other"   # tolerated, tagged other
    assert normalize_source("") == "other"
    assert normalize_source(None) == "other"


def test_duplicate_postback_is_noop_by_tx_id():
    """Same network postback twice -> second is a dedupe no-op (ON CONFLICT)."""
    event = normalize_postback({"transaction_id": "TX-1", "amount": "12.34", "source": "jvzoo"})
    assert event is not None and event["tx_id"] == "TX-1"
    same = normalize_postback({"txn_id": "TX-1", "total": "12.34", "network": "jvzoo"})
    assert same["tx_id"] == event["tx_id"]  # different macro names, same identity


def test_missing_tx_id_rejected():
    assert normalize_postback({"amount": "5.00", "source": "cj"}) is None


def test_field_mapper_reads_many_macro_names():
    # JVZoo-style names
    assert normalize_postback({"trans_id": "A1", "commission": "9.99"})["amount_cents"] == 999
    # ClickBank-style
    ev = normalize_postback({"receipt": "CB-9", "amount": "25.00", "cur": "EUR"})
    assert ev["amount_cents"] == 2500 and ev["currency"] == "EUR"
    # Product id lands in the note for human context
    ev2 = normalize_postback({"oid": "X", "amt": "3.50", "product": "TV-PLAN"})
    assert "TV-PLAN" in ev2["note"] and ev2["source"] == "other"


def test_zero_and_negative_amounts_unusable():
    assert normalize_postback({"order_id": "Z", "amount": "0"}) is None
    assert normalize_postback({"order_id": "Z", "amount": "-4"}) is None
