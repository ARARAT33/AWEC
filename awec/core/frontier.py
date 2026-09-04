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
    def __init__(self, store: StateStore, mode: str = "breadth_first"):
        self.store = store
        self.mode = mode  # breadth_first, depth_first, priority_first, sitemap_first, freshness_first

    def add_url(self, url: str, depth: int = 0, parent_url: str = "", discovery_type: str = "seed", priority: int = 0) -> bool:
        canonical = URLCanonicalizer.canonicalize(url)
        if not canonical:
            return False
        domain = urlparse(canonical).netloc.lower()
        now = datetime.now(timezone.utc).isoformat()

        # Sitemap-discovered URLs get discovery boost if sitemap_first mode
        if discovery_type in ("sitemap", "sitemap_url"):
            priority += 50

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

    def pop_next(self, worker_id: str = "default_worker", lease_seconds: float = 60.0) -> Optional[Dict]:
        now_ts = time.time()
        # Recover expired worker leases
        self.recover_expired_leases()

        if self.mode == "depth_first":
            order_clause = "ORDER BY depth DESC, priority DESC, id ASC"
        elif self.mode == "sitemap_first":
            order_clause = "ORDER BY CASE WHEN discovery_type LIKE 'sitemap%' THEN 0 ELSE 1 END ASC, priority DESC, depth ASC, id ASC"
        else:  # breadth_first / priority_first
            order_clause = "ORDER BY priority DESC, depth ASC, id ASC"

        with self.store.lock, self.store._get_conn() as conn:
            cur = conn.execute(f"""
                SELECT * FROM frontier
                WHERE status = 'pending' AND next_fetch_at <= ?
                {order_clause}
                LIMIT 1
            """, (now_ts,))
            row = cur.fetchone()
            if not row:
                return None

            item = dict(row)
            lease_id = f"lease-{time.time()}-{item['id']}"
            expires_at = now_ts + lease_seconds

            conn.execute("UPDATE frontier SET status = 'in_progress' WHERE id = ?", (item["id"],))
            conn.execute("""
                INSERT OR REPLACE INTO worker_leases (lease_id, worker_id, resource_id, url, domain, lease_time, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (lease_id, worker_id, item["id"], item["url"], item["domain"], now_ts, expires_at))
            conn.commit()

            item["lease_id"] = lease_id
            return item

    def recover_expired_leases(self) -> int:
        now_ts = time.time()
        with self.store.lock, self.store._get_conn() as conn:
            cur = conn.execute("SELECT resource_id, lease_id FROM worker_leases WHERE expires_at < ?", (now_ts,))
            expired = cur.fetchall()
            if not expired:
                return 0

            for row in expired:
                conn.execute("UPDATE frontier SET status = 'pending' WHERE id = ? AND status = 'in_progress'", (row["resource_id"],))
                conn.execute("DELETE FROM worker_leases WHERE lease_id = ?", (row["lease_id"],))
            conn.commit()
            return len(expired)

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
