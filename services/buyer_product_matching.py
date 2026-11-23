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

RELEVANCE GATE (added after the da26fc9 weakness was demonstrated): a
same-industry product sharing buyer vocabulary scored 53/100 and was
RECOMMENDED for a debt-payoff need while solving an investing problem.
Relevance is therefore now gated BEFORE scoring; the numeric score can
never override the gate.

Classifications (mutually exclusive, stored with every match):
  direct_match  : clearly solves the buyer's stated problem
  partial_match : addresses part of it, with stated limitations
  weak_match    : superficial alignment; NOT for promotion
  unrelated     : does not solve the buyer's problem; NEVER recommended
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

DIRECT = "direct_match"
PARTIAL = "partial_match"
WEAK = "weak_match"
UNRELATED = "unrelated"
RELEVANCE_CLASSIFICATIONS = (DIRECT, PARTIAL, WEAK, UNRELATED)

# ---------------------------------------------------------------- gate ----
# Domain lexicon: which problem-space does a text belong to? Applied to the
# buyer's need text AND to the product's VERIFIED name+description only.
_DOMAIN_LEXICON = {
    "trading_markets": (
        "trading", "trader", "traders", "charting", "chart", "charts",
        "stocks", "stock", "forex", "crypto", "investing", "investor",
        "market", "markets", "technical analysis", "indicators",
        "candlestick", "price action",
    ),
    "debt_budgeting": (
        "debt", "debts", "payoff", "pay off", "budget", "budgeting",
        "budgeting worksheets", "worksheet", "worksheets", "credit card",
        "snowball", "avalanche", "debt-free", "get out of debt",
    ),
    "financial_advice": (
        "financial advisor", "financial advice", "financial planning",
        "financial plan", "certified planner", "financial coach",
        "wealth manager", "fiduciary", "advisory service",
    ),
    "home_physical": (
        "floor mat", "floor mats", "garage mat", "doormat", "door mat",
        "rug", "carpet", "flooring", "anti-fatigue", "non-slip mat",
        "heavy duty mat",
    ),
    "games_entertainment": (
        "games", "game", "html5", "gaming", "playable", "arcade",
        "puzzle game", "browser game",
    ),
    "ai_content": (
        "ai", "artificial intelligence", "ai-powered", "copywriting",
        "writing assistant", "content creation", "ai tools",
    ),
    "software_tools": (
        "app", "software", "tool", "platform", "dashboard", "saas",
        "automation", "tracking", "analytics", "api", "integration",
    ),
}

# Problem FUNCTIONS: what the buyer wants DONE, and what a product
# verifiably does. A need maps to functions via its own text; a product's
# functions come ONLY from its verified name+description.
_PROBLEM_FUNCTIONS = {
    "trading_markets": (
        "analyze", "analysis", "chart", "screen", "indicators",
        "technical analysis", "backtest", "alerts", "watch markets",
        "track stocks", "compare platforms", "charting",
    ),
    "debt_budgeting": (
        "payoff", "pay off", "repay", "repayment", "debt reduction",
        "budget", "spending plan", "worksheet", "track spending",
        "emergency fund", "get out of debt",
    ),
    "financial_advice": (
        "advice", "advisor", "planning", "coach", "guidance",
        "portfolio review", "retirement planning",
    ),
    "home_physical": (
        "protect", "cover", "cushion", "absorb", "shield", "barrier",
        "anti-fatigue", "non-slip",
    ),
    "games_entertainment": (
        "play", "entertainment", "playable", "fun", "casual gaming",
    ),
    "ai_content": (
        "write", "writing", "copywriting", "generate content", "draft",
        "rewrite",
    ),
    "software_tools": (
        "track", "organize", "automate", "manage", "monitor", "sync",
        "export", "dashboard",
    ),
}


def _domains_of(text_value: str) -> set:
    lowered = (text_value or "").lower()
    return {domain for domain, words in _DOMAIN_LEXICON.items()
            if any(w in lowered for w in words)}


def _functions_of(text_value: str) -> set:
    lowered = (text_value or "").lower()
    return {domain for domain, words in _PROBLEM_FUNCTIONS.items()
            if any(w in lowered for w in words)}


def _need_domain(need: dict) -> str:
    """The problem domain the BUYER is expressing (from need text only).
    Most-specific-first so 'financial advice need' != 'charting need'."""
    text_value = (f"{need.get('title', '')} "
                  f"{need.get('problem_description', '')} "
                  f"{' '.join(need.get('desired_features') or [])}").lower()
    domains = _domains_of(text_value)
    for preferred in ("home_physical", "financial_advice", "debt_budgeting",
                      "games_entertainment", "ai_content",
                      "trading_markets", "software_tools"):
        if preferred in domains:
            return preferred
    return domains.pop() if domains else "unknown"


def relevance_gate(need: dict, product) -> dict:
    """MANDATORY pre-score gate: does the product demonstrably solve the
    buyer's stated problem? Returns classification + explanation + per-
    dimension reasons. Numeric scores are computed AFTER this and can never
    upgrade a classification.

    Dimensions (spec section 2):
      1. problem alignment    - product's verified domain covers the need's
                                problem domain
      2. desired outcome      - product's verified capabilities cover the
                                function the buyer wants done
      3. functional alignment - verified features cover stated requirements
                                (unevaluable when the need stated none)
      4. audience alignment   - product text speaks to the buyer's audience
      5. purchase context     - a real purchase destination exists
    Missing information DOWNGRADES; it never proves suitability.
    """
    def get(field, default=None):
        if isinstance(product, dict):
            return product.get(field, default)
        return getattr(product, field, default)

    name = (get("name") or "").strip()
    description = (get("description") or "").strip()
    product_text = f"{name} {description}"

    need_domain = _need_domain(need)
    product_domains = _domains_of(product_text)
    product_functions = _functions_of(product_text)
    need_functions = _functions_of(
        f"{need.get('title', '')} {need.get('problem_description', '')}")

    gate_reasons = {}

    # 1. Problem alignment (hard requirement).
    problem_aligned = need_domain in product_domains
    gate_reasons["problem_alignment"] = (
        f"need domain '{need_domain}' vs product domains "
        f"{sorted(product_domains) or ['none identifiable']} -> "
        f"{'pass' if problem_aligned else 'FAIL'}")

    # 2. Desired outcome: buyer's wanted function covered by verified
    #    product capabilities. If the buyer's domain has no function table
    #    entry, the outcome is 'unevaluable' (missing info, not proof).
    want = ({need_domain} if need_domain in _PROBLEM_FUNCTIONS
            else set()) & need_functions
    if want:
        outcome_ok = bool(want & product_functions)
    else:
        outcome_ok = None
    gate_reasons["desired_outcome"] = (
        f"buyer wants {sorted(want) or ['unstated']}; product verifiably "
        f"provides {sorted(product_functions) or ['none']} -> "
        f"{'pass' if outcome_ok else 'FAIL' if outcome_ok is False else 'unevaluable'}")

    # 3. Functional alignment (features).
    feature_tokens = _tokens(" ".join(need.get("desired_features") or []))
    product_tokens = _tokens(product_text)
    feature_overlap = feature_tokens & product_tokens
    if feature_tokens:
        functional_ok = len(feature_overlap) >= max(
            1, len(feature_tokens) // 2)
    else:
        functional_ok = None
    gate_reasons["functional_alignment"] = (
        f"desired features {sorted(feature_tokens)[:6] or ['unstated']}; "
        f"verified overlap {sorted(feature_overlap)[:6]} -> "
        f"{'pass' if functional_ok else 'FAIL' if functional_ok is False else 'unevaluable'}")

    # 4. Audience alignment.
    audience_tokens = _tokens(need.get("target_audience") or "")
    audience_overlap = audience_tokens & product_tokens
    if audience_tokens:
        audience_ok = len(audience_overlap) >= 1
    else:
        audience_ok = None
    gate_reasons["audience_alignment"] = (
        f"audience {sorted(audience_tokens)[:4] or ['unstated']}; overlap "
        f"{sorted(audience_overlap)[:4]} -> "
        f"{'pass' if audience_ok else 'FAIL' if audience_ok is False else 'unevaluable'}")

    # 5. Purchase context.
    has_destination = bool(get("affiliate_url"))
    gate_reasons["purchase_context"] = (
        f"purchase destination {'present' if has_destination else 'missing'}")

    # ------------------------------------------- classification decision
    if not problem_aligned:
        classification = UNRELATED
        explanation = (f"Product's verified text places it in "
                       f"{sorted(product_domains) or ['an unidentifiable']} "
                       f"domain, not the buyer's '{need_domain}' problem "
                       f"domain; it does not solve the stated problem.")
    elif outcome_ok is False:
        classification = UNRELATED
        explanation = ("Product shares the broad problem domain but its "
                       "verified capabilities do not include the outcome "
                       "the buyer wants; shared vocabulary is not solution "
                       "evidence.")
    elif outcome_ok is None and functional_ok is False:
        classification = WEAK
        explanation = ("Same broad domain, but the buyer's requirements "
                       "cannot be confirmed by the product's verified "
                       "description; alignment is superficial.")
    elif outcome_ok and functional_ok is not False and audience_ok is not False:
        if functional_ok and audience_ok and has_destination:
            classification = DIRECT
            explanation = ("Verified product capabilities cover the buyer's "
                           "desired outcome and stated features, fit the "
                           "buyer's audience, and a purchase destination "
                           "exists.")
        else:
            limitations = []
            if functional_ok is None:
                limitations.append("desired features not all confirmed")
            if audience_ok is None:
                limitations.append("audience fit unevaluable")
            if not has_destination:
                limitations.append("no verified purchase destination")
            classification = PARTIAL
            explanation = ("Core outcome appears verifiably satisfied, but: "
                           + "; ".join(limitations) + ".")
    else:
        classification = WEAK
        explanation = ("Some domain similarity, but functional evidence is "
                       "insufficient to claim the product solves the "
                       "buyer's stated problem.")

    return {"classification": classification,
            "explanation": explanation,
            "gate_reasons": gate_reasons}


def match_product(need: dict, product) -> dict:
    """Gate first, then score one candidate product against one need.

    `need` is a buyer_needs row dict; `product` is a Product model or dict
    (verified fields only are read). Returns a transparent verdict dict.
    The numeric score is advisory; the gate classification decides
    promotability (only direct_match qualifies for recommendations).
    """
    gate = relevance_gate(need, product)
    classification = gate["classification"]
    reasons = [f"Relevance gate: {classification.upper()} - "
               f"{gate['explanation']}"]
    gate_detail = "; ".join(f"{k}: {v}"
                             for k, v in gate["gate_reasons"].items())
    reasons.append(f"Gate dimensions: {gate_detail}.")
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
        "classification": classification,
        "gate_explanation": gate["explanation"],
        "gate_reasons": gate["gate_reasons"],
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
    """Evaluate all candidate products for one need; verdicts sorted
    best-first. ONLY direct_match verdicts are recommended, whatever their
    numeric score. Partial matches retained as research findings with
    limitations stated; weak/unrelated are never promotable."""
    verdicts = []
    for product in products:
        verdict = match_product(need, product)
        verdict["product"] = product
        verdict["recommended"] = verdict["classification"] == DIRECT
        verdict["retain_as_research"] = verdict["classification"] in (
            DIRECT, PARTIAL)
        verdicts.append(verdict)
    verdicts.sort(key=lambda v: (
        0 if v["classification"] == DIRECT else
        1 if v["classification"] == PARTIAL else
        2 if v["classification"] == WEAK else 3,
        -v["match_score"]))
    return verdicts
