from models.campaign import Campaign
from services import autonomous_agent


def test_daily_grind_promotes_only_db_authorized_campaigns(monkeypatch):
    launch_id = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
    held_id = "36f0f37b-2e81-49c7-874b-285317abee7c"
    AUTHORIZED = {launch_id}          # DB says: launch authorized, held not
    launch = Campaign("launch-product", "Review", "Launch", "", id=launch_id,
                      promotion_approved=True)
    held = Campaign("held-product", "Review", "Held", "", id=held_id,
                    promotion_approved=False)
    status_changes = []
    published_channels = []

    class FakeProducts:
        def list_products_missing_enrichment(self):
            return []

        def list_products(self):
            return []

    class FakeCampaigns:
        def get_all_campaigns_by_status(self, status):
            return [launch, held]

        def is_promotion_approved(self, campaign_id):
            return campaign_id in AUTHORIZED

        def update_campaign_status(self, campaign_id, status):
            status_changes.append((campaign_id, status))

        def publish_campaign(self, campaign_id):
            # mirrors the real SQL gate: unauthorized -> refuse
            if campaign_id not in AUTHORIZED:
                return False
            status_changes.append((campaign_id, "published"))
            return True

        def list_published_unpushed(self, channel):
            return [
                {"id": launch_id, "headline": "Launch", "body": "Launch"},
                {"id": held_id, "headline": "Held", "body": "Held"},
            ]

        def mark_pushed(self, channel, campaign_id):
            published_channels.append((channel, campaign_id))

        def get_traffic_stats(self):
            return []

        def verified_revenue_by_campaign(self):
            return {}

        def set_agent_flag(self, campaign_id, flag):
            return True

    class FakeLogs:
        def log_action(self, *args):
            pass

        def get_recent_logs(self, limit):
            return []

    class FakeFinance:
        def sum_by_stream_since(self, since):
            return {}

    class FakeHealth:
        def set_status(self, *args):
            pass

    monkeypatch.setattr(autonomous_agent, "ProductRepository", FakeProducts)
    monkeypatch.setattr(autonomous_agent, "CampaignRepository", FakeCampaigns)
    monkeypatch.setattr(autonomous_agent, "AgentLogRepository", FakeLogs)
    monkeypatch.setattr(autonomous_agent, "FinanceRepository", FakeFinance)
    monkeypatch.setattr(autonomous_agent, "IntegrationHealthRepository", FakeHealth)
    monkeypatch.setattr(autonomous_agent, "LeadRepository", lambda: None)
    monkeypatch.setattr(autonomous_agent, "AGENT_AUTONOMY", "full")
    monkeypatch.setattr(autonomous_agent, "DEVTO_API_KEY", "configured")
    monkeypatch.setattr(autonomous_agent, "BLUESKY_HANDLE", "configured")
    monkeypatch.setattr(autonomous_agent, "BLUESKY_APP_PASSWORD", "configured")
    monkeypatch.setattr(autonomous_agent, "MEDIUM_API_KEY", "configured")
    monkeypatch.setattr(autonomous_agent, "publish_to_devto", lambda *args: True)
    monkeypatch.setattr(autonomous_agent, "publish_to_bluesky", lambda *args: True)
    monkeypatch.setattr(autonomous_agent, "publish_to_medium", lambda *args: True)
    monkeypatch.setattr(autonomous_agent, "scout_from_products", lambda products: [])
    monkeypatch.setattr(autonomous_agent, "build_site", lambda: 4)

    autonomous_agent.run_daily_grind()

    assert status_changes == [
        (launch_id, "approved"),
        (launch_id, "published"),
    ]   # held_id: never approved, never published - DB permission is FALSE
    assert published_channels == [
        ("devto", launch_id),
        ("bluesky", launch_id),
        ("medium", launch_id),
    ]   # held_id excluded from every channel
