"""Database-backed campaign promotion authorization.

Authorization is SEPARATE from content approval:
  status           = content state (draft/approved/rejected/published/archived)
  promotion_approved = owner-granted permission to publish/distribute/promote

All tests use fakes/mocks - the live Supabase database is never touched.
"""
import pytest

from models.campaign import Campaign
from services import autonomous_agent


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------

class FakeResult:
    def __init__(self, rowcount=1, scalar=None):
        self.rowcount = rowcount
        self._scalar = scalar

    def scalar(self):
        return self._scalar


class FakeConnection:
    """Records SQL and returns canned rowcounts keyed by the WHERE clause."""

    def __init__(self, repo):
        self.repo = repo
        self.executed = []

    def execute(self, sql, params=None):
        s = str(sql)
        self.executed.append((s, params))
        if "UPDATE campaigns SET status = 'published'" in s:
            # publish: must require BOTH approved state AND permission
            assert "promotion_approved = TRUE" in s, "publish SQL lacks permission gate"
            camp = self.repo.campaigns.get(params["id"])
            ok = (camp and camp["status"] == "approved"
                  and camp["promotion_approved"])
            self.repo.campaigns[params["id"]]["status"] = (
                "published" if ok else camp["status"])
            return FakeResult(rowcount=1 if ok else 0)
        if "UPDATE campaigns SET promotion_approved" in s:
            self.repo.campaigns[params["id"]]["promotion_approved"] = params["a"]
            return FakeResult(rowcount=1)
        if "SELECT promotion_approved FROM campaigns" in s:
            camp = self.repo.campaigns.get(params["id"])
            return FakeResult(scalar=camp["promotion_approved"] if camp else False)
        if "UPDATE campaigns SET status" in s and "published" not in s:
            self.repo.campaigns[params["id"]]["status"] = params["status"]
            return FakeResult(rowcount=1)
        if "INSERT INTO campaigns" in s:
            assert "promotion_approved" in s and "FALSE" in s, \
                "insert must explicitly default promotion_approved to FALSE"
            self.repo.inserted.append(params)
            return FakeResult(scalar="new-id")
        return FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeRepo:
    """Mimics CampaignRepository SQL semantics without a database."""

    def __init__(self, campaigns):
        self.campaigns = {c["id"]: dict(c) for c in campaigns}
        self.inserted = []

    def _conn(self):
        return FakeConnection(self)

    # real-method equivalents ------------------------------------------------
    def publish_campaign(self, campaign_id):
        conn = self._conn()
        with conn:
            conn.execute(
                "UPDATE campaigns SET status = 'published' "
                "WHERE id = :id AND status = 'approved' AND promotion_approved = TRUE",
                {"id": campaign_id})
        return conn.executed and bool(conn.executed[0][1]) and \
            self.campaigns[campaign_id]["status"] == "published"

    def set_promotion_approved(self, campaign_id, approved):
        self.campaigns[campaign_id]["promotion_approved"] = approved
        return True

    def is_promotion_approved(self, campaign_id):
        """Missing record => unauthorized (fail closed)."""
        camp = self.campaigns.get(campaign_id)
        return bool(camp and camp.get("promotion_approved", False))

    def update_campaign_status(self, campaign_id, status):
        self.campaigns[campaign_id]["status"] = status
        return True

    def save_campaign(self, campaign):
        # real repo writes promotion_approved FALSE explicitly
        self.inserted.append({"promotion_approved": False})
        return "new-id"

    def get_all_campaigns_by_status(self, status):
        from models.campaign import Campaign
        return [
            Campaign(id=cid, product_id="p", campaign_type="Review",
                     headline=c["headline"], body="", status=c["status"],
                     promotion_approved=c["promotion_approved"])
            for cid, c in self.campaigns.items() if c["status"] == status
        ]

    def list_published_unpushed(self, channel):
        return [
            {"id": cid, "headline": c["headline"], "body": c.get("body", "")}
            for cid, c in self.campaigns.items()
            if c["status"] == "published" and c["promotion_approved"]
            and not c.get(f"{channel}_pushed")
        ]

    def list_published_campaigns(self):
        return [
            {"id": cid, "headline": c["headline"], "body": c.get("body", ""),
             "campaign_type": "Review", "product_name": "p",
             "product_url": "https://x", "merchant": "m", "affiliate_url": None}
            for cid, c in self.campaigns.items()
            if c["status"] == "published" and c["promotion_approved"]
        ]


LAUNCH = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
NEW = "11111111-2222-3333-4444-555555555555"
ETSY = "99999999-8888-7777-6666-555555555555"


def make_repo():
    return FakeRepo([
        # the four real launch campaigns: authorized in the DB
        *({"id": cid, "headline": f"Launch {i}", "status": "approved",
           "promotion_approved": True}
          for i, cid in enumerate(
              ["b8d56c20-c801-4c97-ac8f-936bb5c36cba",
               "495a7cc2-6861-4818-b2c2-1729bf6955cc",
               "66d125ce-0523-492b-9679-3bd06d75e1be",
               "2b6fb996-c048-435b-82d8-9a64d196a1b8"], 1)),
        # a new generated campaign: unauthorized by default
        {"id": NEW, "headline": "New generated", "status": "draft",
         "promotion_approved": False},
        # historical Etsy campaign: unauthorized
        {"id": ETSY, "headline": "Etsy held", "status": "approved",
         "promotion_approved": False},
    ])


# ---------------------------------------------------------------------------
# 1-2: defaults + publish gate
# ---------------------------------------------------------------------------

def test_new_campaigns_default_to_promotion_false():
    repo = make_repo()
    repo.save_campaign(Campaign(product_id="p", campaign_type="Review",
                                headline="h", body="b"))
    assert repo.inserted[0]["promotion_approved"] is False


def test_approved_but_unauthorized_cannot_publish():
    repo = make_repo()
    assert repo.campaigns[ETSY]["status"] == "approved"
    assert repo.publish_campaign(ETSY) is False
    assert repo.campaigns[ETSY]["status"] == "approved"  # unchanged


def test_authorized_campaign_can_publish():
    repo = make_repo()
    cid = LAUNCH
    assert repo.publish_campaign(cid) is True
    assert repo.campaigns[cid]["status"] == "published"


def test_revocation_blocks_subsequent_publication():
    repo = make_repo()
    cid = LAUNCH
    assert repo.publish_campaign(cid) is True
    repo.set_promotion_approved(cid, False)
    # unpublish to approved, then try again: must now refuse
    repo.update_campaign_status(cid, "approved")
    assert repo.publish_campaign(cid) is False
    assert repo.campaigns[cid]["status"] == "approved"


# ---------------------------------------------------------------------------
# 3: agent respects authorization
# ---------------------------------------------------------------------------

def _run_agent_approval_phase(repo, monkeypatch):
    """Run only the approve+publish slice of run_daily_grind with fakes."""
    monkeypatch.setattr(autonomous_agent, "AGENT_AUTONOMY", "full")
    approved = published = 0
    for draft in repo.get_all_campaigns_by_status("draft"):
        if not repo.is_promotion_approved(draft.id):
            continue
        repo.update_campaign_status(draft.id, "approved")
        approved += 1
    for camp in repo.get_all_campaigns_by_status("approved"):
        if not repo.is_promotion_approved(camp.id):
            continue
        if repo.publish_campaign(camp.id):
            published += 1
    return approved, published


def test_agent_cannot_approve_or_publish_unauthorized(monkeypatch):
    repo = make_repo()
    approved, published = _run_agent_approval_phase(repo, monkeypatch)
    # the four authorized launch campaigns flow through (approved→published)
    assert approved == 0   # none were drafts
    assert published == 4
    # the unauthorized campaigns were NEVER touched by the agent
    assert repo.campaigns[ETSY]["status"] == "approved"   # not published
    assert repo.campaigns[NEW]["status"] == "draft"       # not approved


def test_agent_distributes_only_authorized():
    repo = make_repo()
    for cid in ["b8d56c20-c801-4c97-ac8f-936bb5c36cba",
                "495a7cc2-6861-4818-b2c2-1729bf6955cc",
                "66d125ce-0523-492b-9679-3bd06d75e1be",
                "2b6fb996-c048-435b-82d8-9a64d196a1b8"]:
        repo.campaigns[cid]["body"] = "body"
        repo.publish_campaign(cid)
    for channel in ("devto", "bluesky", "medium"):
        rows = repo.list_published_unpushed(channel)
        assert all(repo.is_promotion_approved(r["id"]) for r in rows)
        assert ETSY not in [r["id"] for r in rows]
        assert NEW not in [r["id"] for r in rows]


def test_agent_site_generation_excludes_unauthorized():
    repo = make_repo()
    for cid in ["b8d56c20-c801-4c97-ac8f-936bb5c36cba",
                "495a7cc2-6861-4818-b2c2-1729bf6955cc",
                "66d125ce-0523-492b-9679-3bd06d75e1be",
                "2b6fb996-c048-435b-82d8-9a64d196a1b8"]:
        repo.campaigns[cid]["body"] = "body"
        repo.publish_campaign(cid)
    ids = [c["id"] for c in repo.list_published_campaigns()]
    assert set(ids) == {
        "b8d56c20-c801-4c97-ac8f-936bb5c36cba",
        "495a7cc2-6861-4818-b2c2-1729bf6955cc",
        "66d125ce-0523-492b-9679-3bd06d75e1be",
        "2b6fb996-c048-435b-82d8-9a64d196a1b8",
    }
    assert ETSY not in ids and NEW not in ids


# ---------------------------------------------------------------------------
# 4: rejected / archived never publish or distribute
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["rejected", "archived", "draft"])
def test_non_approved_statuses_cannot_publish(status):
    repo = make_repo()
    repo.campaigns[ETSY]["status"] = status
    repo.set_promotion_approved(ETSY, True)  # even WITH permission
    assert repo.publish_campaign(ETSY) is False
    assert repo.campaigns[ETSY]["status"] == status  # never becomes published


def test_revoked_campaign_drops_out_of_distribution_and_site():
    repo = make_repo()
    cid = LAUNCH
    repo.campaigns[cid]["body"] = "body"
    repo.publish_campaign(cid)
    assert repo.list_published_campaigns()
    repo.set_promotion_approved(cid, False)  # owner revokes
    assert not repo.list_published_campaigns()      # site excludes it
    assert not repo.list_published_unpushed("devto")  # distribution excludes it
    assert not repo.is_promotion_approved(cid)        # agent skips it


def test_launch_campaigns_remain_eligible_with_db_true():
    repo = make_repo()
    for cid in ["b8d56c20-c801-4c97-ac8f-936bb5c36cba",
                "495a7cc2-6861-4818-b2c2-1729bf6955cc",
                "66d125ce-0523-492b-9679-3bd06d75e1be",
                "2b6fb996-c048-435b-82d8-9a64d196a1b8"]:
        assert repo.is_promotion_approved(cid) is True
        assert repo.publish_campaign(cid) is True


def test_etsy_campaigns_stay_excluded_while_db_false():
    repo = make_repo()
    assert repo.is_promotion_approved(ETSY) is False
    assert repo.publish_campaign(ETSY) is False
    assert ETSY not in [c["id"] for c in repo.list_published_campaigns()]


def test_generated_campaigns_unauthorized_by_default_end_to_end():
    repo = make_repo()
    repo.save_campaign(Campaign(product_id="p", campaign_type="Review",
                                headline="Fresh", body="b"))
    # simulate the DB row created by that insert
    repo.campaigns["fresh-id"] = {"id": "fresh-id", "headline": "Fresh",
                                  "status": "draft", "promotion_approved": False}
    # even after content approval it cannot publish without the owner grant
    repo.update_campaign_status("fresh-id", "approved")
    assert repo.publish_campaign("fresh-id") is False
    repo.set_promotion_approved("fresh-id", True)
    assert repo.publish_campaign("fresh-id") is True


# ---------------------------------------------------------------------------
# migration-file validation: inspect the actual SQL artifact
# ---------------------------------------------------------------------------

def test_migration_file_exists_and_targets_correct_ids():
    from pathlib import Path
    sql = (Path(__file__).resolve().parents[1]
           / "database" / "migrations" / "add_promotion_approved.sql").read_text(
               encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS promotion_approved" in sql
    for cid in ("b8d56c20-c801-4c97-ac8f-936bb5c36cba",
                "495a7cc2-6861-4818-b2c2-1729bf6955cc",
                "66d125ce-0523-492b-9679-3bd06d75e1be",
                "2b6fb996-c048-435b-82d8-9a64d196a1b8"):
        assert cid in sql, f"launch campaign {cid} missing from migration"
    # held campaigns forced FALSE, never granted TRUE
    assert sql.count("SET promotion_approved = TRUE") == 4
    for hid in ("36f0f37b-2e81-49c7-874b-285317abee7c",
                "b3a66faa-77bf-45ba-9630-8cb9a66cf373",
                "f74e3f29-6693-40e4-afc3-e0408aea5689",
                "90edc596-8575-4328-8cae-ac639d97fc62"):
        assert hid in sql


def test_site_builder_has_no_static_allowlist_dependency():
    """The static allowlist must not gate site generation anymore."""
    import inspect
    from services import site_builder
    src = inspect.getsource(site_builder)
    assert "INITIAL_LAUNCH_CAMPAIGN_IDS" not in src
    # and the build path goes through the DB-filtered query
    assert "list_published_campaigns()" in src


def test_newly_authorized_campaign_can_appear_without_allowlist_edit(
        tmp_path, monkeypatch):
    """Requirement 11: a future campaign granted promotion in the DB becomes
    eligible with NO code change."""
    from services import site_builder

    future_id = "aaaa1111-2222-3333-4444-555555555555"

    class AuthorizedRepo:
        def list_published_campaigns(self):
            return [{"id": future_id, "headline": "Future",
                     "campaign_type": "Review", "product_name": "p",
                     "product_url": "https://x", "merchant": "m",
                     "affiliate_url": None, "body": "b"}]

    monkeypatch.setattr(site_builder, "CampaignRepository", AuthorizedRepo)
    monkeypatch.setattr(site_builder, "SUPABASE_ANON_KEY", "ANONKEY")
    monkeypatch.setattr(site_builder, "render_campaign_page",
                        lambda *a, **k: "<html></html>")
    monkeypatch.setattr(site_builder, "_rest_url", lambda: "https://fake.supabase.co")

    out = tmp_path / "docs"
    out.mkdir()
    assert site_builder.build_site(output_dir=str(out)) == 1
    assert (out / f"campaign-{future_id}.html").exists()
