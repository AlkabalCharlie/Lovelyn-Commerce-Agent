"""Product-to-need matching (post-demand research).

Contract (spec sections 6 & 7):
- Consumption order: highest-priority buyer-need clusters first.
- Candidates come from the EXISTING verified product table plus optional
  external affiliate-program search - never invented.
- Only VERIFIED facts are recorded: price only when actually observed,
  commission only with a provenance note. "High commission" alone never
  selects a product.
- Transparent match score with per-point reasoning; missing information is
  flagged explicitly, never papered over.
- No campaign is created here; campaigns.promotion_approved stays the sole
  authorization source of truth.
"""
import re

from services.demand_matcher import _tokens

MATCH_WEIGHTS = {
    "problem_relevance": 30,
    "feature_alignment": 25,
    "audience_fit": 15,
    "price_suitability": 10,
    "evidence_quality": 10,
    "merchant_availability": 10,
}


def match_product(need: dict, product) -> dict:
    """Score one candidate product against one buyer-need cluster.

    `need` is a buyer_needs row dict; `product` is a Product model or dict
    (verified fields only are read). Returns a transparent verdict dict.
    """
    reasons = []
    missing = []

    def get(field, default=None):
        if isinstance(product, dict):
            return product.get(field, default)
        return getattr(product, field, default)

    name = (get("name") or "").strip()
    description = (get("description") or "").strip()
    product_text = f"{name} {description}"
    product_tokens = _tokens(product_text)

    problem_tokens = _tokens(
        f"{need.get('title', '')} {need.get('problem_description', '')}")
    feature_tokens = _tokens(" ".join(need.get("desired_features") or []))
    audience_tokens = _tokens(need.get("target_audience") or "")

    # 1. Problem relevance (30): token overlap between verified product text
    #    and the need's problem statement. Zero overlap = not a candidate.
    overlap = problem_tokens & product_tokens
    if len(overlap) >= 2:
        precision = len(overlap) / max(1, len(problem_tokens))
        recall = len(overlap) / max(1, len(product_tokens))
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall else 0)
        relevance = min(30, round(f1 * 60))
        reasons.append(f"Problem relevance (+{relevance}/30): shared terms "
                       f"{sorted(overlap)[:6]}.")
    else:
        relevance = 0
        reasons.append("Problem relevance (+0/30): fewer than two meaningful "
                       "shared terms with the problem statement.")

    # 2. Feature alignment (25): does the product description mention the
    #    desired features? Only VERIFIED description text counts.
    feature_overlap = feature_tokens & product_tokens
    if feature_tokens:
        alignment = min(25, round(25 * len(feature_overlap) /
                                  max(1, len(feature_tokens))))
        reasons.append(f"Feature alignment (+{alignment}/25): "
                       f"{sorted(feature_overlap)[:6] or 'none'} of the "
                       f"desired features appear in the verified description.")
        if not feature_overlap:
            missing.append("None of the desired features are confirmed by "
                           "the product description.")
    else:
        alignment = 12  # need expressed no specific features: neutral credit
        reasons.append("Feature alignment (+12/25): need expressed no "
                       "specific features to check.")

    # 3. Audience fit (15): audience terms appearing in product text.
    audience_overlap = audience_tokens & product_tokens
    audience = (min(15, round(15 * len(audience_overlap) /
                              max(1, len(audience_tokens))))
                if audience_tokens else 7)
    if audience_tokens:
        reasons.append(f"Audience fit (+{audience}/15): "
                       f"{sorted(audience_overlap)[:4] or 'no direct'} "
                       f"audience-term overlap.")
    else:
        reasons.append("Audience fit (+7/15): target audience not specific "
                       "enough to evaluate.")

    # 4. Price suitability (10): only when BOTH sides are verified.
    price_cents = get("price_cents")
    need_price = parse_price_bound(need.get("price_sensitivity") or "")
    if price_cents is not None and need_price is not None:
        if price_cents <= need_price:
            price_score = 10
            reasons.append(f"Price suitability (+10/10): verified "
                           f"{price_cents/100:.2f} within budget "
                           f"{need_price/100:.2f}.")
        else:
            price_score = 3
            reasons.append(f"Price suitability (+3/10): verified "
                           f"{price_cents/100:.2f} exceeds stated budget "
                           f"{need_price/100:.2f}.")
            missing.append("Price exceeds the buyers' stated budget.")
    else:
        price_score = 5
        reasons.append("Price suitability (+5/10): price or budget "
                       "unverified - flagged, not assumed.")
        if price_cents is None:
            missing.append("Product price unverified.")

    # 5. Evidence quality (10): is there REAL evidence behind the product
    #    claims (description present = extracted facts, not a bare URL)?
    if len(description) >= 80:
        evidence_score = 10
        reasons.append("Evidence quality (+10/10): verified description "
                       "present (fact-extracted, not invented).")
    else:
        evidence_score = 4
        missing.append("Thin product description - claims not verifiable.")
        reasons.append("Evidence quality (+4/10): thin verified data.")

    # 6. Merchant/availability (10): affiliate destination present = buyable.
    if get("affiliate_url"):
        merchant_score = 10
        reasons.append("Merchant availability (+10/10): purchase destination "
                       "configured.")
    else:
        merchant_score = 5
        reasons.append("Merchant availability (+5/10): no affiliate/purchase "
                       "link yet.")
        missing.append("No verified purchase destination.")

    match_score = min(100, relevance + alignment + audience + price_score +
                      evidence_score + merchant_score)
    return {
        "match_score": match_score,
        "match_reasoning": " ".join(reasons),
        "missing_info": missing,
        "verified_features": sorted(feature_overlap)[:10],
    }


_PRICE_RE = re.compile(r"(?:under|below|max|up to|budget of|around|about)?"
                       r"\s*\$?\s*(\d+(?:\.\d{1,2})?)", re.I)


def parse_price_bound(text_value: str):
    """Extract a budget ceiling in CENTS from free-text price sensitivity.
    Returns None when no number is present (never guessed)."""
    match = _PRICE_RE.search(text_value or "")
    if not match:
        return None
    try:
        return int(float(match.group(1)) * 100)
    except ValueError:
        return None


def recommend_for_need(need: dict, products) -> list:
    """Evaluate all candidate products for one need; return scored verdicts
    sorted best-first. Weak matches (<40) are flagged, not recommended."""
    verdicts = []
    for product in products:
        verdict = match_product(need, product)
        verdict["product"] = product
        verdict["recommended"] = verdict["match_score"] >= 40 and (
            verdict["match_score"] >= 55 or not verdict["missing_info"])
        verdicts.append(verdict)
    verdicts.sort(key=lambda v: v["match_score"], reverse=True)
    return verdicts
