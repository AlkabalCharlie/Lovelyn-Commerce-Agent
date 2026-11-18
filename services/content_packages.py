"""Production-ready content packages for non-automated channels.

Everything here is DETERMINISTIC and FACT-BOUNDED: scripts and drafts are
built only from verified product facts already stored in the campaign/product
records. No invented testimonials, results, or first-hand experiences.

Packages produced:
- YouTube/Shorts: full script package (hook, scenes, narration, captions,
  title/description/tags, CTA, disclosure). NOT a rendered video — no ffmpeg
  in the environment; recorded honestly as script-only.
- Blogger: complete markdown article draft.
- Pinterest: pin package (title, description, search terms, destination).
- Community: reply drafts via the existing draft_reply pipeline.
"""
from services.publishing_queue import queue_package

# Verified facts only (checked against live merchant pages 2026-11-18).
PRODUCT_FACTS = {
    "b8d56c20-c801-4c97-ac8f-936bb5c36cba": {  # TradingView
        "name": "TradingView",
        "facts": [
            "Free tier: 2 indicators per chart, 1 saved layout, 5 price alerts, ads shown.",
            "Essential plan: 5 indicators per chart, 2 charts per tab, 20 alerts, no ads ($14.95/mo monthly; lower billed annually).",
            "Paid tiers mainly add: indicators per chart, charts per tab, alert capacity, saved layouts, ad removal.",
            "Community-published scripts and broker integrations are TradingView strengths free clones lack.",
        ],
        "disclosure": ("Disclosure: this link is an affiliate link; if you "
                       "subscribe through it we may earn a commission at no "
                       "extra cost to you."),
    },
    "66d125ce-0523-492b-9679-3bd06d75e1be": {  # Be Free from Debt
        "name": "Be Free from Debt",
        "facts": [
            "$7.00 one-time, instant DOCX download from Payhip.",
            "50+ pages: zero-based budgeting, the 50/30/20 rule, the envelope system.",
            "Includes worksheets and templates you fill in; global examples.",
            "A self-applied workbook: value comes from doing the worksheets. Not financial advice.",
        ],
        "disclosure": ("Disclosure: this is our own product; we receive the "
                       "proceeds if you buy through the link."),
    },
}

CTA = {
    "b8d56c20-c801-4c97-ac8f-936bb5c36cba":
        "Compare the plans yourself here (affiliate link):",
    "66d125ce-0523-492b-9679-3bd06d75e1be":
        "Get the worksheet pack here ($7, instant download):",
}


def youtube_script_package(campaign_id: str, campaign_url: str,
                           topic: str, slug: str, evergreen: bool = False,
                           opportunity: dict | None = None) -> dict | None:
    """Full production-ready script package. NOT a rendered video (no ffmpeg
    available). 45-60s Shorts format."""
    facts = PRODUCT_FACTS.get(campaign_id)
    if not facts:
        return None
    bullets = "\n".join(f"- {f}" for f in facts["facts"])
    package = {
        "format_type": "youtube_shorts_script",
        "origin": ("demand_opportunity" if opportunity
                   else "evergreen_campaign_asset" if evergreen
                   else "unspecified"),
        "opportunity": ({"source_url": opportunity.get("source_url"),
                         "title": opportunity.get("title"),
                         "score": opportunity.get("score"),
                         "intent_score": opportunity.get("intent_score"),
                         "intent_categories": opportunity.get("intent_categories")}
                        if opportunity else None),
        "note": ("SCRIPT PACKAGE ONLY — video rendering requires ffmpeg, "
                 "which is not available in this environment. Owner renders "
                 "with any TTS/slideshow tool, then uploads manually."),
        "title": topic[:95],
        "hook": ("STOP guessing which plan you need — here's the actual "
                 "difference in 45 seconds." if "trading" in slug or
                 "tradingview" in slug.lower() else
                 "Your debt payoff fails at the plan, not the motivation. "
                 "Here's the one-page fix."),
        "scenes": [
            {"scene": 1, "duration_s": 5, "on_screen": "Hook text",
             "narration": "Same as hook."},
            {"scene": 2, "duration_s": 25, "on_screen": bullets,
             "narration": "Read the verified facts above plainly."},
            {"scene": 3, "duration_s": 10, "on_screen": "Who it's for / who should skip",
             "narration": ("If you trade one market on one timeframe, stay free."
                           if campaign_id.startswith("b8d5") else
                           "If the worksheets stay unopened, skip it.")},
            {"scene": 4, "duration_s": 10, "on_screen": CTA[campaign_id],
             "narration": "Link in the description. " + facts["disclosure"]},
        ],
        "captions": bullets,
        "description": f"{topic}\n\n{facts['disclosure']}\n{campaign_url}",
        "tags": ["budgeting", "debt payoff"] if campaign_id.startswith("66d1")
                else ["tradingview", "charting", "trading tools"],
        "campaign_url": campaign_url,
        "disclosure": facts["disclosure"],
    }
    queue_package("youtube", campaign_id, slug, "script", package)
    return package


def opportunity_youtube_script(campaign_id: str, campaign_url: str,
                               opportunity: dict, slug: str) -> dict | None:
    """Script package TAILORED to a discovered opportunity: the hook answers
    the actual question asked, and the opportunity provenance travels with
    the package."""
    topic = (opportunity.get("title") or "Buyer question")[:95]
    pkg = youtube_script_package(campaign_id, campaign_url, topic, slug,
                                 evergreen=False, opportunity=opportunity)
    if pkg:
        pkg["hook"] = (f"Someone just asked: '{topic}'. Here's the direct, "
                       f"fact-checked answer.")
    return pkg


def opportunity_blogger_draft(campaign_id: str, campaign_url: str,
                              opportunity: dict, slug: str) -> dict | None:
    """Blogger draft answering the opportunity's actual question. For
    worksheet/format objections (e.g. 'looking for a spreadsheet'), the draft
    honestly addresses what the guide format does and does not provide."""
    facts = PRODUCT_FACTS.get(campaign_id)
    if not facts:
        return None
    topic = (opportunity.get("title") or "Buyer question")[:95]
    is_debt = campaign_id.startswith("66d1")
    sections = [
        f"The question, verbatim from a real discussion: '{topic}'.",
        ("What actually solves this: list every debt with balance, rate and "
         "minimum; choose snowball (early wins) or avalanche (least interest); "
         "automate minimums; throw every spare dollar at the target.")
        if is_debt else
        ("The facts: " + " ".join(facts["facts"])),
    ]
    if is_debt:
        sections.append(
            "Format honesty: this is a guide with fill-in worksheets, not an "
            "interactive spreadsheet. If you want formulas that recalculate "
            "your debt-free date automatically, a spreadsheet tool fits "
            "better. If you want the methods explained with templates to "
            "fill in by hand, this $7 DOCX pack fits.")
    sections.append("Verified facts: " + " ".join(facts["facts"]))
    package = blogger_article_draft(campaign_id, campaign_url,
                                    f"Answering: {topic}", slug, sections,
                                    evergreen=False)
    if package:
        package["origin"] = "demand_opportunity"
        package["opportunity"] = {"source_url": opportunity.get("source_url"),
                                  "title": opportunity.get("title"),
                                  "score": opportunity.get("score")}
    return package


def blogger_article_draft(campaign_id: str, campaign_url: str, title: str,
                          slug: str, sections: list[str],
                          evergreen: bool = False) -> dict | None:
    facts = PRODUCT_FACTS.get(campaign_id)
    if not facts:
        return None
    body = "\n\n".join(sections)
    package = {
        "format_type": "blogger_article_markdown",
        "origin": ("evergreen_campaign_asset" if evergreen
                   else "unspecified"),
        "title": title[:95],
        "body_markdown": body + (f"\n\n{CTA[campaign_id]} {campaign_url}\n\n"
                                 f"*{facts['disclosure']}*"),
        "labels": ["personal finance", "trading"] if campaign_id.startswith(
            "b8d5") else ["personal finance", "budgeting", "debt"],
        "campaign_url": campaign_url,
        "disclosure": facts["disclosure"],
    }
    queue_package("blogger", campaign_id, slug, "article_draft", package)
    return package


def pinterest_pin_package(campaign_id: str, campaign_url: str, pin_title: str,
                          slug: str, evergreen: bool = False) -> dict | None:
    facts = PRODUCT_FACTS.get(campaign_id)
    if not facts:
        return None
    package = {
        "format_type": "pin_package",
        "origin": ("evergreen_campaign_asset" if evergreen
                   else "unspecified"),
        "pin_title": pin_title[:95],
        "pin_description": (
            f"{facts['facts'][1] if len(facts['facts']) > 1 else facts['facts'][0]} "
            f"{CTA[campaign_id]}"),
        "search_terms": (["debt payoff plan", "budget worksheet",
                          "snowball vs avalanche"] if campaign_id.startswith("66d1")
                         else ["tradingview review", "charting platform",
                               "trading for beginners"]),
        "image_spec": "1000x1500 (2:3), headline text top third, product URL bottom",
        "destination_url": campaign_url,
        "disclosure": facts["disclosure"],
        "note": ("Image asset must be generated by the owner (Pillow template "
                 "possible later); Pinterest API credentials not configured, "
                 "so manual pinning is required."),
    }
    queue_package("pinterest", campaign_id, slug, "pin_package", package)
    return package
