"""AWEC compliance-first & anti-blocking recursive crawler engine.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from bs4 import BeautifulSoup

USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15"
]

@dataclass
class CrawlPolicy:
    follow_links: bool = True
    follow_external_domains: bool = False
    include_subdomains: bool = True
    download_files: bool = True
    respect_robots: bool = True
    max_depth: int = 8
    max_file_size: int = -1
    file_types: list[str] = field(default_factory=lambda: ["*"])
    workers: int = 32
    rate_limit_per_host: float = 0.5
    retry_delays: list[int] = field(default_factory=lambda: [5, 15, 30])
    ua_rotation: bool = True
    delay_jitter: float = 0.25
    auto_headers: bool = True
    verify_ssl: bool = True
    proxy_url: str = ""
    custom_headers: dict = field(default_factory=dict)
    max_local_mb: int = 50
    purge_after_upload: bool = True

class AWECrawler:
    def __init__(self, seeds: list[str], policy: CrawlPolicy, on_event=None, output_dir=None):
        self.seeds = seeds
        self.policy = policy
        self.on_event = on_event or (lambda *_: None)
        self.output_dir = Path(output_dir) if output_dir else Path("fallback")
        self.queue: asyncio.Queue = asyncio.Queue()
        self.seen: set[str] = set()
        self.paused = False
        self.stopped = False
        self.stats = {'status': 'AWEC Stopped', 'pages': 0, 'files': 0, 'bytes': 0, 'errors': 0, 'queued': 0}
        self.host_last = {}

    def get_headers(self) -> dict:
        headers = {}
        if self.policy.ua_rotation:
            headers["User-Agent"] = random.choice(USER_AGENT_POOL)
        else:
            headers["User-Agent"] = "AWEC/3.0 (+https://github.com/ARARAT33/AWEC; Archival Crawler)"

        if self.policy.auto_headers:
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Upgrade-Insecure-Requests": "1"
            })
        if self.policy.custom_headers:
            headers.update(self.policy.custom_headers)
        return headers

    def enforce_local_storage_quota(self):
        if self.policy.max_local_mb < 0 or not self.output_dir.exists():
            return

        max_bytes = self.policy.max_local_mb * 1024 * 1024
        if max_bytes == 0:
            for p in self.output_dir.rglob('*'):
                if p.is_file():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            return

        files = []
        for p in self.output_dir.rglob('*'):
            if p.is_file():
                files.append((p.stat().st_mtime, p.stat().st_size, p))

        files.sort(key=lambda x: x[0])  # oldest first
        current = sum(f[1] for f in files)

        for mtime, size, p in files:
            if current <= max_bytes:
                break
            try:
                p.unlink()
                current -= size
            except Exception:
                pass
