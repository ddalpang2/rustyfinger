from __future__ import annotations

import re

from brf_alert_agent.config import MatchingConfig
from brf_alert_agent.models import ListingDetail, MatchResult

MULTI_SPACE_RE = re.compile(r"\s+")


def evaluate_listing(detail: ListingDetail, config: MatchingConfig) -> MatchResult:
    haystack = normalize_text(
        " ".join(
            [
                detail.title,
                detail.address,
                detail.body_text,
            ]
        )
    )

    reasons: list[str] = []
    matched_keywords: list[str] = []

    if config.require_brf_keyword:
        brf_matches = find_matching_keywords(haystack, config.brf_keywords)
        if not brf_matches:
            return MatchResult(
                is_match=False,
                reasons=["Missing BRF keyword requirement."],
            )
        matched_keywords.extend(brf_matches)
        reasons.append("BRF keyword requirement matched.")

    if config.enforce_innerstad_keyword:
        area_matches = find_matching_keywords(haystack, config.innerstad_keywords)
        if not area_matches:
            return MatchResult(
                is_match=False,
                reasons=["Missing Stockholm innerstad keyword requirement."],
            )
        matched_keywords.extend(area_matches)
        reasons.append("Stockholm innerstad keyword requirement matched.")

    categories: list[str] = []
    whole_unit_matches = find_matching_keywords(
        haystack, config.whole_unit_rental_keywords
    )
    if whole_unit_matches:
        categories.append("whole_unit_rentable")
        matched_keywords.extend(whole_unit_matches)
        reasons.append("Found keywords indicating andrahandsuthyrning is possible.")

    separate_entrance_matches = find_matching_keywords(
        haystack, config.separate_entrance_keywords
    )
    if separate_entrance_matches:
        categories.append("room_with_separate_entrance")
        matched_keywords.extend(separate_entrance_matches)
        reasons.append("Found keywords indicating separate entrance/uthyrningsdel.")

    return MatchResult(
        is_match=bool(categories),
        categories=categories,  # type: ignore[arg-type]
        matched_keywords=sorted(set(matched_keywords)),
        reasons=reasons
        if categories
        else ["Listing does not satisfy rental-friendly keyword filters."],
    )


def find_matching_keywords(normalized_text: str, keywords: list[str]) -> list[str]:
    matches: list[str] = []
    for keyword in keywords:
        normalized_keyword = normalize_text(keyword)
        if normalized_keyword and normalized_keyword in normalized_text:
            matches.append(keyword)
    return matches


def normalize_text(value: str) -> str:
    return MULTI_SPACE_RE.sub(" ", value).strip().casefold()

