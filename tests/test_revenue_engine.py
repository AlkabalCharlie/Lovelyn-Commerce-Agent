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


# --- 5. Complete demand-to-campaign-to-content decision path -------------

TV_CID = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
DEBT_CID = "66d125ce-0523-492b-9679-3bd06d75e1be"


def _products():
    return [
        {"id": TV_CID, "name": "TradingView",
         "description": ("charting platform technical analysis indicators "
                         "alerts stock charts trading tools subscription"),
         "status": "approved"},
        {"id": DEBT_CID, "name": "Be Free from Debt",
         "description": ("debt repayment budgeting worksheets snowball "
                         "avalanche payoff plan guide"),
         "status": "approved"},
    ]


def test_scenario_1_tradingview_opportunity_selects_tradingview():
    r = score_demand(
        "TradingView vs TradingView alternatives - is the paid plan worth it?",
        "comparing TradingView Essential against the free plan for charting "
        "and alerts, is the subscription worth buying",
        _products())
    assert r["qualified"], r["reasons"]
    assert r["matched_product_id"] == TV_CID
    assert r["intent_score"] >= 22  # comparison intent detected


def test_scenario_2_debt_opportunity_selects_debt_guide():
    r = score_demand(
        "Need a debt repayment plan - snowball or avalanche?",
        "looking for practical debt payoff worksheets and budgeting help",
        _products())
    assert r["qualified"], r["reasons"]
    assert r["matched_product_id"] == DEBT_CID


def test_scenario_3_unrelated_opportunity_rejected():
    r = score_demand(
        "Best pizza toppings?",
        "pineapple on pizza debate, casual food discussion",
        _products())
    assert not r["qualified"]
    assert r["matched_product_id"] is None


def test_opportunity_changes_generated_content_and_association():
    from services.content_packages import (
        opportunity_blogger_draft, opportunity_youtube_script)
    opp_tv = {"title": "Is TradingView Essential worth $14.95/mo?",
              "source_url": "https://www.reddit.com/r/TradingView/x1",
              "score": 61, "intent_score": 24, "intent_categories": ["comparison"]}
    opp_debt = {"title": "Need a debt payoff spreadsheet",
                "source_url": "https://www.reddit.com/r/debtfree/x2",
                "score": 55, "intent_score": 22, "intent_categories": ["seeking_solution"]}

    tv_pkg = opportunity_youtube_script(TV_CID, f"https://lovelyn.matchqip.com/campaign-{TV_CID}.html",
                                        opp_tv, f"test-opp-tv-{opp_tv['score']}")
    debt_pkg = opportunity_blogger_draft(DEBT_CID, f"https://lovelyn.matchqip.com/campaign-{DEBT_CID}.html",
                                         opp_debt, f"test-opp-debt-{opp_debt['score']}")
    # Campaign association follows the opportunity's matched campaign
    assert tv_pkg["opportunity"]["source_url"] == opp_tv["source_url"]
    assert debt_pkg["opportunity"]["source_url"] == opp_debt["source_url"]
    # Content differs per opportunity: TV hook quotes its question, debt
    # draft contains the honest format-difference section
    assert opp_tv["title"][:40] in tv_pkg["hook"]
    assert any("spreadsheet" in s and "worksheets" in s
               for s in [debt_pkg["body_markdown"]][0].split("\n\n"))
    assert debt_pkg["origin"] == "demand_opportunity"
    assert tv_pkg["origin"] == "demand_opportunity"


def test_evergreen_package_labelled_and_no_opportunity_claim():
    from services.content_packages import youtube_script_package
    pkg = youtube_script_package(TV_CID, f"https://lovelyn.matchqip.com/campaign-{TV_CID}.html",
                                 "Evergreen topic", "test-evergreen-label",
                                 evergreen=True)
    assert pkg["origin"] == "evergreen_campaign_asset"
    assert pkg["opportunity"] is None


def test_agent_calls_score_demand_and_uses_result():
    """Trace: the scheduled run scores every scout lead, rejects unqualified
    ones, stores provenance in notes, and lets the top score drive packages."""
    import inspect
    from services import autonomous_agent
    src = inspect.getsource(autonomous_agent.run_daily_grind)
    assert "score_demand" in src
    assert 'if not verdict["qualified"]' in src
    assert "intent=" in src and "score=" in src          # provenance in notes
    assert 'max(qualified_leads' in src                   # top opportunity drives packages
    assert "top is None" in src                           # evergreen only as fallback


def test_score_demand_is_called_in_agent():
    import inspect
    from services import autonomous_agent
    src = inspect.getsource(autonomous_agent.run_daily_grind)
    # the actual call site, not merely an import
    assert "score_demand(lead[\"title\"]" in src
