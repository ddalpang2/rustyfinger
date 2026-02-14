from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

MatchCategory = Literal["whole_unit_rentable", "room_with_separate_entrance"]


@dataclass(slots=True)
class ListingSummary:
    source: str
    listing_id: str
    url: str
    title: str = ""


@dataclass(slots=True)
class ListingDetail(ListingSummary):
    address: str = ""
    price: str = ""
    body_text: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class MatchResult:
    is_match: bool
    categories: list[MatchCategory] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

