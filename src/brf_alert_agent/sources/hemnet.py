from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from brf_alert_agent.config import SourceConfig
from brf_alert_agent.models import ListingDetail, ListingSummary

LOGGER = logging.getLogger(__name__)

LISTING_PATH_RE = re.compile(r"^/bostad/[^?#]+-(\d+)(?:/)?$")
PRICE_RE = re.compile(r"\b\d[\d\s\u00A0]*\s*kr\b", re.IGNORECASE)


class HemnetSource:
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
    base_url: str = "https://www.hemnet.se",
) -> list[ListingSummary]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[ListingSummary] = []
    seen_ids: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        absolute_url = urljoin(base_url, href)
        if not _is_hemnet_url(absolute_url):
            continue
        listing_id = _extract_listing_id(absolute_url)
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
    json_ld = _parse_json_ld(soup)
    for obj in json_ld:
        address = obj.get("address")
        if isinstance(address, dict):
            line = address.get("streetAddress")
            locality = address.get("addressLocality")
            if line and locality:
                return f"{line}, {locality}".strip()
            if line:
                return str(line).strip()
        if isinstance(address, str):
            return address.strip()
    og_desc = soup.select_one('meta[property="og:description"]')
    if og_desc and og_desc.get("content"):
        return str(og_desc["content"]).strip()
    return ""


def _extract_price(soup: BeautifulSoup) -> str:
    json_ld = _parse_json_ld(soup)
    for obj in json_ld:
        offers = obj.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price")
            currency = offers.get("priceCurrency", "SEK")
            if price:
                return f"{price} {currency}"
    text = _extract_body_text(soup)
    match = PRICE_RE.search(text)
    return match.group(0).replace("\u00A0", " ").strip() if match else ""


def _extract_body_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    return " ".join(soup.stripped_strings)


def _parse_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for node in soup.select('script[type="application/ld+json"]'):
        raw = (node.string or "").strip()
        if not raw:
            continue
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            parsed.extend(_flatten_json_ld(decoded))
        elif isinstance(decoded, list):
            for item in decoded:
                if isinstance(item, dict):
                    parsed.extend(_flatten_json_ld(item))
    return parsed


def _flatten_json_ld(obj: dict[str, Any]) -> list[dict[str, Any]]:
    graph = obj.get("@graph")
    if isinstance(graph, list):
        return [item for item in graph if isinstance(item, dict)]
    return [obj]


def _is_hemnet_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith("hemnet.se")


def _extract_listing_id(url: str) -> str | None:
    match = LISTING_PATH_RE.search(urlparse(url).path)
    if not match:
        return None
    return match.group(1)

