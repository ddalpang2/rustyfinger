from __future__ import annotations

import json
import logging
import smtplib
from email.message import EmailMessage

import requests

from brf_alert_agent.config import NotificationConfig
from brf_alert_agent.models import ListingDetail, MatchResult

LOGGER = logging.getLogger(__name__)


class NotificationDispatcher:
    def __init__(
        self,
        config: NotificationConfig,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self._config = config
        self._session = session or requests.Session()

    def send(self, detail: ListingDetail, match: MatchResult) -> bool:
        text = self._build_message(detail, match)
        return self._send_to_enabled_channels(text)

    def send_run_summary(
        self,
        *,
        discovered: int,
        new_checked: int,
        matched: int,
        alerted: int,
        source_errors: list[str],
        matched_listing_urls: list[str],
        max_matches: int = 5,
        max_errors: int = 5,
    ) -> bool:
        text = self._build_summary_message(
            discovered=discovered,
            new_checked=new_checked,
            matched=matched,
            alerted=alerted,
            source_errors=source_errors,
            matched_listing_urls=matched_listing_urls,
            max_matches=max_matches,
            max_errors=max_errors,
        )
        return self._send_to_enabled_channels(text)

    def _build_message(self, detail: ListingDetail, match: MatchResult) -> str:
        categories = ", ".join(match.categories) if match.categories else "unknown"
        keywords = ", ".join(match.matched_keywords) if match.matched_keywords else "-"
        title = detail.title or "(no title)"
        address = detail.address or "(no address parsed)"
        price = detail.price or "(no price parsed)"
        return (
            "새 BRF 후보 매물 감지\n"
            f"- Source: {detail.source}\n"
            f"- Title: {title}\n"
            f"- Address: {address}\n"
            f"- Price: {price}\n"
            f"- Categories: {categories}\n"
            f"- Matched keywords: {keywords}\n"
            f"- URL: {detail.url}"
        )

    def _build_summary_message(
        self,
        *,
        discovered: int,
        new_checked: int,
        matched: int,
        alerted: int,
        source_errors: list[str],
        matched_listing_urls: list[str],
        max_matches: int,
        max_errors: int,
    ) -> str:
        lines = [
            "BRF daily run summary",
            f"- discovered: {discovered}",
            f"- new_checked: {new_checked}",
            f"- matched: {matched}",
            f"- alerted: {alerted}",
        ]
        if matched_listing_urls:
            lines.append("- matched_listing_urls:")
            for url in matched_listing_urls[:max_matches]:
                lines.append(f"  - {url}")
            extra_matches = len(matched_listing_urls) - max_matches
            if extra_matches > 0:
                lines.append(f"  - ... and {extra_matches} more")
        if source_errors:
            lines.append("- source_errors:")
            for error in source_errors[:max_errors]:
                lines.append(f"  - {error}")
            extra_errors = len(source_errors) - max_errors
            if extra_errors > 0:
                lines.append(f"  - ... and {extra_errors} more")
        if not matched_listing_urls and not source_errors:
            lines.append("- note: no matches and no source errors.")
        return "\n".join(lines)

    def _send_to_enabled_channels(self, text: str) -> bool:
        delivered = False
        if self._config.slack.enabled:
            delivered = self._send_slack(text) or delivered
        if self._config.email.enabled:
            delivered = self._send_email(text) or delivered
        if self._config.telegram.enabled:
            delivered = self._send_telegram(text) or delivered
        if not delivered:
            LOGGER.info("No notification channel delivered this message.")
        return delivered

    def _send_slack(self, text: str) -> bool:
        webhook_url = self._config.slack.webhook_url
        if not webhook_url:
            LOGGER.warning("Slack is enabled but webhook_url is empty.")
            return False
        response = self._session.post(
            webhook_url,
            data=json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        response.raise_for_status()
        return True

    def _send_email(self, text: str) -> bool:
        email = self._config.email
        if not all([email.username, email.password, email.from_email, email.to_emails]):
            LOGGER.warning("Email is enabled but required SMTP fields are missing.")
            return False
        msg = EmailMessage()
        msg["Subject"] = "Stockholm BRF alert"
        msg["From"] = email.from_email
        msg["To"] = ", ".join(email.to_emails)
        msg.set_content(text)

        with smtplib.SMTP(email.smtp_host, email.smtp_port, timeout=20) as smtp:
            if email.use_tls:
                smtp.starttls()
            smtp.login(email.username, email.password)
            smtp.send_message(msg)
        return True

    def _send_telegram(self, text: str) -> bool:
        telegram = self._config.telegram
        if not telegram.bot_token or not telegram.chat_id:
            LOGGER.warning(
                "Telegram is enabled but bot_token/chat_id is missing."
            )
            return False
        endpoint = f"https://api.telegram.org/bot{telegram.bot_token}/sendMessage"
        payload = {
            "chat_id": telegram.chat_id,
            "text": text,
            "disable_web_page_preview": telegram.disable_web_page_preview,
        }
        response = self._session.post(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=15,
        )
        response.raise_for_status()
        return True

