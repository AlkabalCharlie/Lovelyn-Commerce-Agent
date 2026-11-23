"""AIDA buyer-intent classification + 100-point scoring.

Pure functions, no network, no database: fully unit-testable.

Contract:
- AIDA stage and the numeric score are stored SEPARATELY (a stage is a
  qualitative position in the buyer journey, not a score bucket).
- Every point awarded carries the phrase that earned it (evidence), so the
  score is always explainable and auditable.
- Observed facts (matched phrases) are returned separately from inferred
  intent (stage conclusions), so downstream code never blurs the two.
- Ordinary curiosity without purchase signals never reaches 'action'.
"""
import hashlib
import re

# ---------------------------------------------------------------- AIDA stages
ATTENTION = "attention"   # problem expressed, no solution sought yet
INTEREST = "interest"     # actively researching how to solve it
DESIRE = "desire"         # specific desired outcome / features expressed
ACTION = "action"         # explicit buying signal
NONE = "none"             # no buyer-relevant signal

# ------------------------------------------------------- signal phrase tables
# Ordered strongest-last within each stage; matching is lowercase substring.
PROBLEM_SIGNALS = (
    "struggling with", "having trouble", "stuck with", "frustrated",
    "keeps failing", "can't seem to", "pain point", "annoying",
    "waste of time", "so hard to", "hate that", "problem with",
)
RESEARCH_SIGNALS = (
    "how do i", "how can i", "how to", "any way to", "is there a way",
    "looking for", "does anyone know", "any advice", "tips for",
    "which tool", "which app",
)
COMPARISON_SIGNALS = (
    " vs ", "versus", "compared to", "better than", "alternative to",
    "pros and cons", "which is better", "difference between",
)
DESIRED_OUTCOME_SIGNALS = (
    "i want something that", "looking for something that", "i need it to",
    "would be perfect if", "i wish it had", "must have", "needs to support",
    "budget of", "under $", "around $", "cheap", "affordable",
)
OBJECTION_SIGNALS = (
    "but i'm worried", "not sure if worth", "scam", "refund policy",
    "free trial", "is it safe", "reviews say", "bad reviews",
    "too expensive", "don't want to pay",
)
PURCHASE_SIGNALS = (
    "where can i buy", "where to buy", "where do i get", "buy link",
    "which one should i purchase", "which should i buy", "ready to buy",
    "going to buy", "ordering", "just bought", "worth the price",
    "worth buying", "is there a cheaper", "cheaper alternative",
    "purchase link", "where can i get", "can i buy",
)

SCORE_WEIGHTS = {
    "identifiable_problem": 10,
    "need_specificity": 10,
    "active_solution_research": 15,
    "urgency_or_pain_intensity": 15,
    "desired_outcome": 15,
    "comparison_or_recommendation": 15,
    "explicit_purchase_signals": 20,
}
# Duplicate/low-value markers reduce specificity credit.
VAGUE_MARKERS = ("something", "anything", "whatever", "idk", "not sure what")


def classify_aida(text: str) -> tuple:
    """Return (stage, matched_signal_phrases).

    Rules:
    - 'action' requires an explicit purchase signal — curiosity never counts.
    - 'desire' requires a stated outcome/feature/budget/objection signal.
    - 'interest' requires research/comparison behaviour beyond naming a pain.
    - 'attention' is a stated problem with no solution-seeking.
    """
    lowered = f" {(text or '').lower()} "
    matched = {stage: [] for stage in ("problem", "research", "comparison",
                                       "desire", "objection", "purchase")}
    for phrase in PROBLEM_SIGNALS:
        if phrase in lowered:
            matched["problem"].append(phrase)
    for phrase in RESEARCH_SIGNALS:
        if phrase in lowered:
            matched["research"].append(phrase)
    for phrase in COMPARISON_SIGNALS:
        if phrase in lowered:
            matched["comparison"].append(phrase)
    for phrase in DESIRED_OUTCOME_SIGNALS:
        if phrase in lowered:
            matched["desire"].append(phrase)
    for phrase in OBJECTION_SIGNALS:
        if phrase in lowered:
            matched["objection"].append(phrase)
    for phrase in PURCHASE_SIGNALS:
        if phrase in lowered:
            matched["purchase"].append(phrase)

    if matched["purchase"]:
        return ACTION, matched
    if matched["desire"] or matched["objection"]:
        return DESIRE, matched
    if matched["research"] or matched["comparison"]:
        return INTEREST, matched
    if matched["problem"]:
        return ATTENTION, matched
    return NONE, matched


def _find_evidence(text: str, phrases):
    lowered = f" {(text or '').lower()} "
    return [p for p in phrases if p in lowered]


def _has_specifics(text: str) -> bool:
    """Specificity heuristic: numbers, prices, named products, or concrete
    feature words — and none of the vague markers."""
    lowered = (text or "").lower()
    if any(m in lowered for m in VAGUE_MARKERS):
        return False
    return bool(re.search(r"(\d|\$|gb|hour|day|week|month|year|free|paid)",
                          lowered))


URGENCY_SIGNALS = (
    "urgent", "asap", "as soon as possible", "tomorrow", "today",
    "this week", "deadline", "losing money", "losing customers",
    "about to give up", "at my wit's end", "driving me crazy",
    "every day", "constantly",
)


def score_buyer_intent(text: str) -> dict:
    """Transparent 100-point buyer-intent score.

    Returns:
        score: int 0-100
        stage: AIDA stage (kept separate from the score)
        evidence: {component: [matched phrases]} for EVERY point awarded
        reasoning: ordered human-readable explanation
        observed: list of directly observed facts (matched phrases)
        inferred: list of inferred conclusions (not direct observations)
    """
    evidence = {}
    reasoning = []
    observed = []
    inferred = []

    def award(component, phrases_found):
        evidence[component] = phrases_found
        observed.extend(phrases_found)
        reasoning.append(
            f"{component.replace('_', ' ').title()} "
            f"(+{SCORE_WEIGHTS[component]}): matched "
            f"{', '.join(repr(p) for p in phrases_found[:3])}.")

    stage, matched = classify_aida(text)
    lowered = f" {(text or '').lower()} "
    score = 0

    # 1. Identifiable problem (10): a DIRECT pain statement earns it;
    #    solution-seeking language implies a problem only as a fallback
    #    (inference recorded, not quietly upgraded to an observation).
    problem_hits = _find_evidence(text, PROBLEM_SIGNALS)
    if problem_hits:
        award("identifiable_problem", problem_hits[:3])
        score += SCORE_WEIGHTS["identifiable_problem"]
    elif matched["research"] or matched["desire"] or matched["purchase"]:
        evidence["identifiable_problem"] = ["(inferred) problem implied by "
                                            "solution-seeking language"]
        inferred.append("Problem implied by solution-seeking language; no "
                        "pain stated directly.")
        score += SCORE_WEIGHTS["identifiable_problem"]
        reasoning.append("Identifiable problem (+10, inferred): implied by "
                         "solution-seeking language.")

    # 2. Specificity of need (10)
    if _has_specifics(text):
        specifics = re.findall(r"[\$]?\d[\d,.]*\s?(?:gb|k|hr|h|d)?|under \$?\d+",
                               lowered)[:3]
        evidence["need_specificity"] = specifics or ["concrete specifics present"]
        observed.extend(evidence["need_specificity"])
        reasoning.append("Need specificity (+10): contains concrete numbers, "
                         "prices or constraints.")
        score += SCORE_WEIGHTS["need_specificity"]
    else:
        reasoning.append("Need specificity (+0): no concrete numbers, prices "
                         "or constraints; request is vague.")

    # 3. Active solution research (15)
    research_hits = _find_evidence(text, RESEARCH_SIGNALS + COMPARISON_SIGNALS)
    if research_hits:
        award("active_solution_research", research_hits[:3])
        score += SCORE_WEIGHTS["active_solution_research"]

    # 4. Urgency or pain intensity (15)
    urgency_hits = _find_evidence(text, URGENCY_SIGNALS)
    if urgency_hits:
        award("urgency_or_pain_intensity", urgency_hits[:3])
        score += SCORE_WEIGHTS["urgency_or_pain_intensity"]
    else:
        reasoning.append("Urgency/pain intensity (+0): no urgency language.")

    # 5. Clearly expressed desired outcome (15)
    desire_hits = _find_evidence(text, DESIRED_OUTCOME_SIGNALS)
    if desire_hits:
        award("desired_outcome", desire_hits[:3])
        score += SCORE_WEIGHTS["desired_outcome"]

    # 6. Product comparison / recommendation requests (15)
    comparison_hits = _find_evidence(text, COMPARISON_SIGNALS) or (
        ["request for recommendations"] if "recommend" in lowered else [])
    if comparison_hits:
        award("comparison_or_recommendation", comparison_hits[:3])
        score += SCORE_WEIGHTS["comparison_or_recommendation"]

    # 7. Explicit purchase signals (20) — the strongest single component
    purchase_hits = _find_evidence(text, PURCHASE_SIGNALS)
    if purchase_hits:
        award("explicit_purchase_signals", purchase_hits[:3])
        score += SCORE_WEIGHTS["explicit_purchase_signals"]

    score = min(100, score)

    # Stage-specific inferences (clearly labelled as inference)
    if stage == ACTION:
        inferred.append("Buyer is at the action stage: explicit purchase "
                        "language observed.")
    elif stage == DESIRE:
        inferred.append("Buyer has a formed desired outcome; likely "
                        "receptive to a well-fitted product.")
    elif stage == INTEREST:
        inferred.append("Buyer is actively researching solutions; education "
                        "first, product second.")
    elif stage == ATTENTION:
        inferred.append("Problem awareness only; nurture with useful content "
                        "rather than a product pitch.")

    return {
        "score": score,
        "stage": stage,
        "evidence": evidence,
        "reasoning": reasoning,
        "observed": observed,
        "inferred": inferred,
    }


def confidence_for(evidence_count: int, score: int) -> str:
    """Where evidence is thin, confidence drops rather than inventing
    certainty. A single author is never 'high' confidence regardless of
    score; low scores stay low even with many sources (volume is not
    intent)."""
    if evidence_count >= 3 and score >= 60:
        return "high"
    if evidence_count >= 2 and score >= 40:
        return "medium"
    return "low"


def score_band(score: int) -> str:
    if score >= 80:
        return "high_intent"
    if score >= 60:
        return "strong_opportunity"
    if score >= 40:
        return "developing_demand"
    return "early_awareness"


def dedupe_key(source: str, url: str, author: str, title: str) -> str:
    """Stable content address for duplicate detection (sha256 hex, 32 chars)."""
    normalized = "|".join([
        (source or "").strip().lower(),
        (url or "").strip().lower().rstrip("/"),
        (author or "").strip().lower(),
        (title or "").strip().lower(),
    ])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def cluster_key_for(title: str, body: str = "") -> str:
    """Stable slug key for grouping related discussions into one buyer need.
    Uses the first distinctive tokens (stopwords stripped) so paraphrased
    posts cluster together while unrelated ones do not."""
    tokens = re.findall(r"[a-z0-9]{4,}", f"{title} {body}".lower())
    stopwords = {"about", "after", "this", "that", "with", "have", "what",
                 "when", "where", "which", "would", "could", "there",
                 "their", "been", "being", "some", "then", "them", "they",
                 "from", "your", "will", "just", "like", "need", "want",
                 "best", "good", "anyone", "recommend", "buy", "looking",
                 "shopping", "advice"}
    distinctive = []
    seen = set()
    for tok in tokens:
        if tok in stopwords or tok in seen:
            continue
        seen.add(tok)
        distinctive.append(tok)
        if len(distinctive) == 3:
            break
    # Prefer the FIRST distinctive tokens after stopwords; "best/good" etc.
    # are already stopwords so paraphrases line up on the shared head noun
    # phrase. Longer tails ("...recommendations") share the PREFIX with the
    # canonical key, so prefix-4-token keys group related posts.
    canonical = distinctive[:4]
    if not canonical:
        canonical = ["uncategorized"]
    return "-".join(canonical)
