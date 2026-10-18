"""The autonomous agent: advance pipeline, scale winners, kill losers, rebuild site.

Autonomy policy: AGENT_AUTONOMY=full (default) approves and publishes without
waiting. Set AGENT_AUTONOMY=gated to make new campaigns wait as drafts.
"""
from datetime import datetime, timezone

from config.settings import AGENT_AUTONOMY
from database.repositories import AgentLogRepository, CampaignRepository, ProductRepository
from models.campaign import Campaign
from services.campaign_generator import generate_campaign
from services.optimizer import MAX_WINNER_VARIANTS, WINNER_VARIANT_ANGLES, decide_action
from services.site_builder import build_site


def run_daily_grind():
    prod_repo = ProductRepository()
    camp_repo = CampaignRepository()
    log_repo = AgentLogRepository()

    log_repo.log_action("START", f"Autonomous agent woke up (autonomy={AGENT_AUTONOMY}).")

    generated = 0
    for p in prod_repo.list_products():
        if not camp_repo.list_campaigns_for_product(p.id):
            data = generate_campaign(p.name, p.merchant, "Review")
            camp_repo.save_campaign(Campaign(product_id=p.id, campaign_type=data["type"], headline=data["headline"], body=data["body"]))
            generated += 1
    if generated:
        log_repo.log_action("GENERATE", f"Autonomously generated {generated} new Review campaigns.")

    if AGENT_AUTONOMY == "full":
        approved = 0
        for draft in camp_repo.get_all_campaigns_by_status("draft"):
            camp_repo.update_campaign_status(draft.id, "approved")
            approved += 1
        if approved:
            log_repo.log_action("APPROVE", f"Autonomously approved {approved} draft campaigns.")

        published = 0
        for camp in camp_repo.get_all_campaigns_by_status("approved"):
            camp_repo.publish_campaign(camp.id)
            published += 1
        if published:
            log_repo.log_action("PUBLISH", f"Autonomously published {published} campaigns.")
    else:
        approved = published = 0
        log_repo.log_action("POLICY", "Autonomy gated: new campaigns wait as drafts for owner approval.")

    winners = revived = killed = 0
    now = datetime.now(timezone.utc)
    for row in camp_repo.get_traffic_stats():
        created = row["created_at"]
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (now - created).days
        action = decide_action(row["views"], row["clicks"], age_days, row["agent_flag"])

        if action == "winner":
            camp_repo.set_agent_flag(row["id"], "winner")
            winners += 1
            prod_repo.add_observation(
                row["product_id"], "winner_signal",
                f"Campaign '{row['headline']}' earned {row['clicks']} click(s).", None, "high")
            for angle in WINNER_VARIANT_ANGLES[:MAX_WINNER_VARIANTS]:
                data = generate_campaign(row["product_name"], row["merchant"], angle)
                camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"], headline=data["headline"], body=data["body"]))
            log_repo.log_action("WINNER", f"'{row['headline']}' has clicks → {MAX_WINNER_VARIANTS} new angles auto-generated.")

        elif action == "revive":
            camp_repo.set_agent_flag(row["id"], "revived")
            revived += 1
            data = generate_campaign(row["product_name"], row["merchant"], "Comparison")
            camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"], headline=data["headline"], body=data["body"]))
            log_repo.log_action("OPTIMIZE", f"'{row['headline']}': {row['views']} views, 0 clicks → fresh Comparison angle generated.")

        elif action == "kill":
            camp_repo.set_agent_flag(row["id"], "killed")
            camp_repo.update_campaign_status(row["id"], "archived")
            killed += 1
            log_repo.log_action("KILL", f"'{row['headline']}': {row['views']} views, 0 clicks after {age_days} days → archived, page removed from site.")

    pages = build_site()
    log_repo.log_action("SITE", f"Rebuilt public traffic site with {pages} live page(s), sitemap and robots.txt.")

    summary = (f"Daily grind complete. Generated: {generated}, Approved: {approved}, "
               f"Published: {published}, Winners scaled: {winners}, Revived: {revived}, "
               f"Killed: {killed}, Site pages: {pages}.")
    log_repo.log_action("COMPLETE", summary)
    return summary