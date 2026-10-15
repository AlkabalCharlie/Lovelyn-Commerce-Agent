"""Database access for products and research observations. Parameterized queries only."""
from typing import List

from sqlalchemy import text

from database.connection import engine
from models.product import Product, validate_status


class ProductRepository:
    """All reads and writes for the products and research_observations tables."""

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
                    "url": product.url,
                    "name": product.name,
                    "revenue_model": product.revenue_model,
                    "status": product.status,
                    "merchant": product.merchant,
                    "image_url": product.image_url,
                },
            )
            return str(result.scalar_one())

    def list_products(self, search: str = "", status: str = "all") -> List[Product]:
        query = (
            "SELECT id, url, name, revenue_model, status, merchant, image_url, "
            "opportunity_score, score_reasoning, created_at FROM products"
        )
        clauses, params = [], {}
        if search:
            clauses.append("(url ILIKE :search OR name ILIKE :search)")
            params["search"] = f"%{search}%"
        if status != "all":
            clauses.append("status = :status")
            params["status"] = validate_status(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with engine.connect() as connection:
            rows = connection.execute(text(query), params).mappings().all()
        return [
            Product(
                id=str(row["id"]),
                url=row["url"],
                name=row["name"],
                revenue_model=row["revenue_model"],
                status=row["status"],
                merchant=row["merchant"] or "Unknown",
                image_url=row["image_url"],
                opportunity_score=row["opportunity_score"],
                score_reasoning=row["score_reasoning"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def update_status(self, product_id: str, status: str) -> bool:
        validate_status(status)
        with engine.begin() as connection:
            result = connection.execute(
                text("UPDATE products SET status = :status WHERE id = :id"),
                {"status": status, "id": product_id},
            )
            return result.rowcount == 1

    def update_score(self, product_id: str, score: int, reasoning: str) -> bool:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE products SET opportunity_score = :score, "
                    "score_reasoning = :reasoning WHERE id = :id"
                ),
                {"score": score, "reasoning": reasoning, "id": product_id},
            )
            return result.rowcount == 1

    def add_observation(
        self,
        product_id: str,
        research_type: str,
        finding: str,
        source_url: str = None,
        confidence: str = "medium",
    ) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO research_observations "
                    "(product_id, research_type, finding, source_url, confidence) "
                    "VALUES (:product_id, :research_type, :finding, :source_url, :confidence)"
                ),
                {
                    "product_id": product_id,
                    "research_type": research_type,
                    "finding": finding,
                    "source_url": source_url,
                    "confidence": confidence,
                },
            )