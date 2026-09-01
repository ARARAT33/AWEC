"""AWEC compliance-first & anti-blocking recursive crawler engine.
"""
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
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
import boto3
from PySide6.QtCore import QObject, Signal

APP_DIR = Path.home() / "AWEC"
HREF_RE = re.compile(r"(?:href|src)\s*=\s*['\"]([^'\"]+)['\"]", re.I)
URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.I)

USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0"
]

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
        self.db = sqlite3.connect(APP_DIR / "awec-index.db", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS urls(id INTEGER PRIMARY KEY,url TEXT UNIQUE,domain TEXT,depth INTEGER,source TEXT,status INTEGER,content_type TEXT,size INTEGER,created TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS files(global_id TEXT PRIMARY KEY,domain TEXT,site_name TEXT,url TEXT,filename TEXT,size INTEGER,content_type TEXT,ia_key TEXT,created TEXT)"
        )
        self.db.commit()
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

    def save_url(self, u, d, s, status, ctype, size):
        with self.lock:
            self.db.execute(
                "INSERT OR IGNORE INTO urls(url,domain,depth,source,status,content_type,size,created) VALUES(?,?,?,?,?,?,?,?)",
                (u, urlparse(u).netloc, d, s, status, ctype, size, datetime.now(timezone.utc).isoformat())
            )
            self.db.commit()

    def save_file(self, gid, domain, site, url, fn, size, ctype, key):
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?)",
                (gid, domain, site, url, fn, size, ctype, key, datetime.now(timezone.utc).isoformat())
            )
            self.db.commit()

    def ext_ok(self, url, ctype=""):
        exts_raw = getattr(self.cfg, "file_types", None) or getattr(self.cfg, "extensions", None) or ["*"]
        if "*" in exts_raw:
            return True
        exts = []
        for x in exts_raw:
            x = x.strip().lower()
            if x:
                exts.append(x if x.startswith(".") or x.startswith("mime:") else f".{x}")
        ext = Path(urlparse(url).path.lower()).suffix
        return ext in exts or any(x.startswith("mime:") and x[5:] in ctype.lower() for x in exts)

    def site_name(self, url):
        return re.sub(r"[^a-zA-Z0-9._-]+", "_", urlparse(url).netloc.lower().split(":")[0])[:100] or "site"

    def file_name(self, url, ctype):
        n = re.sub(r"[^\w.()\-]+", "_", Path(urlparse(url).path).name or "index")[:180]
        if "." not in n:
            n += {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "video/mp4": ".mp4", "application/pdf": ".pdf", "application/json": ".json"}.get(ctype.split(";")[0], "")
        return n

    async def ia_put(self, data, key, ctype):
        if not (getattr(self.cfg, "ia_access_key", "") and getattr(self.cfg, "ia_secret_key", "") and getattr(self.cfg, "ia_identifier", "")):
            return False

        body_bytes = bytes(data)
        file_size = len(body_bytes)

        def put():
            s3 = boto3.client(
                "s3",
                endpoint_url=getattr(self.cfg, "ia_endpoint", "https://s3.us.archive.org"),
                aws_access_key_id=self.cfg.ia_access_key,
                aws_secret_access_key=self.cfg.ia_secret_key,
                region_name="us-east-1"
            )
            # boto3 automatically sets Content-Length header for bytes/bytearrays
            s3.put_object(
                Bucket=self.cfg.ia_identifier,
                Key=key,
                Body=body_bytes,
                ContentType=ctype or "application/octet-stream"
            )

        retries = getattr(self.cfg, "max_retries", 3)
        for attempt in range(retries + 1):
            try:
                await asyncio.to_thread(put)
                return True
            except Exception as e:
                if attempt >= retries:
                    self.log.emit(f"❌ IA upload failed: {key}: {e}")
                    return False
                await asyncio.sleep(min(60, 2 ** attempt))
        return False

    async def process_file(self, url, response, body):
        ctype = response.headers.get("content-type", "").split(";")[0].lower()
        length = int(response.headers.get("content-length", "-1") or -1)
        max_fsize = getattr(self.cfg, "max_file_size", -1)
        if not self.ext_ok(url, ctype) or (max_fsize >= 0 and length > max_fsize):
            return
        if max_fsize >= 0 and len(body) > max_fsize:
            return
        self.files_found += 1
        gid = uuid.uuid4().hex
        site = self.site_name(url)
        fn = self.file_name(url, ctype)
        key = f"files/{site}/{gid}_{fn}"
        ok = await self.ia_put(body, key, ctype)

        max_mb = getattr(self.cfg, "max_local_storage_mb", 50)
        purge_after = getattr(self.cfg, "purge_local_files_after_upload", True)

        if ok:
            self.uploaded += 1
            if not purge_after and max_mb != 0:
                fb_dir = getattr(self.cfg, "fallback_dir", "fallback")
                folder = Path(fb_dir) / site
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{gid}_{fn}").write_bytes(body)
        else:
            if max_mb != 0:
                fb_dir = getattr(self.cfg, "fallback_dir", "fallback")
                folder = Path(fb_dir) / site
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"{gid}_{fn}").write_bytes(body)
                self.log.emit(f"💾 Fallback: {folder/(gid+'_'+fn)}")
            else:
                self.log.emit(f"⚠️ IA Upload failed and max_local_storage_mb=0: dropped body for {url}")

        self.save_file(gid, urlparse(url).netloc, site, url, fn, len(body), ctype, key if ok else "")

    def normalize(self, base, raw):
        raw = raw.strip()
        if not raw or raw.startswith(("#", "javascript:", "mailto:", "tel:", "data:", "about:")):
            return None

        # Determine correct base URL format
        if not base.startswith(("http://", "https://")):
            base = "https://" + base

        absolute_url = urljoin(base, raw)
        defragged = urldefrag(absolute_url)[0]
        parsed = urlparse(defragged)

        # Enforce valid HTTP/HTTPS scheme and non-empty valid netloc (e.g. rejecting wp-content:443 or host-less paths)
        if parsed.scheme in ("http", "https") and parsed.netloc and "." in parsed.netloc:
            return defragged[:4000]
        return None

    async def fetch(self, session, item, q, seen, host_next, robots):
        url, depth, source = item
        host = urlparse(url).netloc.lower()
        base_delay = getattr(self.cfg, "per_host_delay", 0.5)
        jitter = getattr(self.cfg, "delay_jitter_sec", 0.25)
        delay = base_delay + random.uniform(0, max(0.0, jitter))

        wait = host_next.get(host, 0) - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        host_next[host] = time.monotonic() + delay

        if getattr(self.cfg, "respect_robots", True):
            if host not in robots:
                rp = RobotFileParser()
                rp.set_url(f"{urlparse(url).scheme}://{host}/robots.txt")
                try:
                    async with session.get(rp.url, timeout=10) as rr:
                        rp.parse((await rr.text(errors="ignore")).splitlines()) if rr.status == 200 else rp.parse([])
                except Exception:
                    rp = None
                robots[host] = rp
            if robots[host] is not None and not robots[host].can_fetch("AWEC/3.0", url):
                self.log.emit(f"🚫 Blocked by robots.txt: {url}")
                return

        retries = getattr(self.cfg, "max_retries", 3)
        proxy_url = getattr(self.cfg, "proxy_url", "") or None

        for attempt in range(retries + 1):
            try:
                async with session.get(url, allow_redirects=True, max_redirects=8, proxy=proxy_url) as r:
                    ctype = r.headers.get("content-type", "")
                    body = await r.read()
                    final = str(r.url)
                    self.fetched += 1

                    if r.status in (403, 503, 530):
                        self.log.emit(f"⚠️ [{r.status}] HTTP Block/CF Challenge on {final}")
                    else:
                        self.log.emit(f"🌐 [{r.status}] {final} ({len(body)} bytes)")

                    self.save_url(final, depth, source, r.status, ctype, len(body))

                    if "text/html" in ctype.lower():
                        text = body.decode(r.charset or "utf-8", errors="ignore")
                        links = []
                        for raw in HREF_RE.findall(text) + URL_RE.findall(text):
                            u = self.normalize(final, raw)
                            if u:
                                links.append(u)
                        for u in dict.fromkeys(links):
                            max_depth = getattr(self.cfg, "max_depth", 8)
                            max_urls = getattr(self.cfg, "max_urls", 0)
                            same_domain = getattr(self.cfg, "same_domain_only", False)
                            if depth < max_depth and u not in seen and (not max_urls or len(seen) < max_urls):
                                seed_netlocs = {urlparse(x if x.startswith(('http://','https://')) else 'https://'+x).netloc.lower() for x in self.cfg.seeds}
                                if same_domain and urlparse(u).netloc.lower() not in seed_netlocs:
                                    continue
                                seen.add(u)
                                await q.put((u, depth + 1, final))
                                self.enqueued += 1
                        if getattr(self.cfg, "download_discovered_files", True):
                            for u in dict.fromkeys(links):
                                if self.ext_ok(u):
                                    await self.fetch_file(session, u)
                    elif getattr(self.cfg, "download_discovered_files", True):
                        await self.process_file(final, r, body)
                    break
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt >= retries:
                    self.errors += 1
                    self.log.emit(f"❌ {url}: {e}")
                else:
                    await asyncio.sleep(min(60, 2 ** attempt))

    async def fetch_file(self, session, url):
        retries = getattr(self.cfg, "max_retries", 3)
        proxy_url = getattr(self.cfg, "proxy_url", "") or None
        for attempt in range(retries + 1):
            try:
                async with session.get(url, allow_redirects=True, max_redirects=8, proxy=proxy_url) as r:
                    if r.status < 400:
                        await self.process_file(str(r.url), r, await r.read())
                    return
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt >= retries:
                    self.errors += 1
                    self.log.emit(f"⚠️ file {url}: {e}")
                else:
                    await asyncio.sleep(min(60, 2 ** attempt))

    async def run_async(self):
        workers = getattr(self.cfg, "workers", 32)
        q = asyncio.Queue(maxsize=max(1000, workers * 50))
        seen = set()
        host_next = {}
        robots = {}

        self.log.emit(f"🌱 Seeds provided: {self.cfg.seeds}")
        for s in self.cfg.seeds:
            u = self.normalize(s, s)
            if u and u not in seen:
                seen.add(u)
                await q.put((u, 0, "seed"))
                self.enqueued += 1
                self.log.emit(f"➕ Enqueued seed: {u}")

        if q.empty():
            self.log.emit("⚠️ No valid seeds found to enqueue.")
            return

        ua_rotation = getattr(self.cfg, "ua_rotation_enabled", True)
        base_ua = getattr(self.cfg, "custom_user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
        headers = {
            "User-Agent": random.choice(USER_AGENT_POOL) if ua_rotation else base_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not=A?Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }

        custom_headers_str = getattr(self.cfg, "custom_headers_json", "")
        if custom_headers_str:
            try:
                ch = json.loads(custom_headers_str)
                if isinstance(ch, dict):
                    headers.update({str(k): str(v) for k, v in ch.items()})
            except Exception:
                pass

        timeout = getattr(self.cfg, "request_timeout", 30)
        verify_ssl = getattr(self.cfg, "verify_ssl", True)
        conn = aiohttp.TCPConnector(limit=max(16, workers * 2), ssl=verify_ssl)
        cookie_jar = aiohttp.CookieJar() if getattr(self.cfg, "cookie_jar_enabled", True) else None

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), headers=headers, connector=conn, cookie_jar=cookie_jar) as session:
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
            with self.lock:
                self.db.close()
            self.finished.emit(json.dumps({"fetched": self.fetched, "files": self.files_found, "uploaded": self.uploaded, "errors": self.errors}))
