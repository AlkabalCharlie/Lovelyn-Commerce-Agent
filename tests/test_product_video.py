"""Tests for product-specific video generation (directive section 10)."""
import pytest

from services.product_video import ProductBrief, build_brief, build_script


DEBT = dict(campaign_id="66d125ce-0523-492b-9679-3bd06d75e1be",
            product_name="Be Free from Debt",
            merchant="Payhip",
            product_url="https://payhip.com/b/debt",
            affiliate_url="https://payhip.com/b/debt?ref=us",
            description="50+ page debt payoff guide with worksheets.",
            price="$7.00")


def test_brief_uses_affiliate_url_as_destination():
    b = build_brief(**DEBT)
    assert b.destination_url == "https://payhip.com/b/debt?ref=us"
    assert b.insufficient is False


def test_brief_missing_url_is_insufficient():
    b = build_brief(**{**DEBT, "affiliate_url": None, "product_url": ""})
    assert b.insufficient is True
    assert "destination_url" in b.missing


def test_brief_without_facts_or_description_is_insufficient():
    b = build_brief(campaign_id="unknown-campaign", product_name="Mystery",
                    merchant="Somewhere", product_url="https://x.example",
                    affiliate_url=None, description=None, price=None)
    assert b.insufficient is True


def test_scripts_differ_between_products():
    """Generic-video failure mode: same script, different last sentence."""
    debt = build_brief(**DEBT)
    tv = build_brief(campaign_id="b8d56c20-c801-4c97-ac8f-936bb5c36cba",
                     product_name="TradingView",
                     merchant="TradingView",
                     product_url="https://tradingview.com",
                     affiliate_url="https://tradingview.com/?ref=us",
                     description=None, price=None)
    s1, s2 = build_script(debt), build_script(tv)
    assert s1["scenes"][0]["narration"] != s2["scenes"][0]["narration"]
    assert s1["scenes"][3]["narration"] != s2["scenes"][3]["narration"]
    assert s1["title"] != s2["title"]


def test_script_names_the_actual_product():
    s = build_script(build_brief(**DEBT))
    joined = " ".join(sc["narration"] for sc in s["scenes"])
    assert "Be Free from Debt" in joined


def test_cta_uses_campaign_destination():
    s = build_script(build_brief(**DEBT))
    assert s["destination_url"] == "https://payhip.com/b/debt?ref=us"
    assert s["scenes"][-1]["beat"] == "cta"


def test_category_detection():
    assert build_brief(**DEBT).category == "digital"
    tv = build_brief(campaign_id="b8d56c20-c801-4c97-ac8f-936bb5c36cba",
                     product_name="TradingView", merchant="TradingView",
                     product_url="https://tv.example", affiliate_url=None,
                     description=None, price=None)
    assert tv.category == "software"


def test_six_beat_structure():
    s = build_script(build_brief(**DEBT))
    beats = [sc["beat"] for sc in s["scenes"]]
    assert beats == ["hook", "problem", "discovery", "demo", "benefit", "cta"]


def test_no_invented_claims():
    """Script must only contain facts from the brief."""
    s = build_script(build_brief(**DEBT))
    joined = " ".join(sc["narration"] for sc in s["scenes"])
    for banned in ("$9", "guaranteed", "best seller", "50000 users"):
        assert banned not in joined
