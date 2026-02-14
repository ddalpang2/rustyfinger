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
        delivered = False
        if self._config.slack.enabled:
            delivered = self._send_slack(text) or delivered
        if self._config.email.enabled:
            delivered = self._send_email(text) or delivered
        return delivered

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

