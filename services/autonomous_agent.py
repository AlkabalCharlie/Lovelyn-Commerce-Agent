"""The autonomous agent: advance pipeline, scale winners by revenue, rebuild site."""
from datetime import datetime, timezone

from config.settings import (
    AGENT_AUTONOMY,
    BLUESKY_APP_PASSWORD,
    BLUESKY_HANDLE,
    DEVTO_API_KEY,
    SITE_BASE_URL,
    AFFILIATE_WEEKLY_TARGET_CENTS,
    OWNED_WEEKLY_TARGET_CENTS,
)
from core.exceptions import ExtractionError, SSRFError
from database.repositories import AgentLogRepository, CampaignRepository, ProductRepository, FinanceRepository
from models.campaign import Campaign
from services.bluesky_publisher import publish_to_bluesky
from services.campaign_generator import generate_campaign
from services.devto_publisher import publish_to_devto
from services.optimizer import MAX_WINNER_VARIANTS, WINNER_VARIANT_ANGLES, decide_action, check_milestones
from services.product_extractor import extract_product_data
from services.site_builder import build_site


def run_daily_grind():
    prod_repo = ProductRepository()
    camp_repo = CampaignRepository()
    log_repo = AgentLogRepository()
    fin_repo = FinanceRepository()

    log_repo.log_action("START", f"Autonomous agent woke up (autonomy={AGENT_AUTONOMY}).")

    # 1. Enrichment
    enriched = 0
    for p in prod_repo.list_products_missing_enrichment():
        try:
            data = extract_product_data(p.url)
            prod_repo.update_enrichment(p.id, data.get("description"), data.get("price"))
            enriched += 1
        except (SSRFError, ExtractionError, Exception):
            prod_repo.mark_enrich_attempted(p.id)
    if enriched:
        log_repo.log_action("ENRICH", f"Enriched {enriched} product(s) with real descriptions/prices.")

    # 2. Pipeline advance
    generated = 0
    for p in prod_repo.list_products():
        if not camp_repo.list_campaigns_for_product(p.id):
            data = generate_campaign(p.name, p.merchant, "Review", p.description, p.price)
            camp_repo.save_campaign(Campaign(product_id=p.id, campaign_type=data["type"], headline=data["headline"], body=data["body"]))
            generated += 1
    if generated:
        log_repo.log_action("GENERATE", f"Autonomously generated {generated} new Review campaigns.")

    approved = published = 0
    if AGENT_AUTONOMY == "full":
        for draft in camp_repo.get_all_campaigns_by_status("draft"):
            camp_repo.update_campaign_status(draft.id, "approved")
            approved += 1
        if approved:
            log_repo.log_action("APPROVE", f"Autonomously approved {approved} draft campaigns.")
        for camp in camp_repo.get_all_campaigns_by_status("approved"):
            camp_repo.publish_campaign(camp.id)
            published += 1
        if published:
            log_repo.log_action("PUBLISH", f"Autonomously published {published} campaigns.")
    else:
        log_repo.log_action("POLICY", "Autonomy gated: new campaigns wait as drafts for owner approval.")

    # 3. Distribution
    pushed = {"devto": 0, "bluesky": 0}
    if DEVTO_API_KEY:
        for camp in camp_repo.list_published_unpushed("devto"):
            url = f"{SITE_BASE_URL}campaign-{camp['id']}.html"
            if publish_to_devto(camp["headline"], camp["body"], url):
                camp_repo.mark_pushed("devto", camp["id"])
                pushed["devto"] += 1
    if BLUESKY_HANDLE and BLUESKY_APP_PASSWORD:
        for camp in camp_repo.list_published_unpushed("bluesky"):
            url = f"{SITE_BASE_URL}campaign-{camp['id']}.html"
            if publish_to_bluesky(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD, camp["headline"], url):
                camp_repo.mark_pushed("bluesky", camp["id"])
                pushed["bluesky"] += 1
    for channel, count in pushed.items():
        if count:
            log_repo.log_action("DISTRIBUTE", f"Pushed {count} article(s) to {channel}.")

    # 4. Revenue-aware kill/scale
    winners = revived = killed = 0
    now = datetime.now(timezone.utc)
    for row in camp_repo.get_traffic_stats():
        created = row["created_at"]
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (now - created).days
        revenue_cents = row.get("revenue_cents", 0)
        action = decide_action(row["views"], row["clicks"], age_days, row["agent_flag"], revenue_cents)

        if action == "winner":
            camp_repo.set_agent_flag(row["id"], "winner")
            winners += 1
            prod_repo.add_observation(
                row["product_id"], "winner_signal",
                f"Campaign '{row['headline']}' earned ${revenue_cents/100:.2f} and {row['clicks']} click(s).", None, "high")
            for angle in WINNER_VARIANT_ANGLES[:MAX_WINNER_VARIANTS]:
                data = generate_campaign(row["product_name"], row["merchant"], angle, row["description"], row["price"])
                camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"], headline=data["headline"], body=data["body"]))
            log_repo.log_action("WINNER", f"'{row['headline']}' has revenue → {MAX_WINNER_VARIANTS} new angles auto-generated.")
        elif action == "revive":
            camp_repo.set_agent_flag(row["id"], "revived")
            revived += 1
            data = generate_campaign(row["product_name"], row["merchant"], "Comparison", row["description"], row["price"])
            camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"], headline=data["headline"], body=data["body"]))
            log_repo.log_action("OPTIMIZE", f"'{row['headline']}': {row['views']} views, 0 clicks → fresh angle generated.")
        elif action == "kill":
            camp_repo.set_agent_flag(row["id"], "killed")
            camp_repo.update_campaign_status(row["id"], "archived")
            killed += 1
            log_repo.log_action("KILL", f"'{row['headline']}': {row['views']} views, 0 clicks after {age_days} days → archived.")

    # 5. Milestone celebrations
    from datetime import timedelta
    week_ago = now.date() - timedelta(days=7)
    totals = fin_repo.sum_by_stream_since(week_ago)
    for stream, cents in totals.items():
        milestones = check_milestones(cents)
        for milestone in milestones:
            log_repo.log_action("MILESTONE", f"🎯 {stream.upper()} crossed ${milestone/100:.2f} in the last 7 days!")

    pages = build_site()
    log_repo.log_action("SITE", f"Rebuilt public traffic site with {pages} live page(s).")

    summary = (f"Daily grind complete. Enriched: {enriched}, Generated: {generated}, "
               f"Approved: {approved}, Published: {published}, "
               f"Dev.to: {pushed['devto']}, Bluesky: {pushed['bluesky']}, "
               f"Winners scaled: {winners}, Revived: {revived}, Killed: {killed}, Site pages: {pages}.")
    log_repo.log_action("COMPLETE", summary)
    return summary