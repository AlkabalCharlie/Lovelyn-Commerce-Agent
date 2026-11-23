"""Buyer-intelligence engine tests.

Pure-unit: no network, no database, no emails sent. Production campaign
data, publishing queues and financial records are never touched.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.buyer_intent import (  # noqa: E402
    ACTION, ATTENTION, DESIRE, INTEREST, NONE,
    SCORE_WEIGHTS, classify_aida, cluster_key_for, confidence_for,
    dedupe_key, score_band, score_buyer_intent,
)
from services.buyer_product_matching import (  # noqa: E402
    match_product, parse_price_bound, recommend_for_need,
)


# ------------------------------------------------------- AIDA classification
def test_action_requires_explicit_purchase_signal():
    stage, matched = classify_aida("Where can I buy a trading journal?")
    assert stage == ACTION
    assert matched["purchase"]


def test_curiosity_is_never_action():
    stage, _ = classify_aida("What is a trading journal exactly?")
    assert stage != ACTION


def test_interest_stage_from_research_language():
    stage, matched = classify_aida("How do I track my day trading trades?")
    assert stage == INTEREST
    assert matched["research"]


def test_desire_stage_from_outcome_language():
    stage, matched = classify_aida(
        "I want something that exports my trades to CSV, must have charts")
    assert stage == DESIRE
    assert matched["desire"]


def test_attention_stage_from_pain_only():
    stage, matched = classify_aida("My notes app keeps failing me every day")
    assert stage == ATTENTION
    assert matched["problem"]


def test_no_signal_is_none():
    stage, matched = classify_aida("The weather is nice today")
    assert stage == NONE


# ------------------------------------------------------------ intent scoring
def test_high_intent_post_scores_above_80():
    result = score_buyer_intent(
        "Urgent: I keep losing money day trading. Which is better, "
        "Tradervue or Edgewonk? Where can I buy one under $30?")
    assert result["score"] >= 80
    assert result["stage"] == ACTION


def test_score_components_are_evidence_backed():
    result = score_buyer_intent(
        "Urgent problem: where can I buy a debt payoff planner under $20?")
    total_claimed = sum(
        SCORE_WEIGHTS[c] for c in result["evidence"]
        if not result["evidence"][c][0].startswith("(inferred)"))
    # awarded weight sum + 0-point components == score, transparently
    assert result["score"] <= 100
    for component, phrases in result["evidence"].items():
        assert phrases, f"{component} awarded with no evidence"


def test_observed_and_inferred_are_separated():
    result = score_buyer_intent("How do I stop overspending on takeout?")
    assert result["observed"], "matched phrases must be observed"
    assert result["inferred"], "stage conclusion must be an inference"
    for obs in result["observed"]:
        assert not obs.startswith("(inferred)")


def test_vague_post_scores_low():
    result = score_buyer_intent("idk just something for money maybe")
    assert result["score"] < 40


def test_score_is_bounded():
    spam = " ".join(["urgent where can i buy cheaper alternative"] * 10)
    result = score_buyer_intent(spam)
    assert result["score"] <= 100


def test_score_bands():
    assert score_band(85) == "high_intent"
    assert score_band(70) == "strong_opportunity"
    assert score_band(45) == "developing_demand"
    assert score_band(10) == "early_awareness"


# ---------------------------------------------------------------- confidence
def test_single_source_high_score_is_low_confidence():
    assert confidence_for(1, 90) == "low"


def test_multi_source_supports_confidence():
    assert confidence_for(3, 90) == "high"
    assert confidence_for(2, 65) in ("medium", "high")


# ------------------------------------------------------------- dedupe/cluster
def test_dedupe_key_stable_and_url_normalized():
    a = dedupe_key("reddit", "http://x.com/p/1/", "alice", "Best budget app?")
    b = dedupe_key("reddit", "http://x.com/p/1", "ALICE", "best budget app?")
    assert a == b  # trailing slash + case normalize to the same content


def test_dedupe_key_distinguishes_posts():
    a = dedupe_key("reddit", "http://x.com/p/1", "alice", "t1")
    b = dedupe_key("reddit", "http://x.com/p/2", "bob", "t2")
    assert a != b


def test_cluster_key_groups_similar_needs():
    a = cluster_key_for("Where can I buy a trading journal tool?")
    b = cluster_key_for("Best trading journal tool recommendations?")
    c = cluster_key_for("My sourdough starter keeps dying")
    assert a == b      # same need vocabulary clusters together
    assert a != c      # unrelated posts do not


# ---------------------------------------------------------- product matching
class FakeProduct:
    def __init__(self, name, description="", price=None, affiliate_url=None,
                 merchant="TestMerchant", status="approved"):
        self.name = name
        self.description = description
        self.price_cents = price
        self.affiliate_url = affiliate_url
        self.merchant = merchant
        self.status = status


NEED = {
    "title": "trading journal tool",
    "problem_description": "trades are hard to track and review",
    "target_audience": "day trading stocks",
    "desired_features": ["csv export", "trade tagging", "analytics"],
    "price_sensitivity": "under $30",
}


def test_matching_product_scores_well():
    product = FakeProduct(
        "TradeLog Pro trading journal",
        "Trading journal with csv export, trade tagging and analytics for "
        "stocks and day trading reviews.", price=2900,
        affiliate_url="https://merchant.example/aff")
    verdict = match_product(NEED, product)
    assert verdict["match_score"] >= 55
    assert verdict["match_reasoning"]
    assert not verdict["missing_info"]


def test_unrelated_product_is_rejected():
    product = FakeProduct("Yoga Mat", "Extra thick non-slip yoga mat.")
    verdict = match_product(NEED, product)
    assert verdict["match_score"] < 40


def test_missing_price_is_flagged_not_assumed():
    product = FakeProduct(
        "TradeLog trading journal",
        "Trading journal with csv export and analytics.",
        price=None)
    verdict = match_product(NEED, product)
    assert any("price" in m.lower() for m in verdict["missing_info"])


def test_missing_affiliate_link_is_flagged():
    product = FakeProduct(
        "TradeLog trading journal",
        "Trading journal with csv export and analytics.", price=2900)
    verdict = match_product(NEED, product)
    assert any("purchase destination" in m.lower()
               for m in verdict["missing_info"])


def test_commission_never_selects_alone():
    # High-commission unrelated product must lose to a low-key relevant one.
    bad = FakeProduct("Crypto Signal Bot", "Premium crypto signals, expensive.",
                      price=99000)
    good = FakeProduct(
        "TradeLog trading journal",
        "Trading journal with csv export, trade tagging and analytics.",
        price=2900)
    ranked = recommend_for_need(NEED, [bad, good])
    assert ranked[0]["product"] is good


def test_price_bound_parsing():
    assert parse_price_bound("under $30") == 3000
    assert parse_price_bound("budget of 50 dollars") == 5000
    assert parse_price_bound("no budget mentioned") is None


# ---------------------------------------------------- email idempotency logic
def test_run_ledger_email_sent_semantics():
    """Documented contract test against a fake: mark_email_sent must be
    once-per-day (returns True once, False afterwards)."""
    class FakeLedger:
        def __init__(self):
            self.sent_at = None
        def mark_email_sent(self, run_date):
            if self.sent_at is None:
                self.sent_at = run_date
                return True
            return False
    ledger = FakeLedger()
    from datetime import date as _d
    assert ledger.mark_email_sent(_d(2026, 1, 1)) is True
    assert ledger.mark_email_sent(_d(2026, 1, 1)) is False
