# LOVELYN — PHASE 1 SOURCE-CODE AUDIT & GAP REPORT
Date: 2026-11-15 · Baseline: `python -m pytest tests -q` → **95 passed** (3.98 s)
Scope: every service, model, repository, migration, Edge Function, dashboard page,
the GitHub Actions workflow, and the public-site builder. No code was modified.

──────────────────────────────────────────────────────────────────────────────
A. MAP: IMPLEMENTATION vs ARCHITECTURE (what actually exists)
──────────────────────────────────────────────────────────────────────────────
PRESENT AND SOLID
- Tiered fact-locked extraction (meta → JSON-LD → microdata → embedded state →
  Playwright), SSRF-guarded via `services/url_safety.py`, prices only from
  structured offer fields. (`product_extractor.py`, 299 lines)
- Fact-locked campaign generation with a price-verification copy polisher
  (`campaign_generator.py`, `copy_polisher.py`). Hallucinated numbers rejected.
- Public site builder: escape-first HTML, minimal markdown, canonical URLs,
  sitemap, robots.txt, FTC disclosure, `rel="nofollow sponsored noopener"`,
  Supabase beacon for view/click events. (`site_builder.py`)
- Attribution-grade ingestion path: generic affiliate postback Edge Function
  (token gate ≥24 chars, tolerant field mapping, cents normalization, tx-id
  dedupe via `record_financial_event` SECURITY DEFINER rpc + unique index) and
  its byte-faithful Python mirror `affiliate_postback.py`.
- Autonomous daily grind with idempotence guards at every step
  (`has_campaign_of_type`, unique lead URLs, unique tx_ids) — safe under
  concurrent local + cloud runs.
- Integer-cents math everywhere (`parse_amount_to_cents`, `normalize_cents`,
  `format_cents`). Received-money-only logging.
- Merchant identification (7 domains + fallback).
- Kill/revive/rewrite optimizer + milestone celebrations.
- Distribution caps per channel (2/1 per run) prevent platform flags.
- 95 passing tests incl. idempotence, URL safety, postback normalization.

RECENTLY ADDED (previous session, tested)
- `affiliate_url` column end-to-end (model validation → repo → Products page
  input → site-builder CTA swap).
- `OWNED_PRODUCT_URL` Buy button on campaign pages.
- `SITE_NICHE_KEYWORD` long-tail headline angles.
- Content-first export formatting; Reddit draft replies in Leads page;
  optimizer rewrite action for zero-traffic pages.

──────────────────────────────────────────────────────────────────────────────
B. GAPS, PRIORITIZED (P0 = blocks revenue · P1 = major · P2 = improvement)
──────────────────────────────────────────────────────────────────────────────
P0-1. Campaign-level attribution is broken in the postback path.
      financial_events stores tx_id + a product string in a NOTE, but there is
      NO column linking a conversion to campaign_id or product_id. The
      optimizer's revenue-aware logic (`revenue_cents` on campaigns) only ever
      gets revenue the dashboard logs manually against a campaign. The Edge
      Function accepts `campaign_id` in PRODUCT_KEYS but discards it into prose.
      → REQUIRED: add `product_id`/`campaign_id` columns to financial_events +
        map them in the postback; without this, priorities 5/6/8/10 cannot work.
P0-2. click ≠ conversion in the optimizer.
      `decide_action` returns "winner" on **1 click** with flag None
      (optimizer.py:23). Directive explicitly forbids this. One click spawns
      2 variant campaigns and steals the agent's generation budget from
      unproven products. Winner requires verified revenue; clicks alone can
      at most reach "promising".
P0-3. No integration-health state. Credentials are checked with `if not KEY`
      and logged as CONFIG, but there is no persisted status (connected /
      expired / missing / quota / failed), so a silently broken webhook or an
      expired token is invisible until money doesn't arrive.
P0-4. Gumroad owned-product payments have NO ingestion path at all. `Payhip`
      webhook token exists (`PAYHIP_WEBHOOK_TOKEN` + test_payhip_webhook.py),
      but Gumroad has no webhook receiver and no adapter. Directive names
      Gumroad as an actual current sales channel — this is the biggest
      single-source revenue hole.
P0-5. No net-profit concept anywhere. financial_events has amount_cents only;
      fees, refunds, COGS are unrepresentable, so "verified net profit" (the
      final acceptance criterion) cannot be computed.

P1-6. Opportunity scorer ignores demand entirely.
      opportunity_scorer.py scores merchant-name lists (hardcoded strings) +
      revenue model + data confidence. No buyer-intent, recency, price-fit, or
      historical-conversion inputs. Fix requires the P2 discovery layer first;
      interim fix: accept an optional demand-signal parameter and reweight.
P1-7. Discovery is Reddit-only, 7 hardcoded finance/trading subreddits
      (reddit_scout.py DEFAULT_SUBREDDITS) — these subreddits are close to
      irrelevant for selling HTML5 games. No product-derived query generation
      (queries currently come from product names verbatim via
      scout_from_products). No intent classification; leads store only
      subreddit/title/url/status.
      → REQUIRED: leads/opportunities table with intent level, product_match,
        source, excerpt, provenance, dedupe id, next action.
P1-8. Publisher adapters are thin: devto/bluesky/medium publish headline+body
      and store a pushed flag, but NO publication URL/ID is recorded (the
      Dev.to one does return a URL that the agent drops), so P7 attribution
      "Publication → Click → Conversion" cannot close. Also no Blogger /
      YouTube / Pinterest adapters (P6 in directive; YouTube/Pinterest need
      OAuth the owner must grant — do these last).
P1-9. Beacon attribution is campaign-scoped only. `page_events` rows carry
      campaign_id + event_type + page_url, but the destination click is not
      differentiated per outbound URL/affiliate id, and there is no
      source/medium capture (referrer) to attribute discovery channels.
P1-10. Optimizer lacks sample-size discipline: kill at ≥10 views/7 days
       throws away slow-but-alive pages; no Testing/Learning/Promising/
       Profitable lifecycle; agent_flag is a single text column rather than a
       status with history/reasoning. Reasoning does land in agent_logs (good).
P1-11. GitHub Pages indexing is unverified: sitemap/robots exist, but nothing
       pings Search Console, no IndexNow/Ping submission, and no check that
       GH Pages actually deployed before commit (workflow commits docs even if
       build_site() wrote zero pages).

P2-12. Product model too thin for commercial validation: no category, target
       audience, problems-solved, currency, availability, commission rate,
       fees, refund policy, verification timestamp, per-platform adapter.
       Adapter set required: JVZoo / Payhip / Gumroad / Etsy / generic.
P2-13. No Pydantic validation layer (models are hand-rolled dataclasses with
       ad-hoc validation). Directive asks for structured validation of URLs,
       currency, statuses, transitions + structured logging with retries.
P2-14. No retry/backoff on publishers or extraction (single attempt, no
       storm — good for safety, but failures are silently absorbed, e.g.
       publish_to_devto False → dropped on the floor without an error log).
P2-15. Missing integration tests: no test touches (a) beacon → page_events →
       traffic_stats SQL join, (b) edge-function ↔ python normalization parity
       beyond unit fixtures, (c) site_builder output for affiliate_url paths,
       (d) full run_daily_grind() with a fake repo.
P2-16. Workflow quality: no test step before deploy (pip install → run agent
       directly), no failure notification, no branch protection guidance.
P2-17. YouTube/Pinterest/Blogger adapters absent (P6 directive phase) — and
       each needs owner OAuth grant; must be gated behind the integration-
       health layer so an unconfigured adapter logs "config missing" instead
       of crashing the grind.
P2-18. Google Search Console reporting: no API integration (needs OAuth);
       feasible as P2 with a manual CSV-import fallback to stay zero-cost.

──────────────────────────────────────────────────────────────────────────────
C. BUGS / INCONSISTENCIES FOUND (small, fix during implementation phases)
──────────────────────────────────────────────────────────────────────────────
B-1.  site_builder._BUY_BUTTON uses a placeholder name ("Get the <product>
      toolkit") that can produce a nonsensical CTA for non-toolkit products;
      should use a neutral "Buy" label or a per-product label field.
B-2.  campaign_generator keyword Comparison headline builds via .format() on a
      literal containing braces when SITE_NICHE_KEYWORD is set — works today,
      but is fragile; rewrite as a single f-string.
B-3.  _from_embedded_state regex `\{.*?\};` can stop at the first `};` inside
      nested JSON strings — acceptable tier-2 risk, worth a defensive try.
B-4.  affiliate_postback.normalize_cents rejects values > 2 decimal places
      silently (returns None) — a 3-decimal amount from a network drops the
      commission entirely instead of rounding. Edge Function behaves the same
      (parity kept intentionally).
B-5.  repositories.list_leads joins products for product_name but the Leads
      draft-reply passes row.get("product_name") — fine — while list_leads
      returns created_at only for some queries; verify column parity if leads
      gain fields (P1-7 rewrite will unify this).
B-6.  `get_traffic_stats` GROUP BY includes p.description/price — fine, but if
      products table gains columns the revenue join in P0-1 must include them.
B-7.  Finance page only shows 7-day totals and a raw list; P8 dashboard needs
      by-product/by-channel/by-source aggregation once P0-1 lands.
B-8.  site_builder writes `docs/` but never deletes campaign pages for
      archived/killed campaigns — stale pages linger in sitemap until they
      fall out of list_published_campaigns (they do drop, but old .html files
      remain on disk; harmless but untidy, and canonical dupes if regenerated).

──────────────────────────────────────────────────────────────────────────────
D. RECOMMENDED IMPLEMENTATION ORDER (mapped to directive phases)
──────────────────────────────────────────────────────────────────────────────
PHASE 2 (revenue validation) — do FIRST, everything else depends on it:
  1. financial_events + product_id, campaign_id, fees_cents, refund_of_tx,
     status(pending/verified/reversed) columns + migration.
  2. Postback & Payhip/Gumroad receivers map campaign/product ids (P0-1, P0-4).
  3. Gumroad webhook adapter (signature verify, tx dedupe, owned stream).
  4. Net-profit rollups (P0-5) + Finance dashboard upgrade (P8) + minimal
     integration-health table (P0-3).
PHASE 3 (discovery):
  5. opportunities table + intent classifier + product-derived query builder
     + multi-source adapters (Reddit improved first; RSS + public search next;
     Quora/YouTube/Pinterest where permitted) (P1-6/P1-7).
  6. Rewrite opportunity_scorer to consume demand signals + conversions.
PHASE 4 (distribution):
  7. Record publication URLs/ids from existing publishers (P1-8) — cheap,
     unblocks attribution.
  8. Blogger adapter (service account, no user OAuth friction) — cheapest new
     channel. YouTube via FFmpeg/Pillow modules + API behind health gate;
     Pinterest last (API access most restrictive).
PHASE 5 (optimizer): evidence-based states, minimum samples, verified-revenue
     promotion gates (P0-2/P1-10) — AFTER attribution exists, or it optimizes
     against nothing.
PHASE 6 (reliability): Pydantic models, retries with backoff, integration
     tests listed in P2-15, workflow test-gate, branch protection docs.
PHASE 7 (experiment): 1 JVZoo product + 1 Gumroad owned game, 30-day run,
     measure by-product/by-channel verified net profit.

CONSTRAINTS HONORED
- Zero-cost: everything above fits free tiers (Supabase free PG, GH Actions,
  FFmpeg/Pillow local generation, service-account Blogger API). Optional AI
  stays behind the existing copy_polisher interface.
- Nothing removed: all existing modules/tests preserved; changes are additive
  columns/tables/adapters.

OPEN QUESTIONS FOR THE OWNER (blocked-on-human, cannot be guessed):
  1. Does a Gumroad account exist with an accessible webhook endpoint + does
     the owner consent to enabling it? (P0-4 needs this)
  2. Which JVZoo product is the Phase-7 experiment candidate?
  3. Is the owner willing to create a Blogger service account + grant
     YouTube/Pinterest OAuth when those phases arrive?
  4. Search Console property verified for the GH Pages domain? (P9 checklist
     needs the property URL and verification method used.)
