"""Database access for products, observations, and campaigns. Parameterized queries only."""
from typing import List

from sqlalchemy import text

from database.connection import engine
from models.product import Product, validate_status
from models.campaign import Campaign, VALID_CAMPAIGN_STATUSES


class ProductRepository:
    """All reads and writes for the core tables."""

    def add(self, product: Product) -> str:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    "INSERT INTO products "
                    "(url, name, revenue_model, status, merchant, image_url) "
                    "VALUES (:url, :name, :revenue_model, :status, :merchant, :image_url) "
                    "RETURNING id"
                ),
                {
                    "url": product.url, "name": product.name,
                    "revenue_model": product.revenue_model, "status": product.status,
                    "merchant": product.merchant, "image_url": product.image_url,
                },
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
    """All reads and writes for the campaigns table."""

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
        """
        Strict publishing gate: Only 'approved' campaigns can be marked as 'published'.
        Returns True if successful, False otherwise.
        """
        with engine.begin() as connection:
            result = connection.execute(
                text("UPDATE campaigns SET status = 'published' WHERE id = :id AND status = 'approved'"),
                {"id": campaign_id}
            )
            return result.rowcount == 1