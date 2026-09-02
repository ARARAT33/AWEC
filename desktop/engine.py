"""AWEC desktop application crawler engine integrated with awec core modules."""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import boto3
from PySide6.QtCore import QObject, Signal

from awec.archive.ia import IAUploader
from awec.archive.warc import ArchivePackageBuilder, WARCGenerator
from awec.core.canonicalizer import CrawlPolicy, ResourceRecord, URLCanonicalizer
from awec.discovery.parsers import ContentExtractor
from awec.http.compression import CompressionDecoder, process_payload
from awec.safety.policy import RobotsManager, SSRFGuard
from awec.safety.waf import WAFDetector
from awec.storage.state_store import StateStore
from desktop.crawler_engine import USER_AGENT_POOL

APP_DIR = Path.home() / "AWEC"


class Engine(QObject):
    log = Signal(str)
    stats = Signal(dict)
    finished = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.is_paused = False
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.store = StateStore(APP_DIR / "awec-index.db")
        self.enqueued = self.fetched = self.files_found = self.uploaded = self.errors = self.active = 0

    def stop(self):
        self.stop_event.set()

    def emit(self):
        self.stats.emit({
            "queued": 0,
            "enqueued": self.enqueued,
            "fetched": self.fetched,
            "pages": self.fetched,
            "files": self.files_found,
            "downloaded": self.uploaded,
            "uploaded": self.uploaded,
            "errors": self.errors,
            "active": self.active,
            "speed": "Active"
        })

    def ext_ok(self, url: str, ctype: str = "") -> bool:
        exts_raw = getattr(self.cfg, "file_types", None) or getattr(self.cfg, "extensions", None) or ["*"]
        if "*" in exts_raw:
            return True
        exts = [x.strip().lower() if x.strip().startswith(".") or x.strip().startswith("mime:") else f".{x.strip().lower()}" for x in exts_raw if x.strip()]
        ext = Path(urlparse(url).path.lower()).suffix
        return ext in exts or any(x.startswith("mime:") and x[5:] in ctype.lower() for x in exts)

    def build_request_headers(self, source_url: str = "") -> dict:
        ua = getattr(self.cfg, "custom_user_agent", "") or None
        if not ua or getattr(self.cfg, "ua_rotation_enabled", True):
            ua = random.choice(USER_AGENT_POOL)

        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hy;q=0.8,ru;q=0.7",
            "Accept-Encoding": CompressionDecoder.get_supported_encodings(),
            "Sec-Ch-Ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none" if not source_url else "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        if source_url and source_url != "seed":
            headers["Referer"] = source_url

        custom_json = getattr(self.cfg, "custom_headers_json", "")
        if custom_json:
            try:
                ch = json.loads(custom_json)
                if isinstance(ch, dict):
                    headers.update(ch)
            except Exception:
                pass
        return headers

    async def ia_put(self, body_bytes: bytes, key: str, ctype: str) -> bool:
        if not (getattr(self.cfg, "ia_access_key", "") and getattr(self.cfg, "ia_secret_key", "") and getattr(self.cfg, "ia_identifier", "")):
            return False

        uploader = IAUploader(
            access_key=self.cfg.ia_access_key,
            secret_key=self.cfg.ia_secret_key,
            identifier=self.cfg.ia_identifier,
            endpoint_url=getattr(self.cfg, "ia_endpoint", "https://s3.us.archive.org")
        )

        tmp_file = APP_DIR / f"tmp_{uuid.uuid4().hex}.bin"
        tmp_file.write_bytes(body_bytes)
        try:
            ok, msg = await asyncio.to_thread(uploader.upload_file_s3, tmp_file, key, ctype)
            if not ok:
                self.log.emit(f"❌ IA upload failed for {key}: {msg}")
            return ok
        finally:
            if tmp_file.exists():
                tmp_file.unlink()

    async def fetch(self, session, item, q, seen, host_next, robots):
        url, depth, source = item
        canonical_url = URLCanonicalizer.canonicalize(url)
        host = urlparse(canonical_url).netloc.lower()

        valid, ssrf_reason = SSRFGuard.validate_url(canonical_url)
        if not valid:
            self.log.emit(f"🛡️ SSRF Blocked {canonical_url}: {ssrf_reason}")
            return

        base_delay = getattr(self.cfg, "per_host_delay", 0.5)
        jitter = getattr(self.cfg, "delay_jitter_sec", 0.25)
        delay = base_delay + random.uniform(0, max(0.0, jitter))

        wait = host_next.get(host, 0) - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        host_next[host] = time.monotonic() + delay

        retries = getattr(self.cfg, "max_retries", 3)
        proxy_url = getattr(self.cfg, "proxy_url", "") or None

        for attempt in range(retries + 1):
            try:
                headers = self.build_request_headers(source)
                async with session.get(canonical_url, allow_redirects=True, max_redirects=8, proxy=proxy_url, headers=headers) as r:
                    ctype = r.headers.get("content-type", "").split(";")[0]
                    wire_bytes = await r.read()
                    final_url = str(r.url)
                    self.fetched += 1

                    payload = process_payload(wire_bytes, r.headers.get("content-encoding", ""))
                    text = payload.decoded_bytes.decode(r.charset or "utf-8", errors="ignore")

                    challenge_detected, challenge_reason = WAFDetector.detect_challenge(r.status, dict(r.headers), text)
                    if challenge_detected:
                        self.log.emit(f"⚠️ [{r.status}] Block/Challenge on {final_url}: {challenge_reason}")
                    else:
                        self.log.emit(f"🌐 [{r.status}] {final_url} ({len(payload.wire_bytes)} wire bytes)")

                    rec = ResourceRecord(
                        id=uuid.uuid4().hex,
                        requested_url=canonical_url,
                        final_url=final_url,
                        canonical_url=URLCanonicalizer.canonicalize(final_url),
                        parent_url=source,
                        status=r.status,
                        content_type=ctype,
                        content_encoding=payload.content_encoding,
                        wire_size=len(payload.wire_bytes),
                        decoded_size=len(payload.decoded_bytes),
                        sha256_wire=payload.sha256_wire,
                        sha256_decoded=payload.sha256_decoded,
                        downloaded_at=datetime.now(timezone.utc).isoformat(),
                        challenge_detected=challenge_detected,
                        challenge_reason=challenge_reason
                    )
                    self.store.save_resource(rec)

                    if "text/html" in ctype.lower():
                        extracted = ContentExtractor.extract_html_links(final_url, text)
                        for u, d_type, _ in extracted:
                            c_u = URLCanonicalizer.canonicalize(u)
                            max_depth = getattr(self.cfg, "max_depth", 8)
                            if depth < max_depth and c_u not in seen:
                                seen.add(c_u)
                                await q.put((c_u, depth + 1, final_url))
                                self.enqueued += 1
                    break
            except Exception as e:
                if attempt >= retries:
                    self.errors += 1
                    self.log.emit(f"❌ {url}: {e}")
                else:
                    await asyncio.sleep(min(60, 2 ** attempt))

    async def run_async(self):
        workers = getattr(self.cfg, "workers", 32)
        q = asyncio.Queue(maxsize=max(1000, workers * 50))
        seen = set()
        host_next = {}
        robots = {}

        for s in self.cfg.seeds:
            u = URLCanonicalizer.canonicalize(s)
            if u and u not in seen:
                seen.add(u)
                await q.put((u, 0, "seed"))
                self.enqueued += 1

        if q.empty():
            self.log.emit("⚠️ No valid seeds found.")
            return

        timeout = getattr(self.cfg, "request_timeout", 30)
        verify_ssl = getattr(self.cfg, "verify_ssl", True)
        conn = aiohttp.TCPConnector(limit=max(16, workers * 2), ssl=verify_ssl)

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), connector=conn) as session:
            async def worker():
                while not self.stop_event.is_set():
                    while getattr(self, "is_paused", False) and not self.stop_event.is_set():
                        await asyncio.sleep(0.2)
                    try:
                        item = await asyncio.wait_for(q.get(), 0.5)
                    except asyncio.TimeoutError:
                        if q.empty() and self.active == 0:
                            return
                        continue

                    self.active += 1
                    try:
                        await self.fetch(session, item, q, seen, host_next, robots)
                    finally:
                        self.active -= 1
                        q.task_done()
                        self.emit()

            tasks = [asyncio.create_task(worker()) for _ in range(workers)]
            while not self.stop_event.is_set():
                if q.empty() and self.active == 0:
                    break
                await asyncio.sleep(0.25)
            await q.join()
            self.stop_event.set()
            await asyncio.gather(*tasks, return_exceptions=True)
        self.log.emit("🏁 Crawl completed")

    def start(self):
        try:
            asyncio.run(self.run_async())
        except Exception as e:
            self.log.emit(f"💥 Fatal: {e}")
        finally:
            self.finished.emit(json.dumps({"fetched": self.fetched, "files": self.files_found, "uploaded": self.uploaded, "errors": self.errors}))
