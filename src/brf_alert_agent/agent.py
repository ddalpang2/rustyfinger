from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from brf_alert_agent.config import AgentConfig, SourceConfig
from brf_alert_agent.matching import evaluate_listing
from brf_alert_agent.notify import NotificationDispatcher
from brf_alert_agent.sources.base import ListingSource
from brf_alert_agent.sources.hemnet import HemnetSource
from brf_alert_agent.store import StateStore

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RunStats:
    discovered: int = 0
    new_checked: int = 0
    matched: int = 0
    alerted: int = 0
    matched_listing_urls: list[str] = field(default_factory=list)
    source_errors: list[str] = field(default_factory=list)


class BrfAlertAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._store = StateStore(config.state_db_path)
        self._notifier = NotificationDispatcher(config.notifications)
        self._sources = [
            _build_source(source_config, config.run.request_spacing_seconds)
            for source_config in config.sources
        ]

    def close(self) -> None:
        self._store.close()

    def run_once(self) -> RunStats:
        stats = RunStats()
        for source in self._sources:
            try:
                stats_for_source = self._run_source_once(source)
            except Exception as exc:
                LOGGER.exception("[%s] source run failed.", source.name)
                stats.source_errors.append(f"{source.name}: {exc}")
                continue
            stats.discovered += stats_for_source.discovered
            stats.new_checked += stats_for_source.new_checked
            stats.matched += stats_for_source.matched
            stats.alerted += stats_for_source.alerted
            stats.matched_listing_urls.extend(stats_for_source.matched_listing_urls)
            stats.source_errors.extend(stats_for_source.source_errors)
        if self._config.run.send_summary_after_run:
            try:
                self._notifier.send_run_summary(
                    discovered=stats.discovered,
                    new_checked=stats.new_checked,
                    matched=stats.matched,
                    alerted=stats.alerted,
                    source_errors=stats.source_errors,
                    matched_listing_urls=stats.matched_listing_urls,
                    max_matches=self._config.run.summary_max_matches,
                    max_errors=self._config.run.summary_max_errors,
                )
            except Exception:
                LOGGER.exception("Failed to send run summary notification.")
        LOGGER.info(
            "Run complete: discovered=%s new_checked=%s matched=%s alerted=%s source_errors=%s",
            stats.discovered,
            stats.new_checked,
            stats.matched,
            stats.alerted,
            len(stats.source_errors),
        )
        return stats

    def run_forever(self) -> None:
        interval = self._config.run.poll_interval_seconds
        while True:
            started = time.time()
            try:
                self.run_once()
            except Exception:  # pragma: no cover - defensive runtime logging
                LOGGER.exception("Unexpected error while running alert loop.")
            elapsed = time.time() - started
            sleep_seconds = max(interval - elapsed, 0)
            LOGGER.info("Sleeping for %.1f seconds", sleep_seconds)
            time.sleep(sleep_seconds)

    def _run_source_once(self, source: ListingSource) -> RunStats:
        source_stats = RunStats()
        summaries = source.fetch_recent_listings()
        source_stats.discovered = len(summaries)
        LOGGER.info("[%s] discovered %s listings", source.name, len(summaries))

        for summary in summaries:
            if self._store.has_seen(summary):
                continue

            detail = source.fetch_listing_detail(summary)
            source_stats.new_checked += 1
            self._store.mark_seen(detail)
            match = evaluate_listing(detail, self._config.matching)
            if not match.is_match:
                continue

            source_stats.matched += 1
            try:
                sent = self._notifier.send(detail, match)
            except Exception:
                LOGGER.exception(
                    "Failed to send notification for listing %s", detail.url
                )
                sent = False
            if sent:
                source_stats.alerted += 1
            self._store.mark_alerted(detail, match)
            source_stats.matched_listing_urls.append(detail.url)
            LOGGER.info(
                "[%s] matched listing %s (alerted=%s)",
                source.name,
                detail.url,
                sent,
            )
        return source_stats


def _build_source(source: SourceConfig, request_spacing_seconds: float) -> ListingSource:
    source_type = source.type.casefold()
    if source_type == "hemnet":
        return HemnetSource(
            source,
            request_spacing_seconds=request_spacing_seconds,
        )
    raise ValueError(f"Unsupported source type: {source.type}")

