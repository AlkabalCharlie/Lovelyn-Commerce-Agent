"""Financial events: received money only, stored in integer cents."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Optional

VALID_STREAMS = ("affiliate", "owned")


class FinanceValidationError(ValueError):
    """Raised when a financial entry is invalid."""


def parse_amount_to_cents(raw: str) -> int:
    """Convert '12.34' (or '$12.34') to 1234 cents. Rejects anything else."""
    if not isinstance(raw, str):
        raise FinanceValidationError("Amount must be text.")
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", cleaned):
        raise FinanceValidationError("Amount must look like 12.34 (dollars.cents).")
    cents = int((Decimal(cleaned) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if cents <= 0:
        raise FinanceValidationError("Amount must be greater than zero.")
    return cents


def format_cents(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


@dataclass
class FinancialEvent:
    stream: str
    amount_cents: int
    source: str = ""
    note: str = ""
    received_at: date = field(default_factory=date.today)
    id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.stream not in VALID_STREAMS:
            raise FinanceValidationError(f"Stream must be one of {VALID_STREAMS}.")
        if not isinstance(self.amount_cents, int) or self.amount_cents <= 0:
            raise FinanceValidationError("Amount must be a positive whole number of cents.")