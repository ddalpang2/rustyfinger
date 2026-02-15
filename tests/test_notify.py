import json

from brf_alert_agent.config import NotificationConfig, TelegramConfig
from brf_alert_agent.models import ListingDetail, MatchResult
from brf_alert_agent.notify import NotificationDispatcher


class _DummyResponse:
    def raise_for_status(self) -> None:
        return None


class _DummySession:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> _DummyResponse:
        self.calls.append(
            {
                "url": url,
                "data": data,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _DummyResponse()


def _sample_detail() -> ListingDetail:
    return ListingDetail(
        source="hemnet-test",
        listing_id="123",
        url="https://example.com/listing/123",
        title="BRF Example",
        address="Vasastan, Stockholm",
        price="5000000 SEK",
        body_text="Föreningen tillåter andrahandsuthyrning.",
    )


def _sample_match() -> MatchResult:
    return MatchResult(
        is_match=True,
        categories=["whole_unit_rentable"],
        matched_keywords=["andrahandsuthyrning"],
    )


def test_send_listing_alert_to_telegram() -> None:
    session = _DummySession()
    dispatcher = NotificationDispatcher(
        NotificationConfig(
            telegram=TelegramConfig(
                enabled=True,
                bot_token="TEST_TOKEN",
                chat_id="123456",
            )
        ),
        session=session,
    )

    delivered = dispatcher.send(_sample_detail(), _sample_match())

    assert delivered
    assert len(session.calls) == 1
    assert "https://api.telegram.org/botTEST_TOKEN/sendMessage" == session.calls[0]["url"]


def test_send_run_summary_to_telegram() -> None:
    session = _DummySession()
    dispatcher = NotificationDispatcher(
        NotificationConfig(
            telegram=TelegramConfig(
                enabled=True,
                bot_token="TEST_TOKEN",
                chat_id="123456",
                disable_web_page_preview=False,
            )
        ),
        session=session,
    )

    delivered = dispatcher.send_run_summary(
        discovered=12,
        new_checked=4,
        matched=1,
        alerted=1,
        source_errors=["hemnet-innerstad: 403 Client Error"],
        matched_listing_urls=["https://example.com/listing/123"],
        max_matches=5,
        max_errors=5,
    )

    assert delivered
    assert len(session.calls) == 1
    payload = json.loads((session.calls[0]["data"] or b"").decode("utf-8"))
    assert payload["chat_id"] == "123456"
    assert payload["disable_web_page_preview"] is False
    assert "BRF daily run summary" in payload["text"]
    assert "hemnet-innerstad: 403 Client Error" in payload["text"]

