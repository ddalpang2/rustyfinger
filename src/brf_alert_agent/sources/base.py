from __future__ import annotations

from typing import Protocol

from brf_alert_agent.models import ListingDetail, ListingSummary


class ListingSource(Protocol):
    name: str

    def fetch_recent_listings(self) -> list[ListingSummary]:
        ...

    def fetch_listing_detail(self, summary: ListingSummary) -> ListingDetail:
        ...

