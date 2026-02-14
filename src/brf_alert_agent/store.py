from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from brf_alert_agent.models import ListingDetail, ListingSummary, MatchResult


class StateStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        if not self._db_path.parent.exists():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        self._conn.close()

    def has_seen(self, summary: ListingSummary) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM seen_listings
            WHERE source = ? AND listing_id = ?
            LIMIT 1
            """,
            (summary.source, summary.listing_id),
        ).fetchone()
        return row is not None

    def mark_seen(self, detail: ListingDetail) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO seen_listings(
              source, listing_id, url, title, first_seen_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                detail.source,
                detail.listing_id,
                detail.url,
                detail.title,
                _utc_now(),
            ),
        )
        self._conn.commit()

    def has_alerted(self, summary: ListingSummary) -> bool:
        row = self._conn.execute(
            """
            SELECT 1
            FROM sent_alerts
            WHERE source = ? AND listing_id = ?
            LIMIT 1
            """,
            (summary.source, summary.listing_id),
        ).fetchone()
        return row is not None

    def mark_alerted(self, detail: ListingDetail, match: MatchResult) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO sent_alerts(
              source, listing_id, url, title, categories, matched_keywords, sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                detail.source,
                detail.listing_id,
                detail.url,
                detail.title,
                json.dumps(match.categories, ensure_ascii=False),
                json.dumps(match.matched_keywords, ensure_ascii=False),
                _utc_now(),
            ),
        )
        self._conn.commit()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen_listings (
                source TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                first_seen_at TEXT NOT NULL,
                PRIMARY KEY (source, listing_id)
            );

            CREATE TABLE IF NOT EXISTS sent_alerts (
                source TEXT NOT NULL,
                listing_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                categories TEXT NOT NULL,
                matched_keywords TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (source, listing_id)
            );
            """
        )
        self._conn.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

