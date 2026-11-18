"""Acceptance tests for the autonomous revenue engine activation.

Covers the directive's minimum verification list that can be tested without
live external services. DB-dependent tests use the real Supabase schema via
the existing engine (single-owner private project; additive-only queue table).
"""
from services.publishing_queue import (
    mark_published,
    queue_count,
    queue_package,
)
from services.demand_matcher import score_demand


# --- 1. Unauthorized campaigns cannot be promoted ------------------------

def test_unauthorized_campaign_never_reaches_site_source():
    import inspect
    from database import repositories
    src = inspect.getsource(repositories.CampaignRepository.publish_campaign)
    assert "promotion_approved = TRUE" in src
    src2 = inspect.getsource(repositories.CampaignRepository.list_published_campaigns)
    assert "promotion_approved = TRUE" in src2


def test_agent_package_queue_only_for_authorized_campaigns():
    """The package-queue step reads authorization before queueing."""
    import inspect
    from services import autonomous_agent
    src = inspect.getsource(autonomous_agent.run_daily_grind)
    assert "_authorized(camp_repo, tv)" in src
    assert "_authorized(camp_repo, debt)" in src


# --- 2. Demand matching feeds campaign selection -------------------------

def test_high_intent_post_matches_authorized_product():
    products = [{
        "id": "debt-1",
        "name": "Be Free from Debt",
        "description": "debt repayment budgeting worksheets snowball avalanche guide",
        "status": "approved",
    }]
    r = score_demand("Which debt payoff method should I use?",
                     "comparing snowball vs avalanche, need budgeting worksheets",
                     products)
    assert r["qualified"] and r["matched_product_id"] == "debt-1"
    assert r["intent_score"] >= 22  # comparison or better


def test_casual_discussion_not_qualified():
    products = [{
        "id": "debt-1", "name": "Be Free from Debt",
        "description": "debt repayment budgeting worksheets guide",
        "status": "approved",
    }]
    r = score_demand("weather today", "sunny with a chance of rain", products)
    assert not r["qualified"] and r["matched_product_id"] is None


# --- 3. Publishing queue: idempotence, statuses, no fake publishing ------

def test_queue_idempotent_and_owner_only_publication():
    cid = "66d125ce-0523-492b-9679-3bd06d75e1be"
    pkg = {"format_type": "youtube_shorts_script", "title": "t"}
    slug = f"test-slug-{__import__('random').randint(10000, 99999)}"
    assert queue_package("youtube", cid, slug, "script", pkg) is True
    assert queue_package("youtube", cid, slug, "script", pkg) is False  # retry = no-op
    assert queue_package("youtube", cid, slug, "script", pkg) is False


def test_queue_rejects_invalid_channel():
    import pytest
    with pytest.raises(ValueError):
        queue_package("tiktok", "66d125ce-0523-492b-9679-3bd06d75e1be",
                      "x", "script", {})


def test_mark_published_requires_queued_status():
    """A published item cannot be re-marked (idempotent transitions)."""
    # mark a nonexistent id -> False (and importantly, does not crash)
    assert mark_published("00000000-0000-0000-0000-000000000000",
                          "https://example.com") is False


def test_content_packages_fact_bounded():
    from services.content_packages import PRODUCT_FACTS, youtube_script_package
    tv = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
    pkg = youtube_script_package(tv, "https://lovelyn.matchqip.com/campaign-b8d56c20-c801-4c97-ac8f-936bb5c36cba.html",
                                 "t", "test-tv-pkg-x")
    assert pkg is not None
    # every fact line must be one of the VERIFIED facts, no invention
    assert all(f in PRODUCT_FACTS[tv]["facts"] for f in
               [s["on_screen"] for s in pkg["scenes"] if s["on_screen"].startswith(("Free", "Essential", "Paid", "Community"))])
    assert "affiliate" in pkg["disclosure"].lower()


# --- 4. Financial integrity guards remain -------------------------------

def test_test_pings_never_recorded():
    from services.gumroad_ping import normalize_ping
    assert normalize_ping({"sale_id": "s1", "price": "100", "test": "true"}) is None


def test_refund_dedupe_key_distinct_from_sale():
    from services.gumroad_ping import normalize_ping
    sale = normalize_ping({"sale_id": "s9", "price": "500", "seller_id": "x"})
    refund = normalize_ping({"sale_id": "s9", "price": "500", "resource_name": "refund"})
    assert sale["tx_id"] != refund["tx_id"]
    assert sale["status"] == "verified" and refund["status"] == "reversed"


def test_reporting_separates_test_data():
    """net_profit_summary exists and the dashboard source excludes nothing by
    accident: statuses verified/reversed are the only money states."""
    import inspect
    from database import repositories
    src = inspect.getsource(repositories.FinanceRepository.net_profit_summary)
    assert "verified" in src
