"""Database access for products, campaigns, events, finance, and agent logs."""
from datetime import date
from typing import List

from sqlalchemy import text

from database.connection import engine
from models.campaign import Campaign, VALID_CAMPAIGN_STATUSES
from models.finance import FinancialEvent
from models.product import Product, validate_status

_DISTRIBUTION_COLUMNS = {
    "devto": "devto_pushed",
    "bluesky": "bluesky_pushed",
    "medium": "medium_pushed",
}

# P1-8: companion column that stores WHERE each channel published the item.
_PUBLICATION_URL_COLUMNS = {
    "devto": "devto_publication_url",
    "bluesky": "bluesky_publication_url",
    "medium": "medium_publication_url",
}

VALID_LEAD_STATUSES = ("new", "contacted", "skipped")
VALID_HEALTH_STATUSES = ("connected", "authorization_expired", "configuration_missing",
                         "quota_exceeded", "failed", "awaiting_verification")


class IntegrationHealthRepository:
    """P0-3: persisted per-integration state so a silently broken webhook or
    expired token is VISIBLE. One row per named integration, upserted."""

    def set_status(self, integration: str, status: str, detail: str = None) -> bool:
        if status not in VALID_HEALTH_STATUSES:
            raise ValueError(f"Invalid health status: {status}")
        with engine.begin() as connection:
            result = connection.execute(text(
                "INSERT INTO integration_health (integration, status, detail, checked_at) "
                "VALUES (:i, :s, :d, now()) "
                "ON CONFLICT (integration) DO UPDATE SET status = :s, detail = :d, "
                "checked_at = now()"),
                {"i": integration, "s": status, "d": detail})
            return result.rowcount >= 1

    def list_status(self) -> list:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT integration, status, detail, checked_at FROM integration_health "
                "ORDER BY integration")).mappings().all()
        return [dict(r) for r in rows]


class LeadRepository:
    """Reddit Scout leads: links for the HUMAN to answer by hand."""

    def add_lead(self, subreddit: str, title: str, url: str,
                 product_id: str = None, notes: str = None) -> bool:
        """Insert a lead. UNIQUE url + ON CONFLICT DO NOTHING makes repeats a no-op.
        Returns True only when a NEW row was inserted. notes carries the
        demand-score provenance (intent, matched campaign, score)."""
        with engine.begin() as connection:
            result = connection.execute(
                text("INSERT INTO leads (product_id, subreddit, title, url, notes) "
                     "VALUES (:product_id, :subreddit, :title, :url, :notes) "
                     "ON CONFLICT (url) DO NOTHING RETURNING id"),
                {"product_id": product_id, "subreddit": subreddit,
                 "title": title, "url": url, "notes": notes},
            )
            return result.first() is not None

    def list_leads(self, status: str = "all", limit: int = 100) -> List[dict]:
        query = ("SELECT l.id, l.subreddit, l.title, l.url, l.found_at, l.status, l.notes, "
                 "l.product_id, p.name AS product_name FROM leads l "
                 "LEFT JOIN products p ON p.id = l.product_id")
        params = {"limit": limit}
        if status != "all":
            if status not in VALID_LEAD_STATUSES:
                raise ValueError(f"Invalid lead status: {status}")
            query += " WHERE l.status = :status"
            params["status"] = status
        query += " ORDER BY l.found_at DESC LIMIT :limit"
        with engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()
        return [dict(r) for r in rows]

    def update_status(self, lead_id: str, status: str) -> bool:
        if status not in VALID_LEAD_STATUSES:
            raise ValueError(f"Invalid lead status: {status}")
        with engine.begin() as connection:
            result = connection.execute(
                text("UPDATE leads SET status = :status WHERE id = :id"),
                {"status": status, "id": lead_id})
            return result.rowcount == 1


class ProductRepository:
    def add(self, product: Product) -> str:
        with engine.begin() as connection:
            result = connection.execute(
                text("INSERT INTO products (url, name, revenue_model, status, merchant, image_url, affiliate_url) VALUES (:url, :name, :revenue_model, :status, :merchant, :image_url, :affiliate_url) RETURNING id"),
                {"url": product.url, "name": product.name, "revenue_model": product.revenue_model, "status": product.status, "merchant": product.merchant, "image_url": product.image_url, "affiliate_url": product.affiliate_url},
            )
            return str(result.scalar_one())

    def set_affiliate_url(self, product_id: str, affiliate_url) -> bool:
        """Owner pastes the real tracked affiliate link here (HUMAN step)."""
        with engine.begin() as connection:
            result = connection.execute(
                text("UPDATE products SET affiliate_url = :a WHERE id = :id"),
                {"a": affiliate_url, "id": product_id})
            return result.rowcount == 1

    def list_products(self, search: str = "", status: str = "all") -> List[Product]:
        query = ("SELECT id, url, name, revenue_model, status, merchant, image_url, description, price, "
                 "affiliate_url, enrich_attempted, opportunity_score, score_reasoning, created_at FROM products")
        clauses, params = [], {}
        if search:
            clauses.append("(url ILIKE :search OR name ILIKE :search)")
            params["search"] = f"%{search}%"
        if status != "all":
            clauses.append("status = :status")
            params["status"] = validate_status(status)
        if clauses: query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()
        return [self._row_to_product(r) for r in rows]

    def _row_to_product(self, r) -> Product:
        return Product(
            id=str(r["id"]), url=r["url"], name=r["name"], revenue_model=r["revenue_model"],
            status=r["status"], merchant=r["merchant"] or "Unknown", image_url=r["image_url"],
            description=r["description"], price=r["price"], affiliate_url=r.get("affiliate_url"),
            enrich_attempted=bool(r["enrich_attempted"]),
            opportunity_score=r["opportunity_score"], score_reasoning=r["score_reasoning"],
            created_at=r["created_at"],
        )

    def list_products_missing_enrichment(self) -> List[Product]:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, url, name, revenue_model, status, merchant, image_url, description, price, "
                "affiliate_url, enrich_attempted, opportunity_score, score_reasoning, created_at FROM products "
                "WHERE description IS NULL AND enrich_attempted = FALSE ORDER BY created_at ASC")).mappings().all()
        return [self._row_to_product(r) for r in rows]

    def update_enrichment(self, product_id: str, description, price) -> bool:
        with engine.begin() as connection:
            result = connection.execute(text(
                "UPDATE products SET description = :description, price = :price, enrich_attempted = TRUE WHERE id = :id"),
                {"description": description, "price": price, "id": product_id})
            return result.rowcount == 1

    def mark_enrich_attempted(self, product_id: str) -> bool:
        with engine.begin() as connection:
            result = connection.execute(text("UPDATE products SET enrich_attempted = TRUE WHERE id = :id"), {"id": product_id})
            return result.rowcount == 1

    def mark_needs_facts(self, product_id: str, needed: bool = True) -> bool:
        """Flag a product whose extraction came back thin across all tiers.
        Owner seeds facts manually; seeded rows skip enrichment entirely."""
        with engine.begin() as connection:
            result = connection.execute(
                text("UPDATE products SET needs_facts = :needed WHERE id = :id"),
                {"needed": needed, "id": product_id})
            return result.rowcount == 1

    def update_status(self, product_id: str, status: str) -> bool:
        validate_status(status)
        with engine.begin() as connection:
            result = connection.execute(text("UPDATE products SET status = :status WHERE id = :id"), {"status": status, "id": product_id})
            return result.rowcount == 1

    def update_score(self, product_id: str, score: int, reasoning: str) -> bool:
        with engine.begin() as connection:
            result = connection.execute(text("UPDATE products SET opportunity_score = :score, score_reasoning = :reasoning WHERE id = :id"), {"score": score, "reasoning": reasoning, "id": product_id})
            return result.rowcount == 1

    def add_observation(self, product_id: str, research_type: str, finding: str, source_url: str = None, confidence: str = "medium") -> None:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO research_observations (product_id, research_type, finding, source_url, confidence) VALUES (:product_id, :research_type, :finding, :source_url, :confidence)"),
                {"product_id": product_id, "research_type": research_type, "finding": finding, "source_url": source_url, "confidence": confidence})


class CampaignRepository:
    def save_campaign(self, campaign: Campaign) -> str:
        with engine.begin() as connection:
            result = connection.execute(
                text("INSERT INTO campaigns (product_id, campaign_type, headline, body, status, promotion_approved) VALUES (:product_id, :campaign_type, :headline, :body, :status, FALSE) RETURNING id"),
                {"product_id": campaign.product_id, "campaign_type": campaign.campaign_type, "headline": campaign.headline, "body": campaign.body, "status": campaign.status}
            )
            return str(result.scalar_one())

    def has_campaign_of_type(self, product_id: str, campaign_type: str) -> bool:
        """Idempotence guard: does this product already have a campaign of this type?"""
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT 1 FROM campaigns WHERE product_id = :pid AND campaign_type = :ctype LIMIT 1"),
                {"pid": product_id, "ctype": campaign_type})
            return result.first() is not None

    def list_campaigns_for_product(self, product_id: str) -> List[Campaign]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT id, product_id, campaign_type, headline, body, status, created_at, promotion_approved FROM campaigns WHERE product_id = :pid ORDER BY created_at DESC"), {"pid": product_id}).mappings().all()
        return [Campaign(id=str(r["id"]), product_id=r["product_id"], campaign_type=r["campaign_type"], headline=r["headline"], body=r["body"], status=r["status"], created_at=r["created_at"], promotion_approved=r["promotion_approved"]) for r in rows]

    def update_campaign_status(self, campaign_id: str, status: str) -> bool:
        if status not in VALID_CAMPAIGN_STATUSES:
            raise ValueError(f"Invalid campaign status: {status}")
        with engine.begin() as connection:
            result = connection.execute(text("UPDATE campaigns SET status = :status WHERE id = :id"), {"status": status, "id": campaign_id})
            return result.rowcount == 1

    def update_campaign_copy(self, campaign_id: str, headline: str, body: str) -> bool:
        """Owner-directed copy improvement for an already-published campaign.
        Does NOT touch status, promotion approval, or any attribution field."""
        with engine.begin() as connection:
            result = connection.execute(text(
                "UPDATE campaigns SET headline = :h, body = :b WHERE id = :id"),
                {"h": headline, "b": body, "id": campaign_id})
            return result.rowcount == 1

    def publish_campaign(self, campaign_id: str) -> bool:
        """Publish ONLY with BOTH content approval and promotion authorization.
        Rejected at the QUERY level: unauthorized rows match zero rows, so a
        stale/buggy caller can never publish an unauthorized campaign."""
        with engine.begin() as connection:
            result = connection.execute(text(
                "UPDATE campaigns SET status = 'published' "
                "WHERE id = :id AND status = 'approved' AND promotion_approved = TRUE"),
                {"id": campaign_id})
            return result.rowcount == 1

    def set_promotion_approved(self, campaign_id: str, approved: bool) -> bool:
        """Owner-controlled promotion authorization (separate from content
        approval). Revocation takes effect immediately everywhere: publish,
        distribution, and site generation all query this column."""
        with engine.begin() as connection:
            result = connection.execute(text(
                "UPDATE campaigns SET promotion_approved = :a WHERE id = :id"),
                {"a": approved, "id": campaign_id})
            return result.rowcount == 1

    def is_promotion_approved(self, campaign_id: str) -> bool:
        """Live authorization check for the agent loop (fresh read every call,
        so a revocation takes effect on the next decision, not next restart)."""
        with engine.connect() as connection:
            row = connection.execute(text(
                "SELECT promotion_approved FROM campaigns WHERE id = :id"),
                {"id": campaign_id}).scalar()
            return bool(row)

    def get_all_campaigns_by_status(self, status: str) -> List[Campaign]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT id, product_id, campaign_type, headline, body, status, created_at, promotion_approved FROM campaigns WHERE status = :status ORDER BY created_at ASC"), {"status": status}).mappings().all()
        return [Campaign(id=str(r["id"]), product_id=r["product_id"], campaign_type=r["campaign_type"], headline=r["headline"], body=r["body"], status=r["status"], created_at=r["created_at"], promotion_approved=r["promotion_approved"]) for r in rows]

    def list_published_campaigns(self) -> List[dict]:
        """Public-site source: published AND promotion-authorized only.
        Rejected/archived/unauthorized rows can never reach the website."""
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT c.id, c.headline, c.body, c.campaign_type, p.name AS product_name, "
                "p.url AS product_url, p.merchant, p.affiliate_url FROM campaigns c "
                "JOIN products p ON p.id = c.product_id "
                "WHERE c.status = 'published' AND c.promotion_approved = TRUE "
                "ORDER BY c.created_at DESC")).mappings().all()
        return [dict(r) for r in rows]

    def list_published_unpushed(self, channel: str) -> List[dict]:
        col = _DISTRIBUTION_COLUMNS[channel]
        with engine.connect() as connection:
            rows = connection.execute(text(
                f"SELECT c.id, c.headline, c.body FROM campaigns c "
                f"WHERE c.status = 'published' AND c.promotion_approved = TRUE "
                f"AND c.{col} = FALSE ORDER BY c.created_at ASC")).mappings().all()
        return [dict(r) for r in rows]

    def mark_pushed(self, channel: str, campaign_id: str, publication_url: str = None) -> bool:
        """Marks a channel pushed, optionally recording the live publication
        URL (P1-8). Falls back gracefully when the publication-url migration
        has not been applied yet."""
        col = _DISTRIBUTION_COLUMNS[channel]
        url_col = _PUBLICATION_URL_COLUMNS.get(channel)
        sets = f"{col} = TRUE"
        if url_col and publication_url:
            sets += f", {url_col} = :u"
        try:
            with engine.begin() as connection:
                result = connection.execute(
                    text(f"UPDATE campaigns SET {sets} WHERE id = :id"),
                    {"id": campaign_id, "u": publication_url})
                return result.rowcount == 1
        except Exception:
            # Column missing (migration pending): still record the push flag.
            with engine.begin() as connection:
                result = connection.execute(
                    text(f"UPDATE campaigns SET {col} = TRUE WHERE id = :id"),
                    {"id": campaign_id})
                return result.rowcount == 1

    def get_traffic_stats(self) -> List[dict]:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT c.id, c.headline, c.body, c.status, c.product_id, c.agent_flag, c.created_at, c.revenue_cents, "
                "p.name AS product_name, p.merchant, p.description, p.price, "
                "COUNT(*) FILTER (WHERE e.event_type = 'view') AS views, "
                "COUNT(*) FILTER (WHERE e.event_type = 'click') AS clicks "
                "FROM campaigns c "
                "JOIN products p ON p.id = c.product_id "
                "LEFT JOIN page_events e ON e.campaign_id = c.id "
                "GROUP BY c.id, c.headline, c.body, c.status, c.product_id, c.agent_flag, c.created_at, c.revenue_cents, p.name, p.merchant, p.description, p.price "
                "ORDER BY views DESC")).mappings().all()
        return [dict(r) for r in rows]

    def set_agent_flag(self, campaign_id: str, flag: str) -> bool:
        with engine.begin() as connection:
            result = connection.execute(text("UPDATE campaigns SET agent_flag = :flag WHERE id = :id"), {"flag": flag, "id": campaign_id})
            return result.rowcount == 1

    def verified_revenue_cents(self, campaign_id: str) -> int:
        """Revenue truth for optimizer decisions: SUM of VERIFIED financial
        events attributed to this campaign. Excludes test transactions (by
        external_id/note markers), refunds/reversals (status), and pending
        events. This is the ONLY revenue source the optimizer may trust."""
        with engine.connect() as connection:
            total = connection.execute(text(
                "SELECT COALESCE(SUM(f.amount_cents), 0) "
                "FROM financial_events f "
                "WHERE f.campaign_id = :cid "
                "AND f.status = 'verified' "
                "AND f.external_id NOT LIKE 'E2E-%' "
                "AND f.external_id NOT LIKE '%TEST%' "
                "AND f.external_id NOT LIKE '%PINGTEST%'"),
                {"cid": campaign_id}).scalar()
            return int(total or 0)

    def verified_revenue_by_campaign(self) -> dict:
        """Single-query variant of verified_revenue_cents for the optimizer's
        per-run sweep (avoids N+1). Same exclusion rules."""
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT f.campaign_id, COALESCE(SUM(f.amount_cents), 0) AS total "
                "FROM financial_events f "
                "WHERE f.campaign_id IS NOT NULL "
                "AND f.status = 'verified' "
                "AND f.external_id NOT LIKE 'E2E-%' "
                "AND f.external_id NOT LIKE '%TEST%' "
                "AND f.external_id NOT LIKE '%PINGTEST%' "
                "GROUP BY f.campaign_id")).mappings().all()
        return {str(r["campaign_id"]): int(r["total"]) for r in rows}


class FinanceRepository:
    def add_event(self, event: FinancialEvent, campaign_id=None, product_id=None,
                  fees_cents=None, status="verified") -> str:
        with engine.begin() as connection:
            result = connection.execute(
                text("INSERT INTO financial_events (stream, amount_cents, source, note, received_at, "
                     "campaign_id, product_id, fees_cents, status) "
                     "VALUES (:stream, :amount_cents, :source, :note, :received_at, "
                     ":campaign_id, :product_id, :fees_cents, :status) RETURNING id"),
                {"stream": event.stream, "amount_cents": event.amount_cents, "source": event.source,
                 "note": event.note, "received_at": event.received_at,
                 "campaign_id": campaign_id, "product_id": product_id,
                 "fees_cents": fees_cents, "status": status},
            )
            return str(result.scalar_one())

    def sum_by_stream_since(self, since: date) -> dict:
        """Verified money only. Pending is never revenue; reversed never adds."""
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT stream, COALESCE(SUM(amount_cents), 0) AS total_cents "
                     "FROM financial_events WHERE received_at >= :since "
                     "AND status = 'verified' GROUP BY stream"),
                {"since": since},
            ).mappings().all()
        return {row["stream"]: int(row["total_cents"]) for row in rows}

    # ---- Phase 2: net profit -------------------------------------------------
    # net = verified revenue - refunds - fees - attributable product costs,
    # computed entirely in SQL on integer cents. Refund rows carry
    # refunded_cents (the reversed amount); their amount_cents is informational
    # (the original sale value) and must NOT count as revenue.

    def net_profit_summary(self, since: date = None) -> dict:
        params = {}
        where = ""
        if since is not None:
            where = "WHERE received_at >= :since"
            params["since"] = since
        with engine.connect() as connection:
            rows = connection.execute(text(f"""
                SELECT stream,
                    COALESCE(SUM(CASE WHEN status = 'verified' THEN amount_cents END), 0) AS gross_cents,
                    COALESCE(SUM(refunded_cents), 0)                                  AS refunds_cents,
                    COALESCE(SUM(CASE WHEN status = 'verified' THEN fees_cents END), 0)
                      + COALESCE(SUM(CASE WHEN status = 'verified' THEN cost_cents END), 0) AS costs_cents
                FROM financial_events {where}
                GROUP BY stream"""), params).mappings().all()
        out = {}
        for row in rows:
            gross = int(row["gross_cents"])
            refunds = int(row["refunds_cents"])
            costs = int(row["costs_cents"])
            out[row["stream"]] = {
                "gross_cents": gross, "refunds_cents": refunds,
                "costs_cents": costs, "net_cents": gross - refunds - costs,
            }
        return out

    def breakdown(self, dimension: str, since: date = None, limit: int = 15):
        """Revenue by 'product', 'campaign', or 'channel' (source).
        Only verified rows; refunds subtracted via refunded_cents."""
        if dimension == "product":
            group = "COALESCE(p.name, '(unattributed)')"
            joins = "LEFT JOIN products p ON p.id = f.product_id"
        elif dimension == "campaign":
            group = "COALESCE(c.headline, '(unattributed)')"
            joins = "LEFT JOIN campaigns c ON c.id = f.campaign_id"
        elif dimension == "channel":
            group, joins = "COALESCE(f.source, '(none)')", ""
        else:
            raise ValueError("dimension must be product, campaign, or channel")
        params = {"limit": limit}
        where = ""
        if since is not None:
            where = "WHERE f.received_at >= :since"
            params["since"] = since
        with engine.connect() as connection:
            rows = connection.execute(text(f"""
                SELECT {group} AS label,
                    COALESCE(SUM(CASE WHEN f.status = 'verified' THEN f.amount_cents END), 0)
                      - COALESCE(SUM(f.refunded_cents), 0)
                      - COALESCE(SUM(CASE WHEN f.status = 'verified' THEN f.fees_cents END), 0)
                      - COALESCE(SUM(CASE WHEN f.status = 'verified' THEN f.cost_cents END), 0)
                      AS net_cents,
                    COUNT(*) FILTER (WHERE f.status = 'verified') AS verified_count
                FROM financial_events f {joins} {where}
                GROUP BY label ORDER BY net_cents DESC LIMIT :limit"""), params).mappings().all()
        return [dict(r) for r in rows]

    def list_recent(self, limit: int = 20) -> List[dict]:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT stream, amount_cents, source, note, received_at FROM financial_events "
                     "ORDER BY received_at DESC, created_at DESC LIMIT :limit"),
                {"limit": limit},
            ).mappings().all()
        return [dict(r) for r in rows]

    def health_status(self) -> List[dict]:
        """Integration health rows for the dashboard status panel (P0-3)."""
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT integration, status, last_ok_at, last_error_at, last_detail, updated_at "
                "FROM integration_health ORDER BY integration")).mappings().all()
        return [dict(r) for r in rows]


class AgentLogRepository:
    def log_action(self, action_type: str, details: str) -> None:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO agent_logs (action_type, details) VALUES (:action_type, :details)"),
                {"action_type": action_type, "details": details}
            )

    def get_recent_logs(self, limit: int = 50) -> List[dict]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT action_type, details, created_at FROM agent_logs ORDER BY created_at DESC LIMIT :limit"), {"limit": limit}).mappings().all()
        return [dict(r) for r in rows]