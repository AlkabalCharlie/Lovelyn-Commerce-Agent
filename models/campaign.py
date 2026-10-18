"""Campaign domain model."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

VALID_CAMPAIGN_STATUSES = ("draft", "approved", "rejected", "published", "archived")


@dataclass
class Campaign:
    product_id: str
    campaign_type: str
    headline: str
    body: str
    status: str = "draft"
    id: Optional[str] = None
    created_at: Optional[datetime] = None