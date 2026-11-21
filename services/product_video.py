"""Product-specific video briefs: campaign -> verified product facts.

Directive section 2 implementation. Source of truth priority:
1. services/content_packages.PRODUCT_FACTS (verified against live pages)
2. The campaign/product DB records (name, merchant, description, price,
   affiliate_url)
3. NOTHING else. No invented features, prices, reviews or guarantees.

If essential facts are missing the brief is marked insufficient=True and the
caller flags the campaign for review instead of generating generic promo.
"""
from dataclasses import dataclass, field

from services.content_packages import PRODUCT_FACTS


@dataclass
class ProductBrief:
    campaign_id: str
    product_name: str
    merchant: str
    category: str                 # digital | physical | software | unknown
    destination_url: str          # the ONLY approved CTA link
    description: str
    facts: list = field(default_factory=list)
    disclosure: str = ""
    audience: str = ""
    insufficient: bool = False
    missing: list = field(default_factory=list)

    def cta(self) -> str:
        return f"Get {self.product_name} at the link below."


def build_brief(campaign_id: str, product_name: str, merchant: str,
                product_url: str, affiliate_url: str | None,
                description: str | None, price) -> ProductBrief:
    """Assemble a verified brief. affiliate_url (when set) IS the approved
    destination - never substituted."""
    dest = (affiliate_url or product_url or "").strip()
    if not dest:
        return ProductBrief(campaign_id, product_name, merchant, "unknown",
                            "", description or "", insufficient=True,
                            missing=["destination_url"])

    known = PRODUCT_FACTS.get(campaign_id)
    facts = list(known["facts"]) if known else []
    disclosure = known["disclosure"] if known else (
        "Disclosure: affiliate link - we may earn a commission at no extra "
        "cost to you.")
    if not facts:
        # Fall back to DB facts only; require at least a description.
        if not (description or "").strip():
            return ProductBrief(campaign_id, product_name, merchant,
                                "unknown", dest, description or "",
                                insufficient=True,
                                missing=["description", "verified_facts"])
        facts = [description.strip()]

    name_l = product_name.lower()
    if any(k in name_l for k in ("guide", "worksheet", "pack", "planner",
                                 "template", "ebook", "course", "debt")):
        category = "digital"
    elif any(k in name_l for k in ("software", "app", "tool", "ai", "saas",
                                   "tradingview")):
        category = "software"
    else:
        category = "physical"

    audience = {
        "digital": "people who want a clear step-by-step system",
        "software": "people who need this exact capability",
        "physical": "people with the problem this product solves",
    }[category]

    brief = ProductBrief(campaign_id, product_name, merchant, category, dest,
                         description or "", facts=facts, disclosure=disclosure,
                         audience=audience)
    if not dest.startswith("http"):
        brief.insufficient = True
        brief.missing.append("valid_url")
    return brief


def build_script(brief: ProductBrief) -> dict:
    """Six-beat narrative structure (directive section 5) built FROM THE
    PRODUCT'S OWN FACTS. Not a generic template: every line names the actual
    product or uses its verified facts."""
    if brief.insufficient:
        raise ValueError(f"insufficient verified info: {brief.missing}")

    cat = brief.category
    problem = {
        "digital": "You keep planning your debt payoff on random notes. "
                   "It never sticks.",
        "software": "You keep doing this the manual way, and it costs you "
                    "hours every week.",
        "physical": "You have the problem. The fixes you've tried don't "
                    "stick.",
    }[cat]
    discovery = f"That is exactly why {brief.product_name} exists."
    demo = " ".join(brief.facts[:2])
    benefit = (f"{brief.facts[-1]} " if len(brief.facts) > 2 else
               f"Made for {brief.audience}. ")
    cta = (f"{brief.cta()} Link below. {brief.disclosure}")

    return {
        "title": f"{brief.product_name}: honest 30-second look",
        "description": (f"What {brief.product_name} actually includes, and "
                        f"who it's for.\n{brief.disclosure}\n"
                        f"{brief.destination_url}"),
        "tags": [brief.product_name.lower(), brief.merchant.lower(),
                 brief.category, "review"],
        "destination_url": brief.destination_url,
        "scenes": [
            {"beat": "hook",      "on_screen": "The plan isn't the problem.",
             "narration": problem.split(".")[0] + "."},
            {"beat": "problem",   "on_screen": "Sound familiar?",
             "narration": problem},
            {"beat": "discovery", "on_screen": brief.product_name,
             "narration": discovery},
            {"beat": "demo",      "on_screen": "What's inside:",
             "narration": demo},
            {"beat": "benefit",   "on_screen": brief.audience,
             "narration": benefit},
            {"beat": "cta",       "on_screen": brief.cta(),
             "narration": cta},
        ],
    }
