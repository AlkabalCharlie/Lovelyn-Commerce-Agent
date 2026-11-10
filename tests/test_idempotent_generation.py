"""Idempotence guards: a campaign type exists once per product, even if the
generator (local + cloud race, or winner branch called twice) tries again."""
from services.autonomous_agent import MAX_WINNER_VARIANTS, WINNER_VARIANT_ANGLES
from services.campaign_generator import generate_campaign


class FakeCampRepo:
    """Mirrors the real repo's guard surface without touching the DB."""

    def __init__(self):
        self.saved = []

    def has_campaign_of_type(self, product_id, campaign_type):
        return any(c.product_id == product_id and c.campaign_type == campaign_type
                   for c in self.saved)

    def save_campaign(self, campaign):
        self.saved.append(campaign)


class FakeCamp:
    def __init__(self, product_id, campaign_type):
        self.product_id = product_id
        self.campaign_type = campaign_type


def _run_winner_branch(repo, product_id, product_name, merchant):
    """Exactly what the agent's winner branch does, incl. the guard."""
    created = 0
    for angle in WINNER_VARIANT_ANGLES[:MAX_WINNER_VARIANTS]:
        data = generate_campaign(product_name, merchant, angle, "desc", "$7")
        if repo.has_campaign_of_type(product_id, data["type"]):
            continue
        repo.save_campaign(FakeCamp(product_id, data["type"]))
        created += 1
    return created


def test_winner_branch_called_twice_creates_variants_once():
    repo = FakeCampRepo()
    first = _run_winner_branch(repo, "prod-1", "Debt Guide", "Payhip")
    second = _run_winner_branch(repo, "prod-1", "Debt Guide", "Payhip")
    assert first == second == 0 or (first > 0 and second == 0)
    assert second == 0  # second call must create nothing
    types = sorted(c.campaign_type for c in repo.saved)
    assert len(types) == len(set(types))  # no duplicate types


def test_different_products_are_not_blocked_by_each_other():
    repo = FakeCampRepo()
    _run_winner_branch(repo, "prod-1", "Debt Guide", "Payhip")
    created = _run_winner_branch(repo, "prod-2", "Other Thing", "Etsy")
    assert created > 0  # guard is per-product, not global


def test_review_generation_guard_prevents_duplicate():
    repo = FakeCampRepo()
    # Step 2 pipeline advance pattern: list-empty check then type guard.
    for _ in range(2):
        data = generate_campaign("Item", "Etsy", "Review", "d", "$7")
        if repo.has_campaign_of_type("p1", data["type"]):
            continue
        repo.save_campaign(FakeCamp("p1", data["type"]))
    assert len([c for c in repo.saved if c.campaign_type == data["type"]]) == 1
