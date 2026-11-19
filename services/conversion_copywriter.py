"""Conversion copywriter: AI rewrite of LIVE campaign copy to sell, not just
describe, with a daily budget so it never burns tokens on rewrites that cost
more than the page earns.

Guardrails (same contract as copy_polisher, kept intentionally):
- FACT-LOCKED: only locked facts (name, merchant, price, description,
  affiliate presence) enter the prompt; every number in the AI output must
  exist in the locked facts or the rewrite is REJECTED and the campaign
  keeps its current copy. No hallucinated prices, ever.
- Budget-capped: at most COPY_REFRESH_DAILY_LIMIT pages per run, preferring
  pages that get views but zero clicks (impressions wasted on weak copy).
- Traffic-aware: pages with zero views are NOT polished (nothing is learned
  from rewriting a page nobody saw); they are handled by the REWRITE path.
- No API key -> no-op. The system degrades to today's behavior.
- Copy updates NEVER change status, promotion approval, or attribution.
"""
import logging

import requests

from services.copy_polisher import _facts_allow_all_numbers

logger = logging.getLogger(__name__)

# Tune via env. 0 or unset disables the refresh entirely.
DEFAULT_DAILY_LIMIT = 3

_CONVERSION_SYSTEM_PROMPT = (
    "You are a direct-response copywriter for affiliate review pages. "
    "Rewrite the page body to convert readers into buyers. HARD RULES:\n"
    "- Use ONLY the facts given. Never invent, add, or estimate a number, "
    "price, statistic, date, or claim.\n"
    "- Lead with the reader's problem, then show how this product solves it, "
    "then one concrete next step.\n"
    "- Address the reader as 'you'. Short sentences. No hype words like "
    "'amazing' or 'revolutionary'.\n"
    "- Be honest: say who this product is NOT for. Honest limits build trust "
    "that converts.\n"
    "- Keep markdown formatting (## headings, - bullets) and roughly the "
    "same length (max 1.5x the original).\n"
    "- Keep or strengthen the call to action near the top and the bottom.\n"
    "- Return only the rewritten body text."
)


def should_refresh(row: dict, refreshed_ids: set) -> bool:
    """Pick the pages most worth spending copy budget on today.

    Preference: views-but-no-clicks (people read it and did not act ->
    the copy is the problem), then any underperforming live page.
    Never pages with zero views (no signal) or already refreshed today."""
    if str(row["id"]) in refreshed_ids:
        return False
    if (row.get("views") or 0) == 0:
        return False
    return True


def rewrite_for_conversion(headline: str, body: str, facts: dict,
                           clicks: int, revenue_cents: int) -> tuple | None:
    """Returns (headline, body) rewritten to convert, or None to keep the
    current copy (any failure, budget refusal, or hallucinated number)."""
    import os

    from config.settings import OPENAI_API_KEY, COPY_AI_MODEL

    if not OPENAI_API_KEY:
        return None
    limit = int(os.getenv("COPY_REFRESH_DAILY_LIMIT", str(DEFAULT_DAILY_LIMIT)) or 0)
    if limit <= 0:
        return None
    if revenue_cents > 0:
        return None  # already converting - do not touch a working page
    locked_values = [str(v) for v in facts.values() if v]
    try:
        import requests
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": COPY_AI_MODEL,
                "messages": [
                    {"role": "system", "content": _CONVERSION_SYSTEM_PROMPT},
                    {"role": "user", "content":
                        f"Locked facts (never invent numbers beyond these): {facts}\n"
                        f"Current headline: {headline}\n"
                        f"This page got {clicks} click(s) total. Rewrite the body "
                        f"to convert.\n\nCurrent body:\n{body}"},
                ],
                "max_tokens": 900,
                "temperature": 0.7,
            },
            timeout=45,
        )
        if resp.status_code != 200:
            logger.info("Conversion rewrite refused: HTTP %s", resp.status_code)
            return None
        new_body = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        if not new_body or len(new_body) < 40:
            return None
        if len(new_body) > len(body) * 2 + 500:
            return None  # runaway length -> reject
        if not _facts_allow_all_numbers(new_body, locked_values):
            logger.info("Conversion rewrite REJECTED: invented a number not in "
                        "the locked facts.")
            return None
        return headline, new_body
    except Exception as exc:
        logger.info("Conversion rewrite failed: %s", type(exc).__name__)
        return None
