"""SQLite storage engine for AWEC state, frontier, resources, and checkpoints."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from awec.core.canonicalizer import ResourceRecord


class StateStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.lock, self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_url TEXT UNIQUE,
                    canonical_url TEXT,
                    domain TEXT,
                    depth INTEGER,
                    source TEXT,
                    status INTEGER,
                    content_type TEXT,
                    wire_size INTEGER,
                    decoded_size INTEGER,
                    sha256_wire TEXT,
                    sha256_decoded TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS frontier (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    canonical_url TEXT,
                    domain TEXT,
                    depth INTEGER,
                    priority INTEGER DEFAULT 0,
                    parent_url TEXT,
                    discovery_type TEXT,
                    status TEXT DEFAULT 'pending', -- pending, in_progress, completed, failed
                    retries INTEGER DEFAULT 0,
                    next_fetch_at REAL DEFAULT 0.0,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS resources (
                    id TEXT PRIMARY KEY,
                    requested_url TEXT,
                    final_url TEXT,
                    canonical_url TEXT,
                    parent_url TEXT,
                    discovery_type TEXT,
                    status INTEGER,
                    headers_json TEXT,
                    request_headers_json TEXT,
                    response_headers_json TEXT,
                    content_type TEXT,
                    charset TEXT,
                    content_encoding TEXT,
                    wire_size INTEGER,
                    decoded_size INTEGER,
                    sha256_wire TEXT,
                    sha256_decoded TEXT,
                    sha512_wire TEXT,
                    sha512_decoded TEXT,
                    first_seen TEXT,
                    downloaded_at TEXT,
                    duration_ms REAL,
                    retry_count INTEGER,
                    error TEXT,
                    archive_path TEXT,
                    warc_file TEXT,
                    warc_offset INTEGER,
                    warc_length INTEGER,
                    challenge_detected INTEGER,
                    challenge_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS blobs (
                    sha256_wire TEXT PRIMARY KEY,
                    sha256_decoded TEXT,
                    wire_size INTEGER,
                    decoded_size INTEGER,
                    content_type TEXT,
                    local_path TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS redirects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_url TEXT,
                    to_url TEXT,
                    status INTEGER,
                    crawl_id TEXT,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    key TEXT PRIMARY KEY,
                    value_json TEXT,
                    updated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_frontier_domain_status ON frontier(domain, status);
                CREATE INDEX IF NOT EXISTS idx_urls_canonical ON urls(canonical_url);
                CREATE INDEX IF NOT EXISTS idx_resources_canonical ON resources(canonical_url);
                CREATE INDEX IF NOT EXISTS idx_resources_wire_hash ON resources(sha256_wire);
            """)

    def save_checkpoint(self, key: str, data: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        val = json.dumps(data)
        with self.lock, self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO checkpoints (key, value_json, updated_at) VALUES (?, ?, ?)",
                (key, val, now)
            )
            conn.commit()

    def get_checkpoint(self, key: str) -> Optional[Dict[str, Any]]:
        with self.lock, self._get_conn() as conn:
            cur = conn.execute("SELECT value_json FROM checkpoints WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                return json.loads(row["value_json"])
            return None

    def save_resource(self, rec: ResourceRecord) -> None:
        with self.lock, self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO resources (
                    id, requested_url, final_url, canonical_url, parent_url, discovery_type,
                    status, headers_json, request_headers_json, response_headers_json,
                    content_type, charset, content_encoding, wire_size, decoded_size,
                    sha256_wire, sha256_decoded, sha512_wire, sha512_decoded,
                    first_seen, downloaded_at, duration_ms, retry_count, error,
                    archive_path, warc_file, warc_offset, warc_length,
                    challenge_detected, challenge_reason
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                rec.id, rec.requested_url, rec.final_url, rec.canonical_url, rec.parent_url, rec.discovery_type,
                rec.status, json.dumps(rec.headers), json.dumps(rec.request_headers), json.dumps(rec.response_headers),
                rec.content_type, rec.charset, rec.content_encoding, rec.wire_size, rec.decoded_size,
                rec.sha256_wire, rec.sha256_decoded, rec.sha512_wire, rec.sha512_decoded,
                rec.first_seen, rec.downloaded_at, rec.duration_ms, rec.retry_count, rec.error,
                rec.archive_path, rec.warc_file, rec.warc_offset, rec.warc_length,
                1 if rec.challenge_detected else 0, rec.challenge_reason
            ))
            conn.commit()

    def get_resources(self) -> List[Dict[str, Any]]:
        with self.lock, self._get_conn() as conn:
            cur = conn.execute("SELECT * FROM resources")
            return [dict(r) for r in cur.fetchall()]
