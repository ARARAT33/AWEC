"""Persistent Frontier Queue for AWEC engine."""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from awec.core.canonicalizer import URLCanonicalizer
from awec.storage.state_store import StateStore


class Frontier:
    def __init__(self, store: StateStore):
        self.store = store

    def add_url(self, url: str, depth: int = 0, parent_url: str = "", discovery_type: str = "seed", priority: int = 0) -> bool:
        canonical = URLCanonicalizer.canonicalize(url)
        if not canonical:
            return False
        domain = urlparse(canonical).netloc.lower()
        now = datetime.now(timezone.utc).isoformat()

        with self.store.lock, self.store._get_conn() as conn:
            try:
                conn.execute("""
                    INSERT INTO frontier (
                        url, canonical_url, domain, depth, priority, parent_url, discovery_type, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """, (url, canonical, domain, depth, priority, parent_url, discovery_type, now))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def pop_next(self) -> Optional[Dict]:
        now_ts = time.time()
        with self.store.lock, self.store._get_conn() as conn:
            cur = conn.execute("""
                SELECT * FROM frontier
                WHERE status = 'pending' AND next_fetch_at <= ?
                ORDER BY priority DESC, depth ASC, id ASC
                LIMIT 1
            """, (now_ts,))
            row = cur.fetchone()
            if not row:
                return None

            item = dict(row)
            conn.execute("UPDATE frontier SET status = 'in_progress' WHERE id = ?", (item["id"],))
            conn.commit()
            return item

    def mark_completed(self, item_id: int) -> None:
        with self.store.lock, self.store._get_conn() as conn:
            conn.execute("UPDATE frontier SET status = 'completed' WHERE id = ?", (item_id,))
            conn.commit()

    def mark_failed(self, item_id: int, retry_delay: float = 0.0) -> None:
        now_ts = time.time() + retry_delay
        with self.store.lock, self.store._get_conn() as conn:
            conn.execute("""
                UPDATE frontier
                SET status = 'pending', retries = retries + 1, next_fetch_at = ?
                WHERE id = ?
            """, (now_ts, item_id))
            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        with self.store.lock, self.store._get_conn() as conn:
            cur = conn.execute("SELECT status, COUNT(*) as cnt FROM frontier GROUP BY status")
            stats = {row["status"]: row["cnt"] for row in cur.fetchall()}
            return {
                "pending": stats.get("pending", 0),
                "in_progress": stats.get("in_progress", 0),
                "completed": stats.get("completed", 0),
                "failed": stats.get("failed", 0),
            }
