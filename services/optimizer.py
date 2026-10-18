"""Kill/scale decision rules for the autonomous agent.

Measured by what works:
- clicks            -> winner  (multiply with new angles)
- views, no clicks  -> revive  (one fresh angle)
- many views, still no clicks, old enough -> kill (archive, stop serving)
The flag column keeps every rule idempotent (runs once per campaign).
"""

WINNER_VARIANT_ANGLES = ("Comparison", "Promo")
MAX_WINNER_VARIANTS = 2


def decide_action(views: int, clicks: int, age_days: int, flag) -> str:
    """Return 'winner', 'revive', 'kill', or None."""
    if clicks >= 1 and flag is None:
        return "winner"
    if clicks == 0 and views >= 10 and age_days >= 7 and flag in (None, "revived"):
        return "kill"
    if clicks == 0 and views >= 3 and age_days >= 3 and flag is None:
        return "revive"
    if flag:
        return None
    return None