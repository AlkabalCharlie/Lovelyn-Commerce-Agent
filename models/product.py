"""Product domain model and input validation rules."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

VALID_REVENUE_MODELS = ("affiliate", "owned", "both")
VALID_STATUSES = ("new", "researching", "approved", "rejected", "archived")


class ProductValidationError(ValueError):
    """Raised when product input fails validation."""


def validate_product_url(url: str) -> str:
    """Return the cleaned URL if it is an absolute http/https URL."""
    if not isinstance(url, str):
        raise ProductValidationError("URL must be text.")
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ProductValidationError("Only http and https URLs are allowed.")
    if not parsed.netloc:
        raise ProductValidationError("URL must include a domain name.")
    return cleaned


def validate_revenue_model(model: str) -> str:
    if model not in VALID_REVENUE_MODELS:
        raise ProductValidationError(
            f"Revenue model must be one of {VALID_REVENUE_MODELS}."
        )
    return model


def validate_status(status: str) -> str:
    if status not in VALID_STATUSES:
        raise ProductValidationError(f"Status must be one of {VALID_STATUSES}.")
    return status


@dataclass
class Product:
    url: str
    name: str
    revenue_model: str
    status: str = "new"
    id: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.url = validate_product_url(self.url)
        self.name = (self.name or "").strip() or "Unnamed product"
        self.revenue_model = validate_revenue_model(self.revenue_model)
        self.status = validate_status(self.status)