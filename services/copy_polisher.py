"""AI copy polish: makes campaign copy sound human while keeping it FACT-LOCKED.

Contract (guardrail #3): the LLM may ONLY rephrase around facts we hand it.
It may never invent a number, price, or claim. We enforce this mechanically:

  1. Only LOCKED facts (name, merchant, price, extracted description) go in
     the prompt. The model rewrites the template's framing, not the facts.
  2. Every number that appears in the AI output must also appear in the
     locked facts. Anything new -> the output is REJECTED and we fall back
     to the deterministic template. No hallucinated prices, ever.
  3. No API key -> template copy, exactly as before. The system degrades
     to today's behavior with zero code-path change for the caller.
"""
import logging
import re

import requests

from config.settings import COPY_AI_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)

_TIMEOUT = 30
_MAX_TOKENS = 700

_SYSTEM_PROMPT = (
    "You are a commerce copy editor. You rewrite product-review copy so it "
    "reads naturally, like a human wrote it. HARD RULES:\n"
    "- Use ONLY the facts given. Do not invent, add, or estimate any number, "
    "price, statistic, date, or claim.\n"
    "- If the given price is unknown, write around it (e.g. 'check the live "
    "page'); never guess.\n"
    "- Keep the same section headings and overall structure.\n"
    "- Keep the markdown formatting (## headings, - bullets).\n"
    "- Disclose clearly that it is a review/opinion, not a seller ad.\n"
    "- Return only the rewritten body text, nothing else."
)


def _numbers_in(text: str) -> set:
    """All standalone numbers in a string (prices, quantities, percentages)."""
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def _facts_allow_all_numbers(text: str, locked_facts: list) -> bool:
    """Every number in the AI text must exist in the locked facts. This is
    the hallucination gate: one new number = rejected output."""
    allowed = set()
    for fact in locked_facts:
        if fact:
            allowed |= _numbers_in(str(fact))
    return _numbers_in(text) <= allowed


def polish_headline(headline: str, facts: dict) -> str:
    """Humanize a headline. Returns the original on any failure."""
    if not OPENAI_API_KEY:
        return headline
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": COPY_AI_MODEL,
                "messages": [
                    {"role": "system", "content":
                        "Rewrite this product-review headline so it sounds "
                        "human and specific. Use ONLY the facts given - never "
                        "invent a number, price, or claim. Return only the "
                        "headline text."},
                    {"role": "user", "content":
                        f"Headline: {headline}\nFacts: {facts}"},
                ],
                "max_tokens": 80,
                "temperature": 0.8,
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.info("Headline polish refused: HTTP %s", resp.status_code)
            return headline
        polished = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        if not polished or len(polished) > 200:
            return headline
        if not _facts_allow_all_numbers(polished, list(facts.values())):
            logger.info("Headline polish rejected (invented numbers).")
            return headline
        return polished
    except Exception as exc:
        logger.info("Headline polish failed: %s", type(exc).__name__)
        return headline


def polish_body(body: str, facts: dict) -> str:
    """Humanize a campaign body. Returns the original template on any
    failure or any hallucinated number - template is always the safe floor."""
    if not OPENAI_API_KEY:
        return body
    locked_values = [str(v) for v in facts.values() if v]
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": COPY_AI_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content":
                        f"Rewrite this. Locked facts (do not change or invent "
                        f"numbers beyond these): {facts}\n\nBody:\n{body}"},
                ],
                "max_tokens": _MAX_TOKENS,
                "temperature": 0.7,
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.info("Body polish refused: HTTP %s", resp.status_code)
            return body
        polished = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        if not polished or len(polished) < 40:
            return body
        if not _facts_allow_all_numbers(polished, locked_values):
            logger.info("Body polish REJECTED: AI invented a number not in "
                        "the locked facts. Falling back to template copy.")
            return body
        return polished
    except Exception as exc:
        logger.info("Body polish failed: %s", type(exc).__name__)
        return body
