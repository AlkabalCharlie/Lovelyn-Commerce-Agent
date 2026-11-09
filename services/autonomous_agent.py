"""The autonomous agent: enrich, advance, scale, distribute, rebuild.

Pacing rule: at most MAX_POSTS_PER_CHANNEL_PER_RUN posts per borrowed
channel per day, so distribution looks like a human drip, not a firehose.
"""
from datetime import datetime, timedelta, timezone

from config.settings import (
    AGENT_AUTONOMY,
    BLUESKY_APP_PASSWORD,
    BLUESKY_HANDLE,
    DEVTO_API_KEY,
    SITE_BASE_URL,
)
from core.exceptions import ExtractionError, SSRFError
from database.repositories import (
    AgentLogRepository,
    CampaignRepository,
    FinanceRepository,
    LeadRepository,
    ProductRepository,
)
from models.campaign import Campaign
from services.bluesky_publisher import publish_to_bluesky
from services.campaign_generator import generate_campaign
from services.devto_publisher import publish_to_devto
from services.optimizer import (
    MAX_WINNER_VARIANTS,
    WINNER_VARIANT_ANGLES,
    check_milestones,
    decide_action,
)
from services.product_extractor import extract_product_data
from services.reddit_scout import scout_from_products, scout_reddit
from services.site_builder import build_site

MAX_POSTS_PER_CHANNEL_PER_RUN = 2
MAX_NEW_LEADS_PER_RUN = 10  # Reddit Scout insert cap (human replies, bot never posts)


def run_daily_grind():
    prod_repo = ProductRepository()
    camp_repo = CampaignRepository()
    log_repo = AgentLogRepository()
    fin_repo = FinanceRepository()

    log_repo.log_action("START", f"Autonomous agent woke up (autonomy={AGENT_AUTONOMY}).")

    # 1. Enrichment: read real descriptions/prices where merchants allow it
    enriched = 0
    for p in prod_repo.list_products_missing_enrichment():
        try:
            data = extract_product_data(p.url)
            prod_repo.update_enrichment(p.id, data.get("description"), data.get("price"))
            enriched += 1
        except (SSRFError, ExtractionError):
            prod_repo.mark_enrich_attempted(p.id)
        except Exception:
            prod_repo.mark_enrich_attempted(p.id)
    if enriched:
        log_repo.log_action("ENRICH", f"Enriched {enriched} product(s) with real descriptions/prices.")

    # 2. Pipeline advance: every product gets a fact-based Review campaign
    generated = 0
    for p in prod_repo.list_products():
        if not camp_repo.list_campaigns_for_product(p.id):
            data = generate_campaign(p.name, p.merchant, "Review", p.description, p.price)
            camp_repo.save_campaign(Campaign(product_id=p.id, campaign_type=data["type"],
                                             headline=data["headline"], body=data["body"]))
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

    # 3. Distribution sweep, capped to a human drip per channel
    pushed = {"devto": 0, "bluesky": 0}
    if not DEVTO_API_KEY:
        log_repo.log_action("CONFIG", "DEVTO_API_KEY missing or parked - Dev.to distribution skipped.")
    else:
        for camp in camp_repo.list_published_unpushed("devto")[:MAX_POSTS_PER_CHANNEL_PER_RUN]:
            url = f"{SITE_BASE_URL}campaign-{camp['id']}.html"
            if publish_to_devto(camp["headline"], camp["body"], url):
                camp_repo.mark_pushed("devto", camp["id"])
                pushed["devto"] += 1
    if not (BLUESKY_HANDLE and BLUESKY_APP_PASSWORD):
        log_repo.log_action("CONFIG", "Bluesky credentials missing - Bluesky distribution skipped.")
    else:
        for camp in camp_repo.list_published_unpushed("bluesky")[:MAX_POSTS_PER_CHANNEL_PER_RUN]:
            url = f"{SITE_BASE_URL}campaign-{camp['id']}.html"
            if publish_to_bluesky(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD, camp["headline"], url):
                camp_repo.mark_pushed("bluesky", camp["id"])
                pushed["bluesky"] += 1
    for channel, count in pushed.items():
        if count:
            log_repo.log_action("DISTRIBUTE", f"Pushed {count} article(s) to {channel} (capped drip).")

    # 3.5 Reddit Scout: surface live buyer questions for the OWNER to answer by hand.
    # Read-only: no posting, no commenting, no login. Dedupe via UNIQUE url no-op.
    new_leads = 0
    try:
        lead_repo = LeadRepository()
        active = [p for p in prod_repo.list_products() if p.status == "active"]
        terms = scout_from_products(active)
        if terms:
            for lead in scout_reddit(terms):
                if new_leads >= MAX_NEW_LEADS_PER_RUN:
                    break
                if lead_repo.add_lead(lead["subreddit"], lead["title"], lead["url"]):
                    new_leads += 1
        log_repo.log_action("SCOUT", f"Reddit Scout surfaced {new_leads} new lead(s) "
                                     f"for human reply (read-only; bot never posts).")
    except Exception as exc:
        log_repo.log_action("SCOUT", f"Reddit Scout skipped this run: {type(exc).__name__}.")

    # 4. Revenue-aware kill/scale on real traffic
    winners = revived = killed = 0
    now = datetime.now(timezone.utc)
    for row in camp_repo.get_traffic_stats():
        created = row["created_at"]
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (now - created).days
        revenue_cents = row.get("revenue_cents", 0) or 0
        action = decide_action(row["views"], row["clicks"], age_days, row["agent_flag"], revenue_cents)

        if action == "winner":
            camp_repo.set_agent_flag(row["id"], "winner")
            winners += 1
            prod_repo.add_observation(
                row["product_id"], "winner_signal",
                f"Campaign '{row['headline']}' earned {revenue_cents} cent(s) and {row['clicks']} click(s).",
                None, "high")
            for angle in WINNER_VARIANT_ANGLES[:MAX_WINNER_VARIANTS]:
                data = generate_campaign(row["product_name"], row["merchant"], angle,
                                         row["description"], row["price"])
                camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"],
                                                 headline=data["headline"], body=data["body"]))
            log_repo.log_action("WINNER", f"'{row['headline']}' earned money/clicks -> {MAX_WINNER_VARIANTS} new angles auto-generated.")
        elif action == "revive":
            camp_repo.set_agent_flag(row["id"], "revived")
            revived += 1
            data = generate_campaign(row["product_name"], row["merchant"], "Comparison",
                                     row["description"], row["price"])
            camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"],
                                             headline=data["headline"], body=data["body"]))
            log_repo.log_action("OPTIMIZE", f"'{row['headline']}': {row['views']} views, 0 clicks -> fresh Comparison angle generated.")
        elif action == "kill":
            camp_repo.set_agent_flag(row["id"], "killed")
            camp_repo.update_campaign_status(row["id"], "archived")
            killed += 1
            log_repo.log_action("KILL", f"'{row['headline']}': {row['views']} views, 0 clicks after {age_days} days -> archived.")

    # 5. Milestone celebrations (each threshold celebrated once per stream)
    week_ago = now.date() - timedelta(days=7)
    totals = fin_repo.sum_by_stream_since(week_ago)
    celebrated = {r["details"] for r in log_repo.get_recent_logs(limit=300) if r["action_type"] == "MILESTONE"}
    for stream, cents in totals.items():
        for threshold in check_milestones(cents):
            note = f"{stream} crossed ${threshold / 100:,.0f} in a 7-day window"
            if note not in celebrated:
                log_repo.log_action("MILESTONE", note)

    # 6. Rebuild the public storefront
    pages = build_site()
    log_repo.log_action("SITE", f"Rebuilt public traffic site with {pages} live page(s).")

    summary = (f"Daily grind complete. Enriched: {enriched}, Generated: {generated}, "
               f"Approved: {approved}, Published: {published}, "
               f"Dev.to: {pushed['devto']}, Bluesky: {pushed['bluesky']}, New leads: {new_leads}, "
               f"Winners scaled: {winners}, Revived: {revived}, Killed: {killed}, Site pages: {pages}.")
    log_repo.log_action("COMPLETE", summary)
    return summary