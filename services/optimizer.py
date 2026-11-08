"""Kill/scale decision rules for the autonomous agent.

Revenue-aware: campaigns judged by money logged, not just clicks.
Clicks are still signals, but revenue is the truth.
"""

WINNER_VARIANT_ANGLES = ("Comparison", "Promo")
MAX_WINNER_VARIANTS = 2

# Thresholds
MIN_VIEWS_TO_JUDGE = 5
MIN_AGE_DAYS = 3
REVENUE_THRESHOLD_CENTS = 100  # $1 minimum to count as "earning"


def decide_action(views: int, clicks: int, age_days: int, flag, revenue_cents: int = 0) -> str:
    """Return 'winner', 'revive', 'kill', or None."""
    # Revenue trumps everything
    if revenue_cents >= REVENUE_THRESHOLD_CENTS and flag is None:
        return "winner"
    
    # Clicks without revenue still count as winner (affiliate sales may lag)
    if clicks >= 1 and flag is None:
        return "winner"
    
    # Kill: many views, no clicks, no revenue, old enough
    if clicks == 0 and revenue_cents == 0 and views >= 10 and age_days >= 7 and flag in (None, "revived"):
        return "kill"
    
    # Revive: some views, no action yet
    if clicks == 0 and revenue_cents == 0 and views >= 3 and age_days >= 3 and flag is None:
        return "revive"
    
    if flag:
        return None
    return None


def check_milestones(total_cents: int, flag: str = None) -> list:
    """Return list of newly crossed milestones."""
    if flag == "milestone_celebrated":
        return []
    from config.settings import MILESTONE_THRESHOLDS_CENTS
    crossed = []
    for threshold in MILESTONE_THRESHOLDS_CENTS:
        if total_cents >= threshold:
            crossed.append(threshold)
    return crossed