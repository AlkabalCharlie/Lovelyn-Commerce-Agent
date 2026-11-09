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
}

VALID_LEAD_STATUSES = ("new", "contacted", "skipped")


class LeadRepository:
    """Reddit Scout leads: links for the HUMAN to answer by hand."""

    def add_lead(self, subreddit: str, title: str, url: str,
                 product_id: str = None) -> bool:
        """Insert a lead. UNIQUE url + ON CONFLICT DO NOTHING makes repeats a no-op.
        Returns True only when a NEW row was inserted."""
        with engine.begin() as connection:
            result = connection.execute(
                text("INSERT INTO leads (product_id, subreddit, title, url) "
                     "VALUES (:product_id, :subreddit, :title, :url) "
                     "ON CONFLICT (url) DO NOTHING RETURNING id"),
                {"product_id": product_id, "subreddit": subreddit,
                 "title": title, "url": url},
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
                text("INSERT INTO products (url, name, revenue_model, status, merchant, image_url) VALUES (:url, :name, :revenue_model, :status, :merchant, :image_url) RETURNING id"),
                {"url": product.url, "name": product.name, "revenue_model": product.revenue_model, "status": product.status, "merchant": product.merchant, "image_url": product.image_url},
            )
            return str(result.scalar_one())

    def list_products(self, search: str = "", status: str = "all") -> List[Product]:
        query = ("SELECT id, url, name, revenue_model, status, merchant, image_url, description, price, "
                 "enrich_attempted, opportunity_score, score_reasoning, created_at FROM products")
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
            description=r["description"], price=r["price"],
            enrich_attempted=bool(r["enrich_attempted"]),
            opportunity_score=r["opportunity_score"], score_reasoning=r["score_reasoning"],
            created_at=r["created_at"],
        )

    def list_products_missing_enrichment(self) -> List[Product]:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, url, name, revenue_model, status, merchant, image_url, description, price, "
                "enrich_attempted, opportunity_score, score_reasoning, created_at FROM products "
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
                text("INSERT INTO campaigns (product_id, campaign_type, headline, body, status) VALUES (:product_id, :campaign_type, :headline, :body, :status) RETURNING id"),
                {"product_id": campaign.product_id, "campaign_type": campaign.campaign_type, "headline": campaign.headline, "body": campaign.body, "status": campaign.status}
            )
            return str(result.scalar_one())

    def list_campaigns_for_product(self, product_id: str) -> List[Campaign]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT id, product_id, campaign_type, headline, body, status, created_at FROM campaigns WHERE product_id = :pid ORDER BY created_at DESC"), {"pid": product_id}).mappings().all()
        return [Campaign(id=str(r["id"]), product_id=r["product_id"], campaign_type=r["campaign_type"], headline=r["headline"], body=r["body"], status=r["status"], created_at=r["created_at"]) for r in rows]

    def update_campaign_status(self, campaign_id: str, status: str) -> bool:
        if status not in VALID_CAMPAIGN_STATUSES:
            raise ValueError(f"Invalid campaign status: {status}")
        with engine.begin() as connection:
            result = connection.execute(text("UPDATE campaigns SET status = :status WHERE id = :id"), {"status": status, "id": campaign_id})
            return result.rowcount == 1

    def publish_campaign(self, campaign_id: str) -> bool:
        with engine.begin() as connection:
            result = connection.execute(text("UPDATE campaigns SET status = 'published' WHERE id = :id AND status = 'approved'"), {"id": campaign_id})
            return result.rowcount == 1

    def get_all_campaigns_by_status(self, status: str) -> List[Campaign]:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT id, product_id, campaign_type, headline, body, status, created_at FROM campaigns WHERE status = :status ORDER BY created_at ASC"), {"status": status}).mappings().all()
        return [Campaign(id=str(r["id"]), product_id=r["product_id"], campaign_type=r["campaign_type"], headline=r["headline"], body=r["body"], status=r["status"], created_at=r["created_at"]) for r in rows]

    def list_published_campaigns(self) -> List[dict]:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT c.id, c.headline, c.body, c.campaign_type, p.name AS product_name, "
                "p.url AS product_url, p.merchant FROM campaigns c "
                "JOIN products p ON p.id = c.product_id "
                "WHERE c.status = 'published' ORDER BY c.created_at DESC")).mappings().all()
        return [dict(r) for r in rows]

    def list_published_unpushed(self, channel: str) -> List[dict]:
        col = _DISTRIBUTION_COLUMNS[channel]
        with engine.connect() as connection:
            rows = connection.execute(text(
                f"SELECT c.id, c.headline, c.body FROM campaigns c "
                f"WHERE c.status = 'published' AND c.{col} = FALSE ORDER BY c.created_at ASC")).mappings().all()
        return [dict(r) for r in rows]

    def mark_pushed(self, channel: str, campaign_id: str) -> bool:
        col = _DISTRIBUTION_COLUMNS[channel]
        with engine.begin() as connection:
            result = connection.execute(text(f"UPDATE campaigns SET {col} = TRUE WHERE id = :id"), {"id": campaign_id})
            return result.rowcount == 1

    def get_traffic_stats(self) -> List[dict]:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT c.id, c.headline, c.status, c.product_id, c.agent_flag, c.created_at, c.revenue_cents, "
                "p.name AS product_name, p.merchant, p.description, p.price, "
                "COUNT(*) FILTER (WHERE e.event_type = 'view') AS views, "
                "COUNT(*) FILTER (WHERE e.event_type = 'click') AS clicks "
                "FROM campaigns c "
                "JOIN products p ON p.id = c.product_id "
                "LEFT JOIN page_events e ON e.campaign_id = c.id "
                "GROUP BY c.id, c.headline, c.status, c.product_id, c.agent_flag, c.created_at, c.revenue_cents, p.name, p.merchant, p.description, p.price "
                "ORDER BY views DESC")).mappings().all()
        return [dict(r) for r in rows]

    def set_agent_flag(self, campaign_id: str, flag: str) -> bool:
        with engine.begin() as connection:
            result = connection.execute(text("UPDATE campaigns SET agent_flag = :flag WHERE id = :id"), {"flag": flag, "id": campaign_id})
            return result.rowcount == 1


class FinanceRepository:
    def add_event(self, event: FinancialEvent) -> str:
        with engine.begin() as connection:
            result = connection.execute(
                text("INSERT INTO financial_events (stream, amount_cents, source, note, received_at) "
                     "VALUES (:stream, :amount_cents, :source, :note, :received_at) RETURNING id"),
                {"stream": event.stream, "amount_cents": event.amount_cents, "source": event.source,
                 "note": event.note, "received_at": event.received_at},
            )
            return str(result.scalar_one())

    def sum_by_stream_since(self, since: date) -> dict:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT stream, COALESCE(SUM(amount_cents), 0) AS total_cents "
                     "FROM financial_events WHERE received_at >= :since GROUP BY stream"),
                {"since": since},
            ).mappings().all()
        return {row["stream"]: int(row["total_cents"]) for row in rows}

    def list_recent(self, limit: int = 20) -> List[dict]:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT stream, amount_cents, source, note, received_at FROM financial_events "
                     "ORDER BY received_at DESC, created_at DESC LIMIT :limit"),
                {"limit": limit},
            ).mappings().all()
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