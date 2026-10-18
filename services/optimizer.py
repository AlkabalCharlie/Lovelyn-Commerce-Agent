"""Kill/scale decision rules for the autonomous agent."""


def decide_action(views: int, clicks: int, age_days: int, flag) -> str:
    """Return 'winner', 'revive', or None (do nothing). Idempotent via flag."""
    if flag:
        return None
    if clicks >= 1:
        return "winner"
    if views >= 3 and age_days >= 3:
        return "revive"
    return None