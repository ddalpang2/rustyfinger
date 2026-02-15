from brf_alert_agent.config import MatchingConfig
from brf_alert_agent.matching import evaluate_listing
from brf_alert_agent.models import ListingDetail


def _sample_detail(text: str) -> ListingDetail:
    return ListingDetail(
        source="hemnet-test",
        listing_id="1",
        url="https://example.com/listing/1",
        title="Bostadsrätt i Vasastan",
        address="Vasastan, Stockholm",
        body_text=text,
    )


def test_evaluate_listing_matches_both_categories() -> None:
    detail = _sample_detail(
        "Föreningen godkänner andrahandsuthyrning. "
        "Lägenheten har separat ingång för uthyrningsdel."
    )
    result = evaluate_listing(detail, MatchingConfig())
    assert result.is_match
    assert "whole_unit_rentable" in result.categories
    assert "room_with_separate_entrance" in result.categories


def test_evaluate_listing_fails_without_brf_keyword() -> None:
    detail = ListingDetail(
        source="hemnet-test",
        listing_id="2",
        url="https://example.com/listing/2",
        title="Lägenhet i Vasastan",
        address="Vasastan, Stockholm",
        body_text="Möjlighet till andrahandsuthyrning.",
    )
    cfg = MatchingConfig(require_brf_keyword=True)
    result = evaluate_listing(detail, cfg)
    assert not result.is_match
    assert "Missing BRF keyword requirement." in result.reasons


def test_evaluate_listing_fails_without_innerstad_keyword() -> None:
    detail = ListingDetail(
        source="hemnet-test",
        listing_id="3",
        url="https://example.com/listing/3",
        title="Bostadsrätt i Täby",
        address="Täby",
        body_text="BRF Solsidan tillåter andrahandsuthyrning.",
    )
    cfg = MatchingConfig(enforce_innerstad_keyword=True)
    result = evaluate_listing(detail, cfg)
    assert not result.is_match
    assert "Missing Stockholm innerstad keyword requirement." in result.reasons

