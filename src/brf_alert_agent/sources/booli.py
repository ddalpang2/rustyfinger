from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from brf_alert_agent.config import SourceConfig
from brf_alert_agent.models import ListingDetail, ListingSummary

LISTING_PATH_RE = re.compile(r"^/(annons|bostad)/(\d+)(?:/)?$")
PRICE_RE = re.compile(r"\b\d[\d\s\u00A0]*\s*kr\b", re.IGNORECASE)


class BooliSource:
    def __init__(
        self,
        config: SourceConfig,
        *,
        request_spacing_seconds: float = 0.2,
        session: requests.Session | None = None,
    ) -> None:
        self.name = config.name
        self._config = config
        self._request_spacing_seconds = request_spacing_seconds
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
            }
        )

    def fetch_recent_listings(self) -> list[ListingSummary]:
        merged: list[ListingSummary] = []
        seen_ids: set[str] = set()
        for idx, search_url in enumerate(self._config.search_urls):
            html = self._get(search_url)
            parsed = parse_search_results_html(
                html=html,
                source_name=self.name,
                base_url=search_url,
            )
            for summary in parsed:
                if summary.listing_id in seen_ids:
                    continue
                merged.append(summary)
                seen_ids.add(summary.listing_id)
                if len(merged) >= self._config.max_listings_per_run:
                    return merged
            if idx < len(self._config.search_urls) - 1:
                time.sleep(self._request_spacing_seconds)
        return merged

    def fetch_listing_detail(self, summary: ListingSummary) -> ListingDetail:
        html = self._get(summary.url)
        return parse_listing_detail_html(summary=summary, html=html)

    def _get(self, url: str) -> str:
        response = self._session.get(url, timeout=self._config.request_timeout_seconds)
        response.raise_for_status()
        return response.text


def parse_search_results_html(
    *,
    html: str,
    source_name: str,
    base_url: str = "https://www.booli.se",
) -> list[ListingSummary]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[ListingSummary] = []
    seen_ids: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)
        if not _is_booli_url(absolute_url):
            continue
        listing_id = _extract_listing_id(parsed.path)
        if not listing_id or listing_id in seen_ids:
            continue
        title = " ".join(anchor.stripped_strings)
        listings.append(
            ListingSummary(
                source=source_name,
                listing_id=listing_id,
                url=absolute_url,
                title=title,
            )
        )
        seen_ids.add(listing_id)
    return listings


def parse_listing_detail_html(*, summary: ListingSummary, html: str) -> ListingDetail:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup) or summary.title
    address = _extract_address(soup)
    price = _extract_price(soup)
    body_text = _extract_body_text(soup)
    return ListingDetail(
        source=summary.source,
        listing_id=summary.listing_id,
        url=summary.url,
        title=title,
        address=address,
        price=price,
        body_text=body_text,
    )


def _extract_title(soup: BeautifulSoup) -> str:
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title and og_title.get("content"):
        return str(og_title["content"]).strip()
    heading = soup.select_one("h1")
    if heading:
        return " ".join(heading.stripped_strings)
    return ""


def _extract_address(soup: BeautifulSoup) -> str:
    address_meta = soup.select_one('meta[property="og:description"]')
    if address_meta and address_meta.get("content"):
        return str(address_meta["content"]).strip()
    heading = _extract_title(soup)
    if "– Booli" in heading:
        # Example: "Lägenhet till salu på ..., Södermalm, Stockholm – Booli"
        return heading.split("– Booli", 1)[0].strip()
    return ""


def _extract_price(soup: BeautifulSoup) -> str:
    text = _extract_body_text(soup)
    match = PRICE_RE.search(text)
    return match.group(0).replace("\u00A0", " ").strip() if match else ""


def _extract_body_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    return " ".join(soup.stripped_strings)


def _is_booli_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith("booli.se")


def _extract_listing_id(path: str) -> str | None:
    match = LISTING_PATH_RE.match(path)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"

