"""Demand scoring and approved-product matching.

This module is deliberately independent of the database and external APIs.
It scores discovered conversations against verified product information.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because",
    "been", "before", "being", "between", "but", "can", "could",
    "did", "does", "doing", "for", "from", "get", "got", "had",
    "has", "have", "help", "here", "how", "into", "its", "just",
    "like", "looking", "make", "many", "more", "most", "much",
    "need", "not", "now", "off", "our", "out", "please", "really",
    "same", "some", "than", "that", "the", "their", "them",
    "there", "these", "they", "this", "those", "through", "too",
    "very", "want", "was", "way", "were", "what", "when", "where",
    "which", "while", "who", "why", "will", "with", "would", "you",
    "your",
}

INTENT_SIGNALS = {
    "seeking_solution": (
        "how do i", "how can i", "how to", "help me", "need a solution",
        "struggling with", "having trouble", "trying to",
    ),
    "recommendation": (
        "recommend", "recommendation", "any suggestions", "what do you use",
        "what should i use", "which one should", "looking for a tool",
        "looking for a way",
    ),
    "comparison": (
        "versus", " vs ", "compared to", "better than", "alternative to",
        "which is better", "pros and cons",
    ),
    "purchase": (
        "where can i buy", "where to buy", "ready to buy", "want to buy",
        "planning to buy", "purchase", "pricing", "how much does",
        "is it worth buying",
    ),
}

INTENT_POINTS = {
    "seeking_solution": 12,
    "recommendation": 22,
    "comparison": 24,
    "purchase": 35,
}


def _get(product: Any, field: str, default: Any = None) -> Any:
    """Read a field from either a Product object or a dictionary."""
    if isinstance(product, dict):
        return product.get(field, default)
    return getattr(product, field, default)


def _tokens(value: str) -> set:
    words = re.findall(r"[a-z0-9]+", (value or "").lower())
    return {word for word in words if len(word) > 2 and word not in STOP_WORDS}


def _intent_assessment(text: str) -> Tuple[int, List[str], List[str]]:
    lowered = f" {text.lower()} "
    points = 0
    signals = []
    categories = []

    for category, phrases in INTENT_SIGNALS.items():
        matches = [phrase.strip() for phrase in phrases if phrase in lowered]
        if matches:
            categories.append(category)
            points = max(points, INTENT_POINTS[category])
            signals.extend(matches[:2])

    # Explicit commercial urgency is an additional, capped signal.
    urgency_phrases = (
        "as soon as possible", "urgent", "today", "this week",
        "before the end of the month",
    )
    urgency = [phrase for phrase in urgency_phrases if phrase in lowered]
    if urgency:
        points += 5
        signals.extend(urgency[:1])

    return min(points, 40), categories, signals


def _product_keywords(product: Any) -> set:
    """Use verified product data; description carries more weight than name."""
    description = _get(product, "description", "") or ""
    name = _get(product, "name", "") or ""

    description_tokens = _tokens(description)
    name_tokens = _tokens(name)

    # Name terms help identify a product, but do not dominate its relevance.
    return description_tokens | name_tokens


def score_demand(
    title: str,
    body: str,
    products: Iterable[Any],
    subreddit: str = "",
) -> Dict[str, Any]:
    """Return the strongest approved-product match for a discovered post.

    Score is out of 100:
      - Product relevance: up to 60
      - Purchase intent: up to 40

    A product is not matched merely because its name appears in a post.
    At least two meaningful product terms must overlap.
    """
    post_text = f"{title or ''} {body or ''}".strip()
    post_tokens = _tokens(post_text)

    if not post_tokens:
        return {
            "qualified": False,
            "score": 0,
            "intent_score": 0,
            "relevance_score": 0,
            "intent_categories": [],
            "matched_product_id": None,
            "matched_product_name": None,
            "reasons": ["The post contains no meaningful searchable terms."],
            "subreddit": subreddit,
        }

    intent_score, intent_categories, intent_signals = (
        _intent_assessment(post_text)
    )

    best_match: Optional[Dict[str, Any]] = None

    for product in products:
        if _get(product, "status", "approved") != "approved":
            continue

        product_tokens = _product_keywords(product)
        overlap = post_tokens & product_tokens

        if len(overlap) < 2:
            continue

        # F1 balances how much of the post and product description overlaps.
        precision = len(overlap) / len(post_tokens)
        recall = len(overlap) / max(1, len(product_tokens))
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0
        )
        relevance_score = min(60, round(f1 * 120))
        total_score = min(100, relevance_score + intent_score)

        reasons = [
            f"Shared product-related terms: {', '.join(sorted(overlap))}.",
            f"Product relevance: {relevance_score}/60.",
            f"Purchase intent: {intent_score}/40.",
        ]
        if intent_signals:
            reasons.append(
                "Buying signals: " + ", ".join(intent_signals) + "."
            )

        candidate = {
            "qualified": relevance_score >= 15 and total_score >= 25,
            "score": total_score,
            "intent_score": intent_score,
            "relevance_score": relevance_score,
            "intent_categories": intent_categories,
            "matched_product_id": _get(product, "id"),
            "matched_product_name": _get(product, "name"),
            "reasons": reasons,
            "matched_terms": sorted(overlap),
            "subreddit": subreddit,
        }

        if best_match is None or candidate["score"] > best_match["score"]:
            best_match = candidate

    if best_match is None:
        return {
            "qualified": False,
            "score": intent_score,
            "intent_score": intent_score,
            "relevance_score": 0,
            "intent_categories": intent_categories,
            "matched_product_id": None,
            "matched_product_name": None,
            "reasons": [
                "No approved product had enough meaningful overlap "
                "with this conversation."
            ],
            "subreddit": subreddit,
        }

    return best_match