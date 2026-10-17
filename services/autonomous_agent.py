"""The autonomous agent that pushes products through the pipeline and republishes the site."""
from database.repositories import ProductRepository, CampaignRepository, AgentLogRepository
from services.campaign_generator import generate_campaign
from services.site_builder import build_site
from models.campaign import Campaign


def run_daily_grind():
    prod_repo = ProductRepository()
    camp_repo = CampaignRepository()
    log_repo = AgentLogRepository()

    log_repo.log_action("START", "Autonomous agent woke up for the daily grind.")

    generated_count = 0
    for p in prod_repo.list_products():
        if not camp_repo.list_campaigns_for_product(p.id):
            data = generate_campaign(p.name, p.merchant, "Review")
            camp_repo.save_campaign(Campaign(product_id=p.id, campaign_type=data["type"], headline=data["headline"], body=data["body"]))
            generated_count += 1
    if generated_count:
        log_repo.log_action("GENERATE", f"Autonomously generated {generated_count} new Review campaigns.")

    approved_count = 0
    for draft in camp_repo.get_all_campaigns_by_status("draft"):
        camp_repo.update_campaign_status(draft.id, "approved")
        approved_count += 1
    if approved_count:
        log_repo.log_action("APPROVE", f"Autonomously approved {approved_count} draft campaigns.")

    published_count = 0
    for camp in camp_repo.get_all_campaigns_by_status("approved"):
        camp_repo.publish_campaign(camp.id)
        published_count += 1
    if published_count:
        log_repo.log_action("PUBLISH", f"Autonomously published {published_count} campaigns.")

    pages = build_site()
    log_repo.log_action("SITE", f"Rebuilt public traffic site with {pages} live page(s).")

    summary = (f"Daily grind complete. Generated: {generated_count}, Approved: {approved_count}, "
               f"Published: {published_count}, Site pages: {pages}.")
    log_repo.log_action("COMPLETE", summary)
    return summary