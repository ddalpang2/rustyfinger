from __future__ import annotations

import logging
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from brf_alert_agent.config import SourceConfig
from brf_alert_agent.models import ListingDetail, ListingSummary

LOGGER = logging.getLogger(__name__)
LISTING_PATH_RE = re.compile(r"^/(annons|bostad)/(\d+)(?:/)?$")
PRICE_RE = re.compile(r"\b\d[\d\s\u00A0]*\s*kr\b", re.IGNORECASE)
BROKER_BLOCKLIST_HOSTS = {
    "apps.apple.com",
    "facebook.com",
    "hittamaklare.se",
    "instagram.com",
    "play.google.com",
    "sbab.se",
    "www.facebook.com",
    "www.hittamaklare.se",
    "www.instagram.com",
    "www.sbab.se",
}


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
        max_pages = max(1, self._config.max_search_pages)
        for source_idx, search_url in enumerate(self._config.search_urls):
            for page in range(1, max_pages + 1):
                paged_url = _with_page_param(search_url, page)
                html = self._get(paged_url)
                parsed = parse_search_results_html(
                    html=html,
                    source_name=self.name,
                    base_url=paged_url,
                )
                if not parsed:
                    break
                newly_added_in_page = 0
                for summary in parsed:
                    if summary.listing_id in seen_ids:
                        continue
                    merged.append(summary)
                    seen_ids.add(summary.listing_id)
                    newly_added_in_page += 1
                    if len(merged) >= self._config.max_listings_per_run:
                        return merged
                if newly_added_in_page == 0:
                    break
                if page < max_pages:
                    time.sleep(self._request_spacing_seconds)
            if source_idx < len(self._config.search_urls) - 1:
                time.sleep(self._request_spacing_seconds)
        return merged

    def fetch_listing_detail(self, summary: ListingSummary) -> ListingDetail:
        html = self._get(summary.url)
        detail = parse_listing_detail_html(summary=summary, html=html)
        if not self._config.follow_broker_listing_links:
            return detail
        broker_text = self._fetch_broker_text(detail_url=summary.url, detail_html=html)
        if broker_text:
            detail.body_text = f"{detail.body_text} {broker_text}".strip()
        return detail

    def _get(self, url: str) -> str:
        response = self._session.get(url, timeout=self._config.request_timeout_seconds)
        response.raise_for_status()
        return response.text

    def _fetch_broker_text(self, *, detail_url: str, detail_html: str) -> str:
        broker_urls = extract_broker_listing_urls(
            html=detail_html,
            base_url=detail_url,
            max_links=self._config.max_broker_links_per_listing,
        )
        if not broker_urls:
            return ""
        chunks: list[str] = []
        for idx, broker_url in enumerate(broker_urls):
            try:
                broker_html = self._get(broker_url)
            except Exception as exc:
                LOGGER.warning(
                    "[%s] failed to fetch broker listing page %s: %s",
                    self.name,
                    broker_url,
                    exc,
                )
                continue
            broker_text = extract_page_text_html(broker_html)
            if not broker_text:
                continue
            chunks.append(
                f"[broker_source:{broker_url}] "
                f"{broker_text[: self._config.broker_text_max_chars]}"
            )
            if idx < len(broker_urls) - 1:
                time.sleep(self._request_spacing_seconds)
        return " ".join(chunks)


def parse_search_results_html(
    *,
    html: str,
    source_name: str,
    base_url: str = "https://www.booli.se",
) -> list[ListingSummary]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[ListingSummary] = []
    seen_ids: set[str] = set()
    anchors = soup.select("li.search-page__module-container a[href]")
    if not anchors:
        anchors = soup.select("a[href]")
    for anchor in anchors:
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


def extract_broker_listing_urls(
    *,
    html: str,
    base_url: str,
    max_links: int,
) -> list[str]:
    if max_links <= 0:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen_urls: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url in seen_urls:
            continue
        parsed = urlparse(absolute_url)
        host = (parsed.hostname or "").casefold()
        if not host or host.endswith("booli.se"):
            continue
        text = " ".join(anchor.stripped_strings).casefold()
        if host in BROKER_BLOCKLIST_HOSTS:
            continue
        if _is_probable_broker_listing_link(url=absolute_url, text=text):
            urls.append(absolute_url)
            seen_urls.add(absolute_url)
        if len(urls) >= max_links:
            break
    return urls


def extract_page_text_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    return " ".join(soup.stripped_strings)


def _is_probable_broker_listing_link(*, url: str, text: str) -> bool:
    if "läs mer hos mäklaren" in text:
        return True
    if "mäklaren" in text and "utropspris" in text:
        return True
    if "utm_source=booli" in url and "referral" in url and "till-salu" in url:
        return True
    return False


def _with_page_param(search_url: str, page: int) -> str:
    if page < 1:
        raise ValueError("page must be >= 1")
    parsed = urlparse(search_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if page == 1:
        params.pop("page", None)
    else:
        params["page"] = str(page)
    updated = parsed._replace(query=urlencode(params, doseq=True))
    return urlunparse(updated)

