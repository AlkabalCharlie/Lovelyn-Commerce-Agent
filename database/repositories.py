"""Database access for products, campaigns, events, finance, and agent logs."""
from datetime import date
from typing import List

from sqlalchemy import text

from database.connection import engine
from models.product import Product, validate_status
from models.campaign import Campaign, VALID_CAMPAIGN_STATUSES
from models.finance import FinancialEvent


class ProductRepository:
    def add(self, product: Product) -> str:
        with engine.begin() as connection:
            result = connection.execute(
                text("INSERT INTO products (url, name, revenue_model, status, merchant, image_url) VALUES (:url, :name, :revenue_model, :status, :merchant, :image_url) RETURNING id"),
                {"url": product.url, "name": product.name, "revenue_model": product.revenue_model, "status": product.status, "merchant": product.merchant, "image_url": product.image_url},
            )
            return str(result.scalar_one())

    def list_products(self, search: str = "", status: str = "all") -> List[Product]:
        query = "SELECT id, url, name, revenue_model, status, merchant, image_url, opportunity_score, score_reasoning, created_at FROM products"
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
        return [
            Product(id=str(r["id"]), url=r["url"], name=r["name"], revenue_model=r["revenue_model"],
                    status=r["status"], merchant=r["merchant"] or "Unknown", image_url=r["image_url"],
                    opportunity_score=r["opportunity_score"], score_reasoning=r["score_reasoning"], created_at=r["created_at"])
            for r in rows
        ]

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

    def get_traffic_stats(self) -> List[dict]:
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT c.id, c.headline, c.status, c.product_id, c.agent_flag, c.created_at, "
                "p.name AS product_name, p.merchant, "
                "COUNT(*) FILTER (WHERE e.event_type = 'view') AS views, "
                "COUNT(*) FILTER (WHERE e.event_type = 'click') AS clicks "
                "FROM campaigns c "
                "JOIN products p ON p.id = c.product_id "
                "LEFT JOIN page_events e ON e.campaign_id = c.id "
                "GROUP BY c.id, c.headline, c.status, c.product_id, c.agent_flag, c.created_at, p.name, p.merchant "
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