#!/usr/bin/env python3
"""Telegram bot that replies to '집' with filtered Booli listings."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


TRIGGER_TEXT = "집"

BOOLI_QUERY = (
    "objectType=L%C3%A4genhet&minRooms=3&minListPrice=6000000&maxListPrice=8000000"
)
AREAS = {
    "KUN": "115353",  # Kungsholmen
    "SOF": "4796",  # Sofia (Sodermalm)
}

EXCLUDED_TERMS_KUNG = ("stadshagen", "kristineberg", "hornsberg")

DEFAULT_MAX_DAYS_ACTIVE = 90
DEFAULT_KUNG_LON_MIN = 18.017
DEFAULT_KUNG_LAT_MAX = 59.3365

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
)


@dataclass
class Listing:
    area_tag: str
    address: str
    subarea: str
    url: str
    days_active: int
    size: str
    floor: str
    avgift: str
    avgift_raw: int | None
    balcony: str
    garage: str
    estimate_raw: int | None
    estimate_text: str
    popularity: str
    negotiation: str
    lat: float | None
    lon: float | None


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def http_get_text(url: str, timeout: int = 30) -> str:
    req = Request(
        url,
        method="GET",
        headers={
            # Booli returns 403 for the default urllib user-agent.
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def http_get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    text = http_get_text(url, timeout=timeout)
    return json.loads(text)


def http_post_form_json(url: str, form_data: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    body = urlencode(form_data).encode("utf-8")
    req = Request(url, data=body, method="POST")
    with urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    return json.loads(text)


def telegram_api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def get_updates(token: str, offset: int | None, timeout: int) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        payload["offset"] = offset
    data = http_post_form_json(telegram_api_url(token, "getUpdates"), payload, timeout=timeout + 5)
    if not data.get("ok"):
        raise RuntimeError(f"getUpdates failed: {data}")
    return data.get("result", [])


def send_message(token: str, chat_id: int, text: str, dry_run: bool = False) -> None:
    if dry_run:
        print(f"\n--- DRY RUN sendMessage chat_id={chat_id} ---\n{text}\n")
        return
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "disable_web_page_preview": "true",
    }
    data = http_post_form_json(telegram_api_url(token, "sendMessage"), payload)
    if not data.get("ok"):
        raise RuntimeError(f"sendMessage failed: {data}")


def send_in_chunks(token: str, chat_id: int, text: str, dry_run: bool) -> None:
    max_len = 3900
    if len(text) <= max_len:
        send_message(token, chat_id, text, dry_run=dry_run)
        return

    lines = text.splitlines()
    current: list[str] = []
    current_len = 0

    for line in lines:
        extra = len(line) + (1 if current else 0)
        if current and current_len + extra > max_len:
            send_message(token, chat_id, "\n".join(current), dry_run=dry_run)
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += extra

    if current:
        send_message(token, chat_id, "\n".join(current), dry_run=dry_run)


def extract_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html)
    if not match:
        raise RuntimeError("Could not locate __NEXT_DATA__ in Booli page.")
    return json.loads(unescape(match.group(1)))


def parse_display_points(display_attributes: dict[str, Any]) -> tuple[str, str, str, str, int | None]:
    size = "-"
    rooms = "-"
    floor = "-"
    avgift = "N/A"
    avgift_raw: int | None = None

    for point in display_attributes.get("dataPoints", []):
        text = (((point.get("value") or {}).get("plainText")) or "").strip()
        if not text:
            continue
        if "m²" in text and size == "-":
            size = text
        if "rum" in text and rooms == "-":
            rooms = text
        if text.lower().startswith("vån") and floor == "-":
            floor = text
        if "kr/mån" in text:
            avgift = text
            digits = "".join(ch for ch in text if ch.isdigit())
            if digits:
                avgift_raw = int(digits)
    return size, rooms, floor, avgift, avgift_raw


def parse_listing(apollo: dict[str, Any], listing_obj: dict[str, Any], area_tag: str, max_days_active: int) -> Listing | None:
    days = listing_obj.get("daysActive")
    if not isinstance(days, int) or days > max_days_active:
        return None

    size, _, floor, avgift, avgift_raw = parse_display_points(
        listing_obj.get("displayAttributes") or {}
    )

    amenities: list[str] = []
    for amenity_ref in listing_obj.get("amenities") or []:
        amenity = apollo.get(amenity_ref.get("__ref", ""), {})
        key = amenity.get("key")
        if isinstance(key, str):
            amenities.append(key)

    balcony = "O" if any(key in ("balcony", "patio") for key in amenities) else "X/?"
    garage = "O" if any(key in ("garage", "parking") for key in amenities) else "X/?"

    estimate = ((listing_obj.get("estimate") or {}).get("price")) or {}
    list_price = listing_obj.get("listPrice") or {}
    estimate_raw = estimate.get("raw")
    list_raw = list_price.get("raw")

    popularity = "높음" if days <= 7 else ("보통" if days <= 30 else "낮음")
    if isinstance(estimate_raw, int) and isinstance(list_raw, int) and list_raw <= estimate_raw and days <= 10:
        negotiation = "낮음"
    elif days > 30 or (
        isinstance(estimate_raw, int) and isinstance(list_raw, int) and list_raw > estimate_raw * 1.05
    ):
        negotiation = "높음"
    else:
        negotiation = "보통"

    return Listing(
        area_tag=area_tag,
        address=listing_obj.get("streetAddress") or "-",
        subarea=listing_obj.get("descriptiveAreaName") or "-",
        url=urljoin("https://www.booli.se", listing_obj.get("url") or ""),
        days_active=days,
        size=size,
        floor=floor,
        avgift=avgift,
        avgift_raw=avgift_raw,
        balcony=balcony,
        garage=garage,
        estimate_raw=estimate_raw if isinstance(estimate_raw, int) else None,
        estimate_text=estimate.get("formatted") or "N/A",
        popularity=popularity,
        negotiation=negotiation,
        lat=listing_obj.get("latitude"),
        lon=listing_obj.get("longitude"),
    )


def extract_search_ref(root_query: dict[str, Any]) -> str:
    for key in root_query.keys():
        if key.startswith('searchForSale({"input"') and "forceOnlyNewConstruction" not in key:
            return key
    raise RuntimeError("Could not find searchForSale key in ROOT_QUERY.")


def fetch_area_listings(area_tag: str, area_id: str, max_days_active: int) -> list[Listing]:
    first_url = f"https://www.booli.se/sok/till-salu?areaIds={area_id}&{BOOLI_QUERY}&page=1"
    first_html = http_get_text(first_url)
    first_data = extract_next_data(first_html)
    apollo = first_data["props"]["pageProps"]["__APOLLO_STATE__"]
    root_query = apollo["ROOT_QUERY"]
    search_ref = extract_search_ref(root_query)
    pages = int(root_query[search_ref].get("pages") or 1)

    all_listings: dict[str, Listing] = {}

    for page in range(1, pages + 1):
        url = f"https://www.booli.se/sok/till-salu?areaIds={area_id}&{BOOLI_QUERY}&page={page}"
        html = http_get_text(url)
        data = extract_next_data(html)
        apollo_page = data["props"]["pageProps"]["__APOLLO_STATE__"]
        root_query_page = apollo_page["ROOT_QUERY"]
        search_ref_page = extract_search_ref(root_query_page)

        for row in root_query_page[search_ref_page].get("result", []):
            ref = row.get("__ref")
            if not isinstance(ref, str) or not ref.startswith("Listing:"):
                continue
            listing_obj = apollo_page.get(ref, {})
            if listing_obj.get("__typename") != "Listing":
                continue
            listing = parse_listing(apollo_page, listing_obj, area_tag, max_days_active)
            if listing is None:
                continue
            all_listings[listing.url] = listing

    return list(all_listings.values())


def filter_kungsholmen(listings: list[Listing], lon_min: float, lat_max: float) -> list[Listing]:
    filtered: list[Listing] = []
    for listing in listings:
        text = f"{listing.subarea} {listing.address}".lower()
        if any(term in text for term in EXCLUDED_TERMS_KUNG):
            continue
        if isinstance(listing.lat, (int, float)) and isinstance(listing.lon, (int, float)):
            if listing.lon < lon_min or listing.lat > lat_max:
                continue
        filtered.append(listing)
    return filtered


def collect_listings(max_days_active: int, lon_min: float, lat_max: float) -> list[Listing]:
    kung = fetch_area_listings("KUN", AREAS["KUN"], max_days_active=max_days_active)
    kung = filter_kungsholmen(kung, lon_min=lon_min, lat_max=lat_max)
    sofia = fetch_area_listings("SOF", AREAS["SOF"], max_days_active=max_days_active)
    combined = {listing.url: listing for listing in kung + sofia}
    return list(combined.values())


def bucket_and_sort(listings: list[Listing]) -> dict[str, list[Listing]]:
    buckets = {
        "<=7.0M": [],
        "7.0M-7.5M": [],
        "7.5M-8.0M": [],
        "기타": [],
    }

    for listing in listings:
        est = listing.estimate_raw
        if est is None:
            buckets["기타"].append(listing)
        elif est <= 7_000_000:
            buckets["<=7.0M"].append(listing)
        elif est <= 7_500_000:
            buckets["7.0M-7.5M"].append(listing)
        elif est <= 8_000_000:
            buckets["7.5M-8.0M"].append(listing)
        else:
            buckets["기타"].append(listing)

    for values in buckets.values():
        values.sort(
            key=lambda item: (
                item.avgift_raw is None,
                item.avgift_raw if item.avgift_raw is not None else 10**12,
            )
        )
    return buckets


def format_report(listings: list[Listing], max_days_active: int) -> list[str]:
    buckets = bucket_and_sort(listings)
    count_kun = sum(1 for item in listings if item.area_tag == "KUN")
    count_sof = sum(1 for item in listings if item.area_tag == "SOF")

    messages = [
        (
            "[Booli 결과]\n"
            "조건: 아파트, 3룸+, 6M~8M\n"
            f"추가필터: 장기매물 > {max_days_active}일 제외\n"
            "지역: Kungsholmen(서/북, Hornsberg/Kristineberg/Stadshagen 제외) + Sofia\n"
            f"총 {len(listings)}건 (KUN {count_kun} / SOF {count_sof})"
        )
    ]

    for bucket_name in ("<=7.0M", "7.0M-7.5M", "7.5M-8.0M", "기타"):
        rows = buckets[bucket_name]
        lines = [f"[{bucket_name}] {len(rows)}건 (avgift 낮은 순)"]
        for index, item in enumerate(rows, start=1):
            lines.append(
                (
                    f"{index}. [{item.area_tag}] {item.address} | est {item.estimate_text} | "
                    f"avgift {item.avgift} | {item.size}, {item.floor} | "
                    f"balc {item.balcony}, garage {item.garage} | {item.days_active}d | "
                    f"인기 {item.popularity}, 협상 {item.negotiation}\n"
                    f"{item.url}"
                )
            )
        messages.append("\n".join(lines))
    return messages


def process_trigger_message(token: str, chat_id: int, max_days_active: int, lon_min: float, lat_max: float, dry_run: bool) -> None:
    send_message(token, chat_id, "요청 확인! Booli 조건으로 검색 중...", dry_run=dry_run)
    listings = collect_listings(max_days_active=max_days_active, lon_min=lon_min, lat_max=lat_max)
    for message in format_report(listings, max_days_active=max_days_active):
        send_in_chunks(token, chat_id, message, dry_run=dry_run)


def load_offset(path: str) -> int | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        return int(value) if value else None
    except FileNotFoundError:
        return None
    except ValueError:
        return None


def save_offset(path: str, offset: int) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(str(offset))


def handle_update(
    token: str,
    update: dict[str, Any],
    max_days_active: int,
    lon_min: float,
    lat_max: float,
    dry_run: bool,
) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    text = (message.get("text") or "").strip()
    if not text:
        return

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return

    if text == TRIGGER_TEXT:
        process_trigger_message(
            token=token,
            chat_id=chat_id,
            max_days_active=max_days_active,
            lon_min=lon_min,
            lat_max=lat_max,
            dry_run=dry_run,
        )
    elif text == "/start":
        send_message(
            token,
            chat_id,
            "안녕하세요! '집' 이라고 보내면 조건에 맞는 Booli 매물을 보내드려요.",
            dry_run=dry_run,
        )


def run_once(
    token: str,
    offset_path: str,
    timeout: int,
    max_days_active: int,
    lon_min: float,
    lat_max: float,
    dry_run: bool,
) -> None:
    offset = load_offset(offset_path)
    updates = get_updates(token, offset=offset, timeout=timeout)
    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            handle_update(
                token=token,
                update=update,
                max_days_active=max_days_active,
                lon_min=lon_min,
                lat_max=lat_max,
                dry_run=dry_run,
            )
            save_offset(offset_path, update_id + 1)


def run_poll(
    token: str,
    offset_path: str,
    timeout: int,
    poll_sleep: float,
    max_days_active: int,
    lon_min: float,
    lat_max: float,
    dry_run: bool,
) -> None:
    while True:
        try:
            run_once(
                token=token,
                offset_path=offset_path,
                timeout=timeout,
                max_days_active=max_days_active,
                lon_min=lon_min,
                lat_max=lat_max,
                dry_run=dry_run,
            )
        except (HTTPError, URLError, TimeoutError, RuntimeError) as err:
            print(f"[warn] polling error: {err}")
            time.sleep(max(2.0, poll_sleep))
        time.sleep(poll_sleep)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reply to Telegram trigger with Booli results.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process current updates once and exit.",
    )
    parser.add_argument(
        "--poll-sleep",
        type=float,
        default=1.0,
        help="Sleep between poll cycles (seconds).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Telegram getUpdates timeout in seconds.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call sendMessage; print outgoing text only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Missing TELEGRAM_BOT_TOKEN environment variable.")
        return 1

    offset_path = os.getenv("TELEGRAM_OFFSET_FILE", ".telegram_offset")
    max_days_active = env_int("BOOLI_MAX_DAYS_ACTIVE", DEFAULT_MAX_DAYS_ACTIVE)
    lon_min = env_float("BOOLI_KUNG_LON_MIN", DEFAULT_KUNG_LON_MIN)
    lat_max = env_float("BOOLI_KUNG_LAT_MAX", DEFAULT_KUNG_LAT_MAX)

    if args.once:
        run_once(
            token=token,
            offset_path=offset_path,
            timeout=args.timeout,
            max_days_active=max_days_active,
            lon_min=lon_min,
            lat_max=lat_max,
            dry_run=args.dry_run,
        )
    else:
        run_poll(
            token=token,
            offset_path=offset_path,
            timeout=args.timeout,
            poll_sleep=args.poll_sleep,
            max_days_active=max_days_active,
            lon_min=lon_min,
            lat_max=lat_max,
            dry_run=args.dry_run,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
