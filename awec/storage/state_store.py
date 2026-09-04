"""SQLite storage engine for AWEC state, frontier, resources, and checkpoints."""
from __future__ import annotations
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
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
                CREATE TABLE IF NOT EXISTS urls (id INTEGER PRIMARY KEY AUTOINCREMENT, requested_url TEXT UNIQUE, canonical_url TEXT, domain TEXT, depth INTEGER, source TEXT, status INTEGER, content_type TEXT, wire_size INTEGER, decoded_size INTEGER, sha256_wire TEXT, sha256_decoded TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS frontier (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, canonical_url TEXT, domain TEXT, depth INTEGER, priority INTEGER DEFAULT 0, parent_url TEXT, discovery_type TEXT, status TEXT DEFAULT 'pending', retries INTEGER DEFAULT 0, next_fetch_at REAL DEFAULT 0.0, created_at TEXT);
                CREATE TABLE IF NOT EXISTS resources (id TEXT PRIMARY KEY, requested_url TEXT, final_url TEXT, canonical_url TEXT, parent_url TEXT, discovery_type TEXT, status INTEGER, headers_json TEXT, request_headers_json TEXT, response_headers_json TEXT, content_type TEXT, charset TEXT, content_encoding TEXT, wire_size INTEGER, decoded_size INTEGER, sha256_wire TEXT, sha256_decoded TEXT, sha512_wire TEXT, sha512_decoded TEXT, first_seen TEXT, downloaded_at TEXT, duration_ms REAL, retry_count INTEGER, error TEXT, archive_path TEXT, warc_file TEXT, warc_offset INTEGER, warc_length INTEGER, challenge_detected INTEGER, challenge_reason TEXT);
                CREATE TABLE IF NOT EXISTS blobs (sha256_wire TEXT PRIMARY KEY, sha256_decoded TEXT, wire_size INTEGER, decoded_size INTEGER, content_type TEXT, local_path TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS redirects (id INTEGER PRIMARY KEY AUTOINCREMENT, from_url TEXT, to_url TEXT, status INTEGER, crawl_id TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS checkpoints (key TEXT PRIMARY KEY, value_json TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS host_memory (domain TEXT PRIMARY KEY, concurrency INTEGER DEFAULT 4, delay REAL DEFAULT 0.5, timeout REAL DEFAULT 30.0, retries INTEGER DEFAULT 5, ua_profile TEXT DEFAULT 'archive', state TEXT DEFAULT 'HEALTHY', circuit_state TEXT DEFAULT 'CLOSED', consecutive_failures INTEGER DEFAULT 0, last_failure_ts REAL DEFAULT 0.0, avg_latency_ms REAL DEFAULT 0.0, success_rate REAL DEFAULT 100.0, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS link_graph (id INTEGER PRIMARY KEY AUTOINCREMENT, source_url TEXT, target_url TEXT, discovery_type TEXT, crawl_id TEXT, relationship_type TEXT DEFAULT 'link', created_at TEXT);
                CREATE TABLE IF NOT EXISTS worker_leases (lease_id TEXT PRIMARY KEY, worker_id TEXT, resource_id INTEGER, url TEXT, domain TEXT, lease_time REAL, expires_at REAL);
                CREATE TABLE IF NOT EXISTS upload_spool (id TEXT PRIMARY KEY, crawl_id TEXT, local_path TEXT, remote_key TEXT, target_backend TEXT, status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, last_error TEXT, created_at TEXT, updated_at TEXT);
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_search USING fts5(resource_id UNINDEXED, url, title, headings, body_text, description, domain, language, tokenize = 'unicode61');
                CREATE INDEX IF NOT EXISTS idx_frontier_domain_status ON frontier(domain, status);
                CREATE INDEX IF NOT EXISTS idx_urls_canonical ON urls(canonical_url);
                CREATE INDEX IF NOT EXISTS idx_resources_canonical ON resources(canonical_url);
                CREATE INDEX IF NOT EXISTS idx_resources_wire_hash ON resources(sha256_wire);
                CREATE INDEX IF NOT EXISTS idx_link_graph_src ON link_graph(source_url);
                CREATE INDEX IF NOT EXISTS idx_link_graph_target ON link_graph(target_url);
                CREATE INDEX IF NOT EXISTS idx_upload_spool_status ON upload_spool(status);
            """)

    def recover_interrupted_frontier(self) -> int:
        """Make a crashed/closed crawl resumable by returning leased URLs to pending."""
        with self.lock, self._get_conn() as conn:
            cur = conn.execute("UPDATE frontier SET status='pending' WHERE status='in_progress'")
            conn.execute("DELETE FROM worker_leases WHERE expires_at < ?", (__import__('time').time() + 1,))
            conn.commit()
            return cur.rowcount

    def frontier_counts(self) -> Dict[str, int]:
        with self.lock, self._get_conn() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM frontier GROUP BY status").fetchall()
            return {str(r['status']): int(r['n']) for r in rows}

    def save_checkpoint(self, key: str, data: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO checkpoints (key, value_json, updated_at) VALUES (?, ?, ?)", (key, json.dumps(data), now)); conn.commit()

    def get_checkpoint(self, key: str) -> Optional[Dict[str, Any]]:
        with self.lock, self._get_conn() as conn:
            cur = conn.execute("SELECT value_json FROM checkpoints WHERE key = ?", (key,)); row = cur.fetchone()
            return json.loads(row['value_json']) if row else None

    def save_resource(self, rec: ResourceRecord) -> None:
        with self.lock, self._get_conn() as conn:
            conn.execute("""INSERT OR REPLACE INTO resources (id, requested_url, final_url, canonical_url, parent_url, discovery_type, status, headers_json, request_headers_json, response_headers_json, content_type, charset, content_encoding, wire_size, decoded_size, sha256_wire, sha256_decoded, sha512_wire, sha512_decoded, first_seen, downloaded_at, duration_ms, retry_count, error, archive_path, warc_file, warc_offset, warc_length, challenge_detected, challenge_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (rec.id, rec.requested_url, rec.final_url, rec.canonical_url, rec.parent_url, rec.discovery_type, rec.status, json.dumps(rec.headers), json.dumps(rec.request_headers), json.dumps(rec.response_headers), rec.content_type, rec.charset, rec.content_encoding, rec.wire_size, rec.decoded_size, rec.sha256_wire, rec.sha256_decoded, rec.sha512_wire, rec.sha512_decoded, rec.first_seen, rec.downloaded_at, rec.duration_ms, rec.retry_count, rec.error, rec.archive_path, rec.warc_file, rec.warc_offset, rec.warc_length, 1 if rec.challenge_detected else 0, rec.challenge_reason)); conn.commit()

    def get_resources(self) -> List[Dict[str, Any]]:
        with self.lock, self._get_conn() as conn: return [dict(r) for r in conn.execute("SELECT * FROM resources ORDER BY rowid").fetchall()]

    def index_search_doc(self, resource_id: str, url: str, title: str, headings: str, body_text: str, description: str, domain: str, language: str) -> None:
        with self.lock, self._get_conn() as conn:
            conn.execute("INSERT INTO fts_search (resource_id, url, title, headings, body_text, description, domain, language) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (resource_id, url, title, headings, body_text, description, domain, language)); conn.commit()

    def search(self, query: str, domain: str = "", language: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        if not query.strip(): return []
        sql = "SELECT resource_id, url, title, description, domain, language, bm25(fts_search) as score FROM fts_search WHERE fts_search MATCH ?"; params: List[Any] = [query]
        if domain: sql += " AND domain = ?"; params.append(domain.lower())
        if language: sql += " AND language = ?"; params.append(language.lower())
        sql += " ORDER BY score ASC LIMIT ?"; params.append(limit)
        with self.lock, self._get_conn() as conn: return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def save_host_profile(self, profile: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self._get_conn() as conn:
            conn.execute("""INSERT OR REPLACE INTO host_memory (domain, concurrency, delay, timeout, retries, ua_profile, state, circuit_state, consecutive_failures, last_failure_ts, avg_latency_ms, success_rate, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (profile['domain'], profile.get('concurrency',4), profile.get('delay',0.5), profile.get('timeout',30.0), profile.get('retries',5), profile.get('ua_profile','archive'), profile.get('state','HEALTHY'), profile.get('circuit_state','CLOSED'), profile.get('consecutive_failures',0), profile.get('last_failure_ts',0.0), profile.get('avg_latency_ms',0.0), profile.get('success_rate',100.0), now)); conn.commit()

    def get_host_profile(self, domain: str) -> Optional[Dict[str, Any]]:
        with self.lock, self._get_conn() as conn:
            row = conn.execute("SELECT * FROM host_memory WHERE domain = ?", (domain.lower(),)).fetchone(); return dict(row) if row else None

    def add_link_edge(self, source_url: str, target_url: str, discovery_type: str, crawl_id: str, relationship_type: str = 'link') -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self._get_conn() as conn:
            conn.execute("INSERT INTO link_graph (source_url, target_url, discovery_type, crawl_id, relationship_type, created_at) VALUES (?, ?, ?, ?, ?, ?)", (source_url, target_url, discovery_type, crawl_id, relationship_type, now)); conn.commit()

    def save_upload_spool(self, spool_id: str, crawl_id: str, local_path: str, remote_key: str, target_backend: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO upload_spool (id, crawl_id, local_path, remote_key, target_backend, status, attempts, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)", (spool_id,crawl_id,local_path,remote_key,target_backend,now,now)); conn.commit()

    def update_upload_spool_status(self, spool_id: str, status: str, last_error: str = '') -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self._get_conn() as conn:
            conn.execute("UPDATE upload_spool SET status=?, attempts=attempts+1, last_error=?, updated_at=? WHERE id=?", (status,last_error,now,spool_id)); conn.commit()

    def get_pending_uploads(self) -> List[Dict[str, Any]]:
        with self.lock, self._get_conn() as conn: return [dict(r) for r in conn.execute("SELECT * FROM upload_spool WHERE status IN ('pending','failed') AND attempts < 5").fetchall()]
