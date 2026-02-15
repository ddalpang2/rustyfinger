from pathlib import Path

from brf_alert_agent.models import ListingSummary
from brf_alert_agent.sources.hemnet import (
    parse_listing_detail_html,
    parse_search_results_html,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_search_results_html_extracts_unique_listing_links() -> None:
    html = (FIXTURE_DIR / "hemnet_search_sample.html").read_text(encoding="utf-8")
    listings = parse_search_results_html(
        html=html,
        source_name="hemnet-test",
        base_url="https://www.hemnet.se",
    )
    assert len(listings) == 2
    assert listings[0].listing_id == "12345678"
    assert listings[1].listing_id == "87654321"
    assert listings[0].url.startswith("https://www.hemnet.se/bostad/")


def test_parse_listing_detail_html_extracts_title_address_and_price() -> None:
    html = (FIXTURE_DIR / "hemnet_listing_sample.html").read_text(encoding="utf-8")
    summary = ListingSummary(
        source="hemnet-test",
        listing_id="12345678",
        url="https://www.hemnet.se/bostad/lagenhet-2rum-test-12345678",
        title="fallback title",
    )
    detail = parse_listing_detail_html(summary=summary, html=html)
    assert "BRF Exempelhuset" in detail.title
    assert "Exempelgatan 9" in detail.address
    assert detail.price == "5995000 SEK"
    assert "separat ingång" in detail.body_text

