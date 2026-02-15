from pathlib import Path

from brf_alert_agent.models import ListingSummary
from brf_alert_agent.sources.booli import (
    parse_listing_detail_html,
    parse_search_results_html,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_search_results_html_extracts_unique_listing_links() -> None:
    html = (FIXTURE_DIR / "booli_search_sample.html").read_text(encoding="utf-8")
    listings = parse_search_results_html(
        html=html,
        source_name="booli-test",
        base_url="https://www.booli.se",
    )
    assert len(listings) == 2
    assert listings[0].listing_id == "annons-6010724"
    assert listings[1].listing_id == "bostad-4395362"
    assert listings[0].url == "https://www.booli.se/annons/6010724"


def test_parse_listing_detail_html_extracts_title_address_and_price() -> None:
    html = (FIXTURE_DIR / "booli_listing_sample.html").read_text(encoding="utf-8")
    summary = ListingSummary(
        source="booli-test",
        listing_id="annons-6010724",
        url="https://www.booli.se/annons/6010724",
        title="fallback title",
    )
    detail = parse_listing_detail_html(summary=summary, html=html)
    assert "Vasastan" in detail.title
    assert "Testgatan 1" in detail.address
    assert detail.price == "5 995 000 kr"
    assert "andrahandsuthyrning" in detail.body_text

