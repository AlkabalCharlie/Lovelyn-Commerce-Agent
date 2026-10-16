"""The autonomous agent that pushes products through the pipeline."""
from database.repositories import ProductRepository, CampaignRepository, AgentLogRepository
from services.campaign_generator import generate_campaign
from models.campaign import Campaign

def run_daily_grind():
    """
    The daily heartbeat. Scans the database and autonomously advances the pipeline.
    """
    prod_repo = ProductRepository()
    camp_repo = CampaignRepository()
    log_repo = AgentLogRepository()
    
    log_repo.log_action("START", "Autonomous agent woke up for the daily grind.")
    
    # RULE 1: Find products without campaigns and generate a "Review" draft.
    products = prod_repo.list_products()
    generated_count = 0
    for p in products:
        existing_campaigns = camp_repo.list_campaigns_for_product(p.id)
        if not existing_campaigns:
            data = generate_campaign(p.name, p.merchant, "Review")
            new_camp = Campaign(product_id=p.id, campaign_type=data["type"], headline=data["headline"], body=data["body"])
            camp_repo.save_campaign(new_camp)
            generated_count += 1
            
    if generated_count > 0:
        log_repo.log_action("GENERATE", f"Autonomously generated {generated_count} new Review campaigns.")

    # RULE 2: Auto-approve all drafts.
    drafts = camp_repo.get_all_campaigns_by_status("draft")
    approved_count = 0
    for draft in drafts:
        camp_repo.update_campaign_status(draft.id, "approved")
        approved_count += 1
        
    if approved_count > 0:
        log_repo.log_action("APPROVE", f"Autonomously approved {approved_count} draft campaigns.")

    # RULE 3: Auto-publish all approved campaigns.
    approved_camps = camp_repo.get_all_campaigns_by_status("approved")
    published_count = 0
    for camp in approved_camps:
        camp_repo.publish_campaign(camp.id)
        published_count += 1
        
    if published_count > 0:
        log_repo.log_action("PUBLISH", f"Autonomously published {published_count} campaigns.")

    # Final Summary
    summary = f"Daily grind complete. Generated: {generated_count}, Approved: {approved_count}, Published: {published_count}."
    log_repo.log_action("COMPLETE", summary)
    return summary