from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(slots=True)
class SourceConfig:
    name: str
    type: str
    search_urls: list[str]
    max_listings_per_run: int = 80
    request_timeout_seconds: int = 20
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )


@dataclass(slots=True)
class MatchingConfig:
    require_brf_keyword: bool = True
    enforce_innerstad_keyword: bool = True
    brf_keywords: list[str] = field(
        default_factory=lambda: [
            "bostadsrätt",
            "brf",
            "förening",
            "föreningen",
        ]
    )
    innerstad_keywords: list[str] = field(
        default_factory=lambda: [
            "norrmalm",
            "östermalm",
            "södermalm",
            "kungsholmen",
            "vasastan",
            "gamla stan",
            "stockholm innerstad",
            "city",
        ]
    )
    whole_unit_rental_keywords: list[str] = field(
        default_factory=lambda: [
            "andrahandsuthyrning",
            "uthyrning i andra hand",
            "får hyras ut i andra hand",
            "tillåter andrahandsuthyrning",
            "godkänner andrahandsuthyrning",
            "möjlighet till andrahandsuthyrning",
            "subletting allowed",
        ]
    )
    separate_entrance_keywords: list[str] = field(
        default_factory=lambda: [
            "separat ingång",
            "egen ingång",
            "egen entré",
            "uthyrningsdel",
            "delbar planlösning",
            "separate entrance",
            "private entrance",
        ]
    )


@dataclass(slots=True)
class SlackConfig:
    enabled: bool = False
    webhook_url: str | None = None


@dataclass(slots=True)
class EmailConfig:
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str | None = None
    password: str | None = None
    from_email: str | None = None
    to_emails: list[str] = field(default_factory=list)
    use_tls: bool = True


@dataclass(slots=True)
class NotificationConfig:
    slack: SlackConfig = field(default_factory=SlackConfig)
    email: EmailConfig = field(default_factory=EmailConfig)


@dataclass(slots=True)
class RunConfig:
    poll_interval_seconds: int = 900
    request_spacing_seconds: float = 0.2


@dataclass(slots=True)
class AgentConfig:
    state_db_path: str = ".data/brf_alert_agent.db"
    sources: list[SourceConfig] = field(default_factory=list)
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    run: RunConfig = field(default_factory=RunConfig)


def load_config(path: str | Path) -> AgentConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    expanded = _expand_env_values(raw)
    sources_raw = expanded.get("sources", [])
    if not sources_raw:
        raise ValueError("Config must define at least one source in 'sources'.")

    sources = [
        SourceConfig(
            name=item["name"],
            type=item.get("type", "hemnet"),
            search_urls=_as_string_list(item["search_urls"]),
            max_listings_per_run=int(item.get("max_listings_per_run", 80)),
            request_timeout_seconds=int(item.get("request_timeout_seconds", 20)),
            user_agent=item.get("user_agent", SourceConfig.__dataclass_fields__["user_agent"].default),  # type: ignore[index]
        )
        for item in sources_raw
    ]

    matching_raw = expanded.get("matching", {})
    matching = MatchingConfig(
        require_brf_keyword=bool(matching_raw.get("require_brf_keyword", True)),
        enforce_innerstad_keyword=bool(matching_raw.get("enforce_innerstad_keyword", True)),
        brf_keywords=_as_string_list(
            matching_raw.get("brf_keywords", MatchingConfig().brf_keywords)
        ),
        innerstad_keywords=_as_string_list(
            matching_raw.get("innerstad_keywords", MatchingConfig().innerstad_keywords)
        ),
        whole_unit_rental_keywords=_as_string_list(
            matching_raw.get(
                "whole_unit_rental_keywords",
                MatchingConfig().whole_unit_rental_keywords,
            )
        ),
        separate_entrance_keywords=_as_string_list(
            matching_raw.get(
                "separate_entrance_keywords",
                MatchingConfig().separate_entrance_keywords,
            )
        ),
    )

    notifications_raw = expanded.get("notifications", {})
    slack_raw = notifications_raw.get("slack", {})
    email_raw = notifications_raw.get("email", {})
    notifications = NotificationConfig(
        slack=SlackConfig(
            enabled=bool(slack_raw.get("enabled", False)),
            webhook_url=slack_raw.get("webhook_url"),
        ),
        email=EmailConfig(
            enabled=bool(email_raw.get("enabled", False)),
            smtp_host=email_raw.get("smtp_host", "smtp.gmail.com"),
            smtp_port=int(email_raw.get("smtp_port", 587)),
            username=email_raw.get("username"),
            password=email_raw.get("password"),
            from_email=email_raw.get("from_email"),
            to_emails=_as_string_list(email_raw.get("to_emails", [])),
            use_tls=bool(email_raw.get("use_tls", True)),
        ),
    )

    run_raw = expanded.get("run", {})
    run = RunConfig(
        poll_interval_seconds=int(run_raw.get("poll_interval_seconds", 900)),
        request_spacing_seconds=float(run_raw.get("request_spacing_seconds", 0.2)),
    )

    return AgentConfig(
        state_db_path=expanded.get("state_db_path", ".data/brf_alert_agent.db"),
        sources=sources,
        matching=matching,
        notifications=notifications,
        run=run,
    )


def _expand_env_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _expand_env_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_values(v) for v in value]
    if isinstance(value, str):
        return ENV_PATTERN.sub(lambda m: os.getenv(m.group(1), ""), value)
    return value


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise TypeError(f"Expected list[str], got {type(value)}")
    return [str(item) for item in value]

