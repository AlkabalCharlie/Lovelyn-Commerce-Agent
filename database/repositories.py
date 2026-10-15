"""Database access for products. Parameterized queries only."""
from typing import List

from sqlalchemy import text

from database.connection import engine
from models.product import Product, validate_status


class ProductRepository:
    """All reads and writes for the products table."""

    def add(self, product: Product) -> str:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    "INSERT INTO products (url, name, revenue_model, status) "
                    "VALUES (:url, :name, :revenue_model, :status) "
                    "RETURNING id"
                ),
                {
                    "url": product.url,
                    "name": product.name,
                    "revenue_model": product.revenue_model,
                    "status": product.status,
                },
            )
            return str(result.scalar_one())

    def list_products(self, search: str = "", status: str = "all") -> List[Product]:
        query = "SELECT id, url, name, revenue_model, status, created_at FROM products"
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