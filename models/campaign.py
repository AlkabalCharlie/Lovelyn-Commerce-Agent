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
    # Promotion authorization is SEPARATE from content approval: a campaign
    # may be beautifully written and approved yet NOT authorized for public
    # promotion. Defaults to False for every newly created campaign; only the
    # owner grants it (pages/campaigns.py), and publish/distribute/site
    # generation all refuse without it.
    promotion_approved: bool = False