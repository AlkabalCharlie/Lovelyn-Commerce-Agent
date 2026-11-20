"""The autonomous agent: enrich, advance, scale, distribute, rebuild.

Pacing rule: at most MAX_POSTS_PER_CHANNEL_PER_RUN posts per borrowed
channel per day, so distribution looks like a human drip, not a firehose.
"""
from datetime import datetime, timedelta, timezone
import os

from config.settings import (
    AGENT_AUTONOMY,
    BLUESKY_APP_PASSWORD,
    BLUESKY_HANDLE,
    DEVTO_API_KEY,
    MEDIUM_API_KEY,
    OPENAI_API_KEY,
    OWNED_PRODUCT_URL,
    SITE_BASE_URL,
)
from core.exceptions import ExtractionError, SSRFError
from database.repositories import (
    AgentLogRepository,
    CampaignRepository,
    FinanceRepository,
    IntegrationHealthRepository,
    LeadRepository,
    ProductRepository,
)
from models.campaign import Campaign
from services.bluesky_publisher import publish_to_bluesky
from services.campaign_generator import generate_campaign
from services.devto_publisher import publish_to_devto
from services.medium_publisher import publish_to_medium
from services import youtube_upload
from services.optimizer import (
    MAX_WINNER_VARIANTS,
    WINNER_VARIANT_ANGLES,
    check_milestones,
    decide_action,
    decide_rewrite,
)
from services.product_extractor import extract_product_data
from services.reddit_scout import scout_from_products, scout_reddit
from services.site_builder import build_site

MAX_POSTS_PER_CHANNEL_PER_RUN = 2
MAX_MEDIUM_POSTS_PER_RUN = 1  # Medium flags automation faster than Bluesky
MAX_NEW_LEADS_PER_RUN = 10  # Reddit Scout insert cap (human replies, bot never posts)


def _authorized(camp_repo, campaign_id: str) -> bool:
    """Fresh DB read: is this campaign promotion-authorized?
    Authorization lives in campaigns.promotion_approved (owner-controlled).
    A fresh check per decision means an owner revocation takes effect on the
    very next agent decision, not after a restart."""
    return camp_repo.is_promotion_approved(campaign_id)


def run_daily_grind():
    prod_repo = ProductRepository()
    camp_repo = CampaignRepository()
    log_repo = AgentLogRepository()
    fin_repo = FinanceRepository()

    log_repo.log_action("START", f"Autonomous agent woke up (autonomy={AGENT_AUTONOMY}).")

    # 0. Integration health snapshot: every external dependency gets a persisted
    #    status row (connected / configuration_missing / failed). No silent gaps.
    health_repo = IntegrationHealthRepository()
    _HEALTH_KEYS = (
        ("devto", bool(DEVTO_API_KEY), "DEVTO_API_KEY"),
        ("bluesky", bool(BLUESKY_HANDLE and BLUESKY_APP_PASSWORD), "BLUESKY_HANDLE/BLUESKY_APP_PASSWORD"),
        ("medium", bool(MEDIUM_API_KEY), "MEDIUM_API_KEY"),
        ("gumroad_ping", bool(os.getenv("GUMROAD_PING_TOKEN")), "GUMROAD_PING_TOKEN"),
        ("payhip_webhook", bool(os.getenv("PAYHIP_WEBHOOK_TOKEN")), "PAYHIP_WEBHOOK_TOKEN"),
        ("owned_product", bool(OWNED_PRODUCT_URL), "OWNED_PRODUCT_URL"),
    )
    for integration, configured, key_name in _HEALTH_KEYS:
        try:
            health_repo.set_status(
                integration,
                "connected" if configured else "configuration_missing",
                f"{key_name} {'set' if configured else 'not set'}")
        except Exception as exc:
            log_repo.log_action("HEALTH", f"{integration} health write failed: {type(exc).__name__}.")

    # 1. Enrichment: tiered extraction (meta -> JSON-LD -> headless render).
    # Seeded rows (description already set) are skipped entirely.
    enriched = needs_facts_count = 0
    for p in prod_repo.list_products_missing_enrichment():
        try:
            data = extract_product_data(p.url)
            prod_repo.update_enrichment(p.id, data.get("description"), data.get("price"))
            enriched += 1
            if not (data.get("description") or "").strip():
                # Thin across all tiers: flag for the owner to seed manually.
                prod_repo.mark_needs_facts(p.id, True)
                needs_facts_count += 1
            else:
                prod_repo.mark_needs_facts(p.id, False)
        except (SSRFError, ExtractionError):
            prod_repo.mark_enrich_attempted(p.id)
        except Exception:
            prod_repo.mark_enrich_attempted(p.id)
    if enriched:
        log_repo.log_action("ENRICH", f"Enriched {enriched} product(s) with real descriptions/prices.")
    if needs_facts_count:
        log_repo.log_action("ENRICH", f"{needs_facts_count} product(s) flagged needs_facts - owner must seed facts manually.")

    # 2. Pipeline advance: every product gets a fact-based Review campaign
    generated = 0
    for p in prod_repo.list_products():
        if not camp_repo.list_campaigns_for_product(p.id):
            data = generate_campaign(p.name, p.merchant, "Review", p.description, p.price)
            if camp_repo.has_campaign_of_type(p.id, data["type"]):
                continue  # idempotence: another run (local or cloud) got here first
            camp_repo.save_campaign(Campaign(product_id=p.id, campaign_type=data["type"],
                                             headline=data["headline"], body=data["body"]))
            generated += 1
    if generated:
        log_repo.log_action("GENERATE", f"Autonomously generated {generated} new Review campaigns.")

    approved = published = 0
    if AGENT_AUTONOMY == "full":
        for draft in camp_repo.get_all_campaigns_by_status("draft"):
            # Content approval alone is NOT promotion: only drafts whose owner
            # has granted promotion_approved may be auto-approved.
            if not _authorized(camp_repo, draft.id):
                continue
            camp_repo.update_campaign_status(draft.id, "approved")
            approved += 1
        if approved:
            log_repo.log_action("APPROVE", f"Autonomously approved {approved} draft campaigns.")
        for camp in camp_repo.get_all_campaigns_by_status("approved"):
            # publish_campaign re-checks the permission at the query level.
            if not _authorized(camp_repo, camp.id):
                continue
            if camp_repo.publish_campaign(camp.id):
                published += 1
        if published:
            log_repo.log_action("PUBLISH", f"Autonomously published {published} campaigns.")
    else:
        log_repo.log_action("POLICY", "Autonomy gated: new campaigns wait as drafts for owner approval.")

    # 3. Distribution sweep, capped to a human drip per channel
    pushed = {"devto": 0, "bluesky": 0, "medium": 0}
    if not DEVTO_API_KEY:
        log_repo.log_action("CONFIG", "DEVTO_API_KEY missing or parked - Dev.to distribution skipped.")
    else:
        launch_campaigns = [
            camp for camp in camp_repo.list_published_unpushed("devto")
            if _authorized(camp_repo, camp["id"])
        ]
        for camp in launch_campaigns[:MAX_POSTS_PER_CHANNEL_PER_RUN]:
            url = f"{SITE_BASE_URL}campaign-{camp['id']}.html"
            pub_url = publish_to_devto(camp["headline"], camp["body"], url)
            if pub_url is not None:
                camp_repo.mark_pushed("devto", camp["id"], pub_url or None)
                pushed["devto"] += 1
    if not (BLUESKY_HANDLE and BLUESKY_APP_PASSWORD):
        log_repo.log_action("CONFIG", "Bluesky credentials missing - Bluesky distribution skipped.")
    else:
        launch_campaigns = [
            camp for camp in camp_repo.list_published_unpushed("bluesky")
            if _authorized(camp_repo, camp["id"])
        ]
        for camp in launch_campaigns[:MAX_POSTS_PER_CHANNEL_PER_RUN]:
            url = f"{SITE_BASE_URL}campaign-{camp['id']}.html"
            if publish_to_bluesky(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD, camp["headline"], url):
                camp_repo.mark_pushed("bluesky", camp["id"], url)  # bluesky API returns no per-post URL; the campaign link is in the post
                pushed["bluesky"] += 1
    if not MEDIUM_API_KEY:
        log_repo.log_action("CONFIG", "MEDIUM_API_KEY missing or parked - Medium distribution skipped.")
    else:
        launch_campaigns = [
            camp for camp in camp_repo.list_published_unpushed("medium")
            if _authorized(camp_repo, camp["id"])
        ]
        for camp in launch_campaigns[:MAX_MEDIUM_POSTS_PER_RUN]:
            url = f"{SITE_BASE_URL}campaign-{camp['id']}.html"
            pub_url = publish_to_medium(camp["headline"], camp["body"], url)
            if pub_url is not None:
                camp_repo.mark_pushed("medium", camp["id"], pub_url or None)
                pushed["medium"] += 1
    for channel, count in pushed.items():
        if count:
            log_repo.log_action("DISTRIBUTE", f"Pushed {count} article(s) to {channel} (capped drip).")

    # 3.5 Reddit Scout: surface live buyer questions for the OWNER to answer by hand.
    # Read-only: no posting, no commenting, no login. Dedupe via UNIQUE url no-op.
    # DEMAND-SCORED: every lead is scored by demand_matcher; only QUALIFIED
    # buyer-intent posts are stored with their score + matched campaign in
    # notes (provenance). Weak posts are rejected here, not stored.
    # 3.6 Opportunity-driven packaging: the TOP-QUALIFIED lead feeds a
    # campaign-specific package (opportunity source URL + score retained in
    # the package). Evergreen packages are queued once, labelled evergreen,
    # and never re-created (UNIQUE constraint makes reruns no-ops).
    qualified_leads = []
    new_leads = 0
    packages_queued = 0
    try:
        lead_repo = LeadRepository()
        active = [p for p in prod_repo.list_products() if p.status == "active"]
        approved_products = [p for p in active if p.status == "approved"]
        if not approved_products:
            approved_products = active  # products table uses active as its live status
        terms = scout_from_products(active)
        if terms:
            from services.demand_matcher import score_demand
            for lead in scout_reddit(terms):
                if new_leads >= MAX_NEW_LEADS_PER_RUN:
                    break
                verdict = score_demand(lead["title"], "", approved_products,
                                       lead.get("subreddit", ""))
                if not verdict["qualified"]:
                    continue  # weak/irrelevant opportunity: rejected, not stored
                note = (f"intent={verdict['intent_score']}/40 "
                        f"relevance={verdict['relevance_score']}/60 "
                        f"score={verdict['score']}/100 "
                        f"campaign_product={verdict.get('matched_product_name')} "
                        f"signals={verdict.get('intent_categories')}")
                if lead_repo.add_lead(lead["subreddit"], lead["title"],
                                      lead["url"], notes=note):
                    new_leads += 1
                verdict["source_url"] = lead["url"]
                verdict["title"] = lead["title"]
                qualified_leads.append(verdict)
        log_repo.log_action("SCOUT", f"Reddit Scout: {new_leads} NEW qualified lead(s) "
                                     f"(buyer-intent scored; weak posts rejected at insert; read-only).")
    except Exception as exc:
        log_repo.log_action("SCOUT", f"Reddit Scout skipped this run: {type(exc).__name__}.")

    # 3.6 Demand-to-content packages: queue production-ready packages for the
    # channels the agent cannot publish to directly. Opportunity-led first:
    # the highest-scoring qualified lead drives a source-specific package.
    # Evergreen fallback: only when NO qualified opportunity exists, so we
    # never pad the queue with predetermined content.
    try:
        from services.content_packages import (
            blogger_article_draft,
            opportunity_blogger_draft,
            opportunity_youtube_script,
            pinterest_pin_package,
            youtube_script_package,
        )
        from services.publishing_queue import ensure_queue_table, queue_count
        ensure_queue_table()
        tv = "b8d56c20-c801-4c97-ac8f-936bb5c36cba"
        debt = "66d125ce-0523-492b-9679-3bd06d75e1be"
        tv_url = f"{SITE_BASE_URL}campaign-{tv}.html"
        debt_url = f"{SITE_BASE_URL}campaign-{debt}.html"

        top = max(qualified_leads, key=lambda v: v["score"], default=None)
        if top is not None and _authorized(camp_repo, tv):
            pkg = opportunity_youtube_script(tv, tv_url, top, f"opp-{top['score']}-tv-shorts")
            if pkg:
                packages_queued += 1
        if top is not None and _authorized(camp_repo, debt):
            pkg = opportunity_blogger_draft(debt, debt_url, top, f"opp-{top['score']}-debt-draft")
            if pkg:
                packages_queued += 1
        if top is None:
            # Evergreen campaign assets: queued ONCE (UNIQUE makes reruns
            # no-ops), labelled evergreen, only for authorized campaigns.
            if _authorized(camp_repo, tv):
                youtube_script_package(tv, tv_url, "TradingView Free vs Paid: What Each Tier Actually Changes", "tv-free-vs-paid-shorts", evergreen=True)
                blogger_article_draft(tv, tv_url, "TradingView Free vs Paid in 2026: An Honest Tier Comparison", "tv-free-vs-paid-2026",
                                      ["What the free tier includes - and who it genuinely serves.",
                                       "What Essential adds: 5 indicators, 2 charts per tab, 20 alerts, no ads.",
                                       "When paying is worth it: multi-chart workflows, alert-driven trading.",
                                       "When it is not: single-market, single-timeframe traders."], evergreen=True)
                pinterest_pin_package(tv, tv_url, "TradingView Free vs Paid: The Real Differences", "tv-free-vs-paid-pin", evergreen=True)
                packages_queued += 1
            if _authorized(camp_repo, debt):
                youtube_script_package(debt, debt_url, "Snowball or Avalanche? Pick Your Debt Payoff Method in 45 Seconds", "debt-method-shorts", evergreen=True)
                blogger_article_draft(debt, debt_url, "Snowball vs Avalanche: Which Debt Payoff Plan Will You Actually Finish?", "snowball-vs-avalanche-2026",
                                      ["Avalanche saves the most interest; snowball saves motivation.",
                                       "Write every debt down first: balance, rate, minimum.",
                                       "The method you abandon is the one that costs you.",
                                       "Worksheet-based planning beats app-passive tracking for follow-through."], evergreen=True)
                pinterest_pin_package(debt, debt_url, "Snowball vs Avalanche: Pick Your Payoff Plan", "debt-method-pin", evergreen=True)
                packages_queued += 1
        log_repo.log_action("QUEUE", f"Publishing queue: {queue_count()} queued item(s) "
                                     f"({packages_queued} package(s) ensured this run; "
                                     f"opportunity-led: {top is not None}).")
    except Exception as exc:
        log_repo.log_action("QUEUE", f"Publishing queue step skipped: {type(exc).__name__}.")

    # 4. Revenue-aware kill/scale on real traffic — revenue truth is computed
    # LIVE from verified financial_events only (excluding tests/refunds), so a
    # stale or test-contaminated campaigns.revenue_cents column can NEVER
    # manufacture a winner. This closes the residual winner-label defect.
    winners = revived = killed = rewritten = 0
    now = datetime.now(timezone.utc)
    # Pre-fetch verified revenue for every campaign in ONE query (no N+1).
    _verified_rev = camp_repo.verified_revenue_by_campaign()
    for row in camp_repo.get_traffic_stats():
        # Revoked/unauthorized campaigns are skipped for promotion-related
        # optimization (winner scaling, revival, rewrite). Archiving a dead
        # unauthorized campaign is still allowed - that is cleanup, not
        # promotion.
        authorized = _authorized(camp_repo, row["id"])
        if not authorized:
            # only permit the kill path for unauthorized rows
            created = row["created_at"]
            if created is None:
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = (now - created).days
            if decide_action(row["views"], row["clicks"], age_days, row["agent_flag"],
                             _verified_rev.get(str(row["id"]), 0)) == "kill":
                camp_repo.set_agent_flag(row["id"], "killed")
                camp_repo.update_campaign_status(row["id"], "archived")
                killed += 1
                log_repo.log_action("KILL", f"'{row['headline']}' (unauthorized): archived dead campaign.")
            continue
        created = row["created_at"]
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (now - created).days
        # Revenue truth: recomputed per-campaign from VERIFIED financial events
        # only. campaigns.revenue_cents is ignored — prove_loop.py's recompute
        # summed TEST events into it (2698c on every owned campaign), and the
        # next agent run promoted four campaigns to 'winner' on test money.
        revenue_cents = _verified_rev.get(str(row["id"]), 0)
        action = decide_action(row["views"], row["clicks"], age_days,
                               row["agent_flag"], revenue_cents)

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
                if camp_repo.has_campaign_of_type(row["product_id"], data["type"]):
                    continue  # idempotence: variant already exists
                camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"],
                                                 headline=data["headline"], body=data["body"]))
            log_repo.log_action("WINNER", f"'{row['headline']}' earned money/clicks -> {MAX_WINNER_VARIANTS} new angles auto-generated.")
        elif action == "revive":
            camp_repo.set_agent_flag(row["id"], "revived")
            data = generate_campaign(row["product_name"], row["merchant"], "Comparison",
                                     row["description"], row["price"])
            if camp_repo.has_campaign_of_type(row["product_id"], data["type"]):
                continue  # idempotence: comparison already exists
            revived += 1
            camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"],
                                             headline=data["headline"], body=data["body"]))
            log_repo.log_action("OPTIMIZE", f"'{row['headline']}': {row['views']} views, 0 clicks -> fresh Comparison angle generated.")
        elif decide_rewrite(row["views"], row["clicks"], age_days, row["agent_flag"]):
            # Zero views after N days: the headline/meta never caught anyone.
            # Regenerate with the long-tail keyword angle instead of archiving.
            camp_repo.set_agent_flag(row["id"], "rewritten")
            data = generate_campaign(row["product_name"], row["merchant"], "Review",
                                     row["description"], row["price"])
            if camp_repo.has_campaign_of_type(row["product_id"], data["type"]):
                data = generate_campaign(row["product_name"], row["merchant"], "Promo",
                                         row["description"], row["price"])
            if not camp_repo.has_campaign_of_type(row["product_id"], data["type"]):
                camp_repo.save_campaign(Campaign(product_id=row["product_id"], campaign_type=data["type"],
                                                 headline=data["headline"], body=data["body"]))
            rewritten += 1
            log_repo.log_action(
                "REWRITE",
                f"'{row['headline']}' got zero views in {age_days} days -> keyword-angled replacement generated.")
        elif action == "kill":
            camp_repo.set_agent_flag(row["id"], "killed")
            camp_repo.update_campaign_status(row["id"], "archived")
            killed += 1
            log_repo.log_action("KILL", f"'{row['headline']}': {row['views']} views, 0 clicks after {age_days} days -> archived.")

    # 4.5 Daily conversion-copy refresh: spend a small AI budget rewriting
    # LIVE campaign bodies that get views but no clicks (copy is the leak),
    # never touching pages that already earn. Fact-locked: a hallucinated
    # number rejects the rewrite and the page keeps its current copy.
    copy_refreshed = 0
    if OPENAI_API_KEY:
        try:
            from services.conversion_copywriter import rewrite_for_conversion, should_refresh
            refreshed_ids = set()
            limit = max(1, int(os.getenv("COPY_REFRESH_DAILY_LIMIT", "3") or 3))
            # Prefer weakest-first: views-but-no-clicks, oldest first.
            candidates = sorted(
                [r for r in camp_repo.get_traffic_stats()
                 if _authorized(camp_repo, r["id"]) and should_refresh(r, refreshed_ids)
                 and _verified_rev.get(str(r["id"]), 0) == 0],
                key=lambda r: (-(r.get("views") or 0), r.get("created_at") or now))
            for row in candidates[:limit]:
                try:
                    facts = {"product": row["product_name"], "merchant": row["merchant"],
                             "description": row["description"] or "",
                             "price": row["price"] if row["price"] is not None else ""}
                    result = rewrite_for_conversion(row["headline"], row["body"], facts,
                                                    row["clicks"],
                                                    _verified_rev.get(str(row["id"]), 0))
                    if result:
                        camp_repo.update_campaign_copy(row["id"], result[0], result[1])
                        refreshed_ids.add(str(row["id"]))
                        copy_refreshed += 1
                        log_repo.log_action("COPY", f"Conversion rewrite applied to '{row['headline']}' "
                                                    f"({row['views']} views, {row['clicks']} clicks -> fresh copy).")
                except Exception as row_exc:
                    # One bad page never aborts the refresh (or the grind).
                    log_repo.log_action("COPY", f"Copy refresh skipped for a page: {type(row_exc).__name__}.")
            if copy_refreshed:
                log_repo.log_action("COPY", f"Daily copy refresh: {copy_refreshed} page(s) rewritten (limit {limit}).")
        except Exception as exc:
            log_repo.log_action("COPY", f"Copy refresh step failed (non-fatal): {type(exc).__name__}.")

    # 4.7 YouTube Shorts pipeline (max 2/day, non-fatal): render one queued
    # script package into a real MP4, then upload any rendered-but-unuploaded
    # one whose campaign is still authorized. Missing ffmpeg or YouTube
    # credentials NEVER blocks other channels - exact reason is logged.
    rendered = uploaded_count = 0
    try:
        from services.publishing_queue import (
            claim_next_rendered_for_upload, claim_next_short_for_render,
            ensure_shorts_columns, mark_rendered, mark_uploaded, set_status)
        from services.shorts_renderer import ffmpeg_missing, render_short
        ensure_shorts_columns()
        MAX_SHORTS_PER_RUN = 2
        if ffmpeg_missing():
            log_repo.log_action("SHORTS", "ffmpeg missing on runner - rendering skipped "
                                          "(install ffmpeg; queue unchanged).")
        else:
            for _ in range(MAX_SHORTS_PER_RUN):
                item = claim_next_short_for_render()
                if not item:
                    break
                pkg = item.get("package") or {}
                if not _authorized(camp_repo, str(item.get("campaign_id") or "")):
                    set_status(item["id"], "skipped",
                               error="campaign no longer promotion-authorized")
                    continue
                out = os.path.join("media", "shorts", f"short-{item['id'][:8]}.mp4")
                set_status(item["id"], "generating")
                path = render_short(pkg, out)
                if path:
                    mark_rendered(item["id"], path)
                    rendered += 1
                    log_repo.log_action("SHORTS", f"Rendered MP4 for '{item['title'][:60]}'.")
                else:
                    set_status(item["id"], "failed", error="render returned no file")
        if youtube_upload.credentials_ready():
            for _ in range(MAX_SHORTS_PER_RUN):
                item = claim_next_rendered_for_upload()
                if not item:
                    break
                if not _authorized(camp_repo, str(item.get("campaign_id") or "")):
                    set_status(item["id"], "skipped",
                               error="campaign no longer promotion-authorized")
                    continue
                pkg = item.get("package") or {}
                set_status(item["id"], "uploading")
                ok, vid_or_reason = youtube_upload.upload_short(
                    item["video_path"],
                    (pkg.get("title") or item["title"])[:100],
                    pkg.get("description") or "",
                    pkg.get("tags") or [])
                if ok and "/shorts/" in vid_or_reason:
                    mark_uploaded(item["id"], vid_or_reason.rsplit("/", 1)[-1], vid_or_reason)
                    uploaded_count += 1
                    log_repo.log_action("SHORTS", f"Published Short: {vid_or_reason}")
                else:
                    set_status(item["id"], "rendered", error=vid_or_reason)
                    log_repo.log_action("SHORTS", f"Upload not completed: {vid_or_reason[:160]}")
        else:
            log_repo.log_action("SHORTS", "YouTube credentials missing - rendered videos "
                                          "wait in queue (owner setup: services/youtube_upload.py docstring).")
    except Exception as exc:
        log_repo.log_action("SHORTS", f"Shorts pipeline step failed (non-fatal): {type(exc).__name__}.")

    # 5. Milestone celebrations (each threshold celebrated once per stream)
    week_ago = now.date() - timedelta(days=7)
    totals = fin_repo.sum_by_stream_since(week_ago)
    celebrated = {r["details"] for r in log_repo.get_recent_logs(limit=300) if r["action_type"] == "MILESTONE"}
    for stream, cents in totals.items():
        for threshold in check_milestones(cents):
            note = f"{stream} crossed ${threshold / 100:,.0f} in a 7-day window"
            if note not in celebrated:
                log_repo.log_action("MILESTONE", note)

    # 6. Rebuild the public storefront, then ping search engines so the
    #    fresh pages are actually discovered (P1-11). Ping failures are
    #    non-fatal and never block the grind.
    pages = build_site()
    log_repo.log_action("SITE", f"Rebuilt public traffic site with {pages} live page(s).")
    try:
        from services.index_ping import ping_sitemap_urls
        if pages:
            ping_sitemap_urls(["index.html"] + [f"campaign-{c['id']}.html" for c in camp_repo.list_published_campaigns()])
            log_repo.log_action("SITE", "Search-engine ping (IndexNow) submitted.")
        else:
            log_repo.log_action("SITE", "No pages built - search-engine ping skipped.")
    except Exception as exc:
        log_repo.log_action("SITE", f"Index ping skipped: {type(exc).__name__}.")

    summary = (f"Daily grind complete. Enriched: {enriched}, Generated: {generated}, "
               f"Approved: {approved}, Published: {published}, "
               f"Dev.to: {pushed['devto']}, Bluesky: {pushed['bluesky']}, Medium: {pushed['medium']}, "
               f"New leads: {new_leads}, Queued packages: {packages_queued}, "
               f"Winners scaled: {winners}, Revived: {revived}, Killed: {killed}, "
               f"Shorts rendered: {rendered}, Shorts uploaded: {uploaded_count}, "
               f"Site pages: {pages}.")
    log_repo.log_action("COMPLETE", summary)
    return summary