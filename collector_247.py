#!/usr/bin/env python3
"""
AWEC Production Crawler – Self‑expanding URL collector, 24/7 ready.
Includes: URL normalization, Bloom filter, batch save, sitemap discovery,
          robots.txt sitemap extraction, RSS/Atom, JS/CSS URL extraction,
          file URL extraction (all text formats).
"""
import asyncio
import aiohttp
import hashlib
import json
import logging
import math
import os
import random
import re
import sqlite3
import sys
import time
import zlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import (parse_qs, urlencode, urldefrag, urljoin, urlparse,
                          urlunparse, quote)

import gzip
from bs4 import BeautifulSoup
from lxml import etree

# ---------------------------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------------------------
@dataclass
class Config:
    db_path: str = "links.db"
    log_file: str = "logs/crawler.log"
    max_workers: int = 2000
    max_queue_size: int = 150_000
    max_depth: int = 100
    request_timeout: int = 8
    max_retries: int = 3
    backoff_base: float = 1.5
    batch_size: int = 2000
    flush_interval: float = 120.0
    bloom_size: int = 500_000_000
    bloom_hashes: int = 7
    commoncrawl_interval: int = 3600
    cdx_interval: int = 1800
    crtsh_interval: int = 600
    github_interval: int = 900
    sitemap_interval: int = 300
    rss_interval: int = 300
    dataset_interval: int = 7200
    wikipedia_interval: int = 7200
    ia_access: str = os.getenv("IA_ACCESS_KEY", "")
    ia_secret: str = os.getenv("IA_SECRET_KEY", "")
    job_hours: float = 5.0              # 5h0m
    dns_cache_ttl: int = 300
    log_level: str = "INFO"
    stats_interval: int = 120

    @property
    def deadline(self) -> float:
        return time.time() + self.job_hours * 3600


# ---------------------------------------------------------------------------
# 2. LOGGER
# ---------------------------------------------------------------------------
def setup_logger(cfg: Config) -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger("awec")
    logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(cfg.log_file)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


# ---------------------------------------------------------------------------
# 3. BLOOM FILTER
# ---------------------------------------------------------------------------
class BloomFilter:
    def __init__(self, size: int, hash_count: int) -> None:
        self.size = size
        self.hash_count = hash_count
        self.bit_array = bytearray((size + 7) // 8)
        self._lock = asyncio.Lock()

    def _hashes(self, item: str) -> List[int]:
        h1 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.sha1(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]

    def add(self, item: str) -> None:
        for h in self._hashes(item):
            self.bit_array[h // 8] |= (1 << (h % 8))

    def contains(self, item: str) -> bool:
        return all(self.bit_array[h // 8] & (1 << (h % 8))
                   for h in self._hashes(item))

    async def add_async(self, item: str) -> None:
        async with self._lock:
            self.add(item)

    async def contains_async(self, item: str) -> bool:
        async with self._lock:
            return self.contains(item)

    def estimate_count(self) -> int:
        bits_set = sum(bin(b).count('1') for b in self.bit_array)
        if bits_set == 0:
            return 0
        return int(-(self.size / self.hash_count) *
                   math.log(1.0 - bits_set / self.size))


# ---------------------------------------------------------------------------
# 4. URL NORMALIZER
# ---------------------------------------------------------------------------
class URLNormalizer:
    TRACKING = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'utm_id', 'fbclid', 'gclid', 'gclsrc', 'dclid', 'msclkid', 'twclid',
        'igshid', 'mc_cid', 'mc_eid', '_ga', '_gl', 'ref', 'referrer',
        'source', 'campaign', 'affiliate', 'session_id', 'trk', 'cid', 'sid', 'pid'
    }

    @staticmethod
    def normalize(url: str) -> Optional[str]:
        if not url or len(url) > 6000:
            return None
        try:
            url, _ = urldefrag(url.strip())
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            if scheme not in ('http', 'https', 'ftp', 'ftps', 'ssh', 'git',
                              'svn', 'ws', 'wss', 'magnet', 'ipfs', 'ipns'):
                if scheme:
                    return None
                url = f"https://{url}"
                parsed = urlparse(url)
                scheme = 'https'
            netloc = parsed.netloc.lower()
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            if ':' in netloc:
                host, port = netloc.rsplit(':', 1)
                if (scheme == 'http' and port == '80') or \
                   (scheme == 'https' and port == '443'):
                    netloc = host
            path = parsed.path or '/'
            path = re.sub(r'/+', '/', path)
            if len(path) > 1 and path.endswith('/'):
                path = path[:-1]
            query = ''
            if parsed.query:
                params = parse_qs(parsed.query, keep_blank_values=False)
                clean = {k: v for k, v in params.items()
                         if k.lower() not in URLNormalizer.TRACKING}
                if clean:
                    query = urlencode(clean, doseq=True)
            normalized = urlunparse((scheme, netloc, path, parsed.params, query, ''))
            if len(normalized) < 10:
                return None
            if normalized.lower().startswith(('javascript:', 'data:', 'mailto:', 'tel:', 'sms:')):
                return None
            return normalized
        except Exception:
            return None

    @staticmethod
    def get_domain(url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    @staticmethod
    def get_path(url: str) -> str:
        try:
            return urlparse(url).path or '/'
        except Exception:
            return '/'


# ---------------------------------------------------------------------------
# 5. DATABASE
# ---------------------------------------------------------------------------
class Database:
    def __init__(self, cfg: Config, logger: logging.Logger) -> None:
        self.cfg = cfg
        self.logger = logger
        self.conn = sqlite3.connect(cfg.db_path, check_same_thread=False)
        self._optimize()
        self._create_tables()
        self.bloom = BloomFilter(cfg.bloom_size, cfg.bloom_hashes)
        self._load_bloom()
        self._buffer: List[Dict[str, Any]] = []
        self._buf_lock = asyncio.Lock()
        self._last_flush = time.time()

    def _optimize(self) -> None:
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-200000")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.conn.execute("PRAGMA busy_timeout=5000")

    def _create_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS urls (
                url TEXT PRIMARY KEY,
                url_hash TEXT,
                domain TEXT,
                path TEXT,
                depth INTEGER DEFAULT 0,
                parent_url TEXT,
                source TEXT DEFAULT 'unknown',
                status TEXT DEFAULT 'pending',
                first_seen TEXT,
                last_seen TEXT,
                content_type TEXT,
                content_hash TEXT,
                error_count INTEGER DEFAULT 0,
                priority REAL DEFAULT 1.0
            );
            CREATE INDEX IF NOT EXISTS idx_status ON urls(status);
            CREATE INDEX IF NOT EXISTS idx_domain ON urls(domain);
            CREATE INDEX IF NOT EXISTS idx_priority ON urls(priority DESC);
            CREATE TABLE IF NOT EXISTS crash_recovery (
                id INTEGER PRIMARY KEY,
                last_url TEXT,
                last_time TEXT
            );
        """)
        self.conn.commit()

    def _load_bloom(self) -> None:
        cur = self.conn.execute("SELECT url FROM urls")
        cnt = 0
        for (url,) in cur:
            self.bloom.add(url)
            cnt += 1
        self.logger.info("Bloom filter loaded with %d URLs", cnt)

    async def insert_batch(self, url_dicts: List[Dict[str, Any]]) -> int:
        async with self._buf_lock:
            self._buffer.extend(url_dicts)
            if len(self._buffer) >= self.cfg.batch_size:
                return await self._flush()
        return 0

    async def _flush(self) -> int:
        if not self._buffer:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        for d in self._buffer:
            url = d['url']
            if self.bloom.contains(url):
                continue
            try:
                self.conn.execute(
                    """INSERT OR IGNORE INTO urls
                       (url, url_hash, domain, path, depth, parent_url, source,
                        status, first_seen, last_seen, priority)
                       VALUES (?,?,?,?,?,?,?,'pending',?,?,?)""",
                    (url,
                     hashlib.sha256(url.encode()).hexdigest()[:16],
                     d.get('domain', ''),
                     d.get('path', ''),
                     d.get('depth', 0),
                     d.get('parent_url', ''),
                     d.get('source', 'unknown'),
                     now, now,
                     d.get('priority', 1.0))
                )
                self.bloom.add(url)
                inserted += 1
            except sqlite3.IntegrityError:
                continue
            except Exception as exc:
                self.logger.debug("Insert error for %s: %s", url[:80], exc)
        self.conn.commit()
        if self._buffer:
            self.conn.execute(
                "INSERT OR REPLACE INTO crash_recovery (id, last_url, last_time) VALUES (1,?,?)",
                (self._buffer[-1]['url'], now))
            self.conn.commit()
        self._buffer.clear()
        self._last_flush = time.time()
        return inserted

    async def periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(self.cfg.flush_interval)
            async with self._buf_lock:
                if self._buffer:
                    await self._flush()

    def get_pending(self, limit: int = 2000) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        rows = self.conn.execute(
            """SELECT url, depth, priority FROM urls
               WHERE status='pending'
               ORDER BY priority DESC, first_seen ASC
               LIMIT ?""", (limit,)).fetchall()
        for (url, _, _) in rows:
            self.conn.execute(
                "UPDATE urls SET status='in_progress', last_seen=? WHERE url=?",
                (now, url))
        self.conn.commit()
        return [{'url': r[0], 'depth': r[1], 'priority': r[2]} for r in rows]

    def mark_visited(self, url: str, success: bool = True,
                     content_type: str = '', content_hash: str = '') -> None:
        now = datetime.now(timezone.utc).isoformat()
        status = 'visited' if success else 'failed'
        self.conn.execute(
            "UPDATE urls SET status=?, last_seen=?, content_type=?, content_hash=? WHERE url=?",
            (status, now, content_type, content_hash, url))
        if not success:
            self.conn.execute(
                "UPDATE urls SET error_count=error_count+1 WHERE url=?", (url,))
        self.conn.commit()

    def total_urls(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0]

    def top_domains(self, limit: int = 20) -> List[Tuple[str, int]]:
        return self.conn.execute(
            "SELECT domain, COUNT(*) cnt FROM urls WHERE domain!='' "
            "GROUP BY domain ORDER BY cnt DESC LIMIT ?", (limit,)).fetchall()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()


# ---------------------------------------------------------------------------
# 6. FETCHER
# ---------------------------------------------------------------------------
class Fetcher:
    def __init__(self, cfg: Config, logger: logging.Logger) -> None:
        self.cfg = cfg
        self.logger = logger
        self.session: Optional[aiohttp.ClientSession] = None
        self.requests = 0
        self.errors = 0
        self.timeouts = 0
        self.bytes_dl = 0

    async def start(self) -> None:
        connector = aiohttp.TCPConnector(
            limit=0, limit_per_host=0,
            ttl_dns_cache=self.cfg.dns_cache_ttl,
            force_close=True)
        timeout = aiohttp.ClientTimeout(total=self.cfg.request_timeout)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'AWEC/8.0',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9'
            })

    async def stop(self) -> None:
        if self.session:
            await self.session.close()

    async def fetch(self, url: str, retry: int = 0) -> Optional[Dict[str, Any]]:
        self.requests += 1
        try:
            async with self.session.get(url, allow_redirects=True,
                                       max_redirects=5, ssl=False) as resp:
                if resp.status == 200:
                    ct = resp.headers.get('Content-Type', '').lower()
                    data = await resp.read()
                    self.bytes_dl += len(data)
                    text = await self._decompress(data, resp.headers.get('Content-Encoding', ''))
                    return {
                        'url': str(resp.url),
                        'content_type': ct,
                        'text': text,
                        'hash': hashlib.sha256(data).hexdigest(),
                        'size': len(data)
                    }
                elif resp.status in (429, 503, 502) and retry < self.cfg.max_retries:
                    await asyncio.sleep(self.cfg.backoff_base ** retry)
                    return await self.fetch(url, retry + 1)
        except asyncio.TimeoutError:
            self.timeouts += 1
            if retry < self.cfg.max_retries:
                await asyncio.sleep(self.cfg.backoff_base ** retry)
                return await self.fetch(url, retry + 1)
        except aiohttp.ClientError as exc:
            self.errors += 1
            self.logger.debug("Client error %s: %s", url[:100], exc)
        except Exception as exc:
            self.errors += 1
            self.logger.debug("Fetch error %s: %s", url[:100], exc)
        return None

    async def _decompress(self, data: bytes, encoding: str) -> str:
        try:
            if encoding == 'gzip' or data[:2] == b'\x1f\x8b':
                return gzip.decompress(data).decode('utf-8', 'ignore')
            elif encoding == 'deflate':
                return zlib.decompress(data).decode('utf-8', 'ignore')
            elif encoding == 'br':
                try:
                    import brotli
                    return brotli.decompress(data).decode('utf-8', 'ignore')
                except ImportError:
                    pass
            return data.decode('utf-8', 'ignore')
        except Exception:
            return data.decode('utf-8', 'ignore')


# ---------------------------------------------------------------------------
# 7. PARSER (HTML, JSON, XML, CSS, JS, text, sitemap, rss)
# ---------------------------------------------------------------------------
class Parser:
    URL_RE = re.compile(r"""
        (?:https?|ftp|ftps|ssh|git|svn|ws|wss|magnet|ipfs|ipns)
        ://[^\s<>"'\{\}\[\]\\^`|]+
        |
        \b[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}
        (?:/[^\s<>"'\{\}\[\]\\^`|]*)?
        |
        \b[a-z2-7]{16,56}\.onion\b
        |
        magnet:\?xt=urn:[^\s<>"'\{\}\[\]\\^`|]+
        |
        \b\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?(?:/[^\s<>"'\{\}\[\]\\^`|]*)?
    """, re.IGNORECASE | re.VERBOSE)

    CSS_URL = re.compile(r'url\(\s*["\']?([^"\'()\s]+)["\']?\s*\)', re.IGNORECASE)

    @staticmethod
    def extract_all(text: str, base: str = '') -> Set[str]:
        if not text:
            return set()
        urls: Set[str] = set()
        for m in Parser.URL_RE.finditer(text):
            u = m.group(0).rstrip('.,;:)>')
            if u:
                urls.add(u)
        for m in Parser.CSS_URL.finditer(text):
            u = m.group(1).strip('\'"')
            if u and not u.startswith('data:'):
                urls.add(u)
        return Parser._resolve(urls, base)

    @staticmethod
    def html(text: str, base: str) -> Set[str]:
        urls: Set[str] = set()
        try:
            soup = BeautifulSoup(text, 'lxml')
            for tag in soup.find_all(['a', 'link', 'script', 'img', 'iframe',
                                      'embed', 'object', 'video', 'audio', 'source']):
                for attr in ('href', 'src', 'data', 'srcset'):
                    val = tag.get(attr)
                    if not val:
                        continue
                    if attr == 'srcset':
                        for part in val.split(','):
                            u = part.strip().split()[0]
                            if u:
                                urls.add(u)
                    else:
                        urls.add(val)
            for tag in soup.find_all('meta', attrs={'http-equiv': 'refresh'}):
                content = tag.get('content', '')
                m = re.search(r'url=([^;]+)', content, re.IGNORECASE)
                if m:
                    urls.add(m.group(1))
            for tag in soup.find_all('form', action=True):
                urls.add(tag['action'])
        except Exception:
            pass
        return Parser._resolve(urls, base)

    @staticmethod
    def json_parse(text: str, base: str) -> Set[str]:
        try:
            data = json.loads(text)
            return Parser.extract_all(json.dumps(data), base)
        except Exception:
            return set()

    @staticmethod
    def xml(text: str, base: str) -> Set[str]:
        urls: Set[str] = set()
        try:
            root = etree.fromstring(text.encode('utf-8', 'ignore'))
            for elem in root.iter():
                if elem.text:
                    urls.update(Parser.URL_RE.findall(elem.text))
                for key, val in elem.attrib.items():
                    if val and any(kw in key.lower() for kw in ('url', 'href', 'src', 'link', 'loc')):
                        urls.add(val)
        except Exception:
            pass
        return Parser._resolve(urls, base)

    @staticmethod
    def sitemap(text: str) -> Set[str]:
        urls: Set[str] = set()
        try:
            root = etree.fromstring(text.encode('utf-8', 'ignore'))
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            for loc in root.findall('.//sm:loc', ns):
                if loc.text:
                    urls.add(loc.text.strip())
            for sm in root.findall('.//sm:sitemap/sm:loc', ns):
                if sm.text:
                    urls.add(sm.text.strip())
        except Exception:
            pass
        return urls

    @staticmethod
    def rss(text: str) -> Set[str]:
        urls: Set[str] = set()
        try:
            root = etree.fromstring(text.encode('utf-8', 'ignore'))
            for link in root.findall('.//link'):
                if link.text:
                    urls.add(link.text.strip())
            for enc in root.findall('.//enclosure'):
                u = enc.get('url', '')
                if u:
                    urls.add(u)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for link in root.findall('.//atom:link', ns):
                href = link.get('href', '')
                if href:
                    urls.add(href)
        except Exception:
            pass
        return urls

    @staticmethod
    def _resolve(urls: Set[str], base: str) -> Set[str]:
        resolved: Set[str] = set()
        for u in urls:
            if not u:
                continue
            if base and not urlparse(u).netloc:
                try:
                    u = urljoin(base, u)
                except Exception:
                    pass
            resolved.add(u)
        return resolved


# ---------------------------------------------------------------------------
# 8. DISCOVERY MODULES (including robots.txt sitemap extraction)
# ---------------------------------------------------------------------------
class CommonCrawlImporter:
    INDEXES = [
        f"https://data.commoncrawl.org/cc-index/collections/CC-MAIN-2024-{w:02d}/indexes/cdx-00000.gz"
        for w in [10, 18, 26, 34, 42, 50]
    ] + [
        "https://data.commoncrawl.org/cc-index/collections/CC-MAIN-2025-05/indexes/cdx-00000.gz",
    ]

    def __init__(self, db: Database, fetcher: Fetcher, cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.cfg = cfg
        self.logger = logger
        self.last_run = 0.0

    async def run(self) -> int:
        if time.time() - self.last_run < self.cfg.commoncrawl_interval:
            return 0
        self.last_run = time.time()
        total = 0
        for idx in self.INDEXES:
            res = await self.fetcher.fetch(idx)
            if res and res['text']:
                urls: Set[str] = set()
                for line in res['text'].split('\n')[:200000]:
                    parts = line.split(' ')
                    if len(parts) >= 3:
                        raw = parts[2] if parts[2].startswith('http') else 'https://' + parts[2]
                        norm = URLNormalizer.normalize(raw)
                        if norm:
                            urls.add(norm)
                data = [{'url': u, 'domain': URLNormalizer.get_domain(u),
                         'path': URLNormalizer.get_path(u), 'depth': 0,
                         'parent_url': idx, 'source': 'commoncrawl', 'priority': 5.0}
                        for u in urls]
                total += await self.db.insert_batch(data)
        if total:
            self.logger.info("CommonCrawl: +%d URLs", total)
        return total


class CDXImporter:
    DOMAINS = ['wikipedia.org', 'github.com', 'stackoverflow.com', 'reddit.com',
               'youtube.com', 'amazon.com', 'bbc.com', 'nytimes.com', 'medium.com']

    def __init__(self, db: Database, fetcher: Fetcher, cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.cfg = cfg
        self.logger = logger
        self.last_run = 0.0

    async def run(self) -> int:
        if time.time() - self.last_run < self.cfg.cdx_interval:
            return 0
        self.last_run = time.time()
        total = 0
        for dom in self.DOMAINS:
            cdx = f"https://web.archive.org/cdx/search/cdx?url={dom}/*&output=text&fl=original&limit=100000"
            res = await self.fetcher.fetch(cdx)
            if res and res['text']:
                urls: Set[str] = set()
                for line in res['text'].split('\n'):
                    if line.startswith('http'):
                        norm = URLNormalizer.normalize(line.strip())
                        if norm:
                            urls.add(norm)
                data = [{'url': u, 'domain': URLNormalizer.get_domain(u),
                         'path': URLNormalizer.get_path(u), 'depth': 0,
                         'parent_url': cdx, 'source': 'cdx', 'priority': 4.0}
                        for u in urls]
                total += await self.db.insert_batch(data)
        if total:
            self.logger.info("CDX: +%d URLs", total)
        return total


class CrtShDiscovery:
    DOMAINS = ['google.com', 'facebook.com', 'apple.com', 'microsoft.com',
               'amazon.com', 'netflix.com', 'twitter.com', 'linkedin.com',
               'github.com', 'cloudflare.com']

    def __init__(self, db: Database, fetcher: Fetcher, cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.cfg = cfg
        self.logger = logger
        self.last_run = 0.0

    async def run(self) -> int:
        if time.time() - self.last_run < self.cfg.crtsh_interval:
            return 0
        self.last_run = time.time()
        total = 0
        for dom in self.DOMAINS:
            url = f"https://crt.sh/?q=%25.{dom}&output=json"
            res = await self.fetcher.fetch(url)
            if res and res['text']:
                try:
                    data = json.loads(res['text'])
                    subs: Set[str] = set()
                    for entry in data:
                        for name in entry.get('name_value', '').split('\n'):
                            name = name.strip()
                            if name and '*' not in name:
                                u = f"https://{name}"
                                norm = URLNormalizer.normalize(u)
                                if norm:
                                    subs.add(norm)
                    batch = [{'url': u, 'domain': URLNormalizer.get_domain(u),
                              'path': '/', 'depth': 0,
                              'parent_url': f'crtsh://{dom}', 'source': 'crtsh', 'priority': 6.0}
                             for u in subs]
                    total += await self.db.insert_batch(batch)
                except json.JSONDecodeError:
                    pass
        if total:
            self.logger.info("crt.sh: +%d subdomains", total)
        return total


class GitHubDiscovery:
    QUERIES = [
        "language:python stars:>1000",
        "language:javascript stars:>1000",
        "topic:web-scraping",
        "topic:crawler"
    ]

    def __init__(self, db: Database, fetcher: Fetcher, cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.cfg = cfg
        self.logger = logger
        self.last_run = 0.0

    async def run(self) -> int:
        if time.time() - self.last_run < self.cfg.github_interval:
            return 0
        self.last_run = time.time()
        total = 0
        for q in self.QUERIES:
            api = f"https://api.github.com/search/repositories?q={quote(q)}&per_page=100"
            res = await self.fetcher.fetch(api)
            if res and res['text']:
                try:
                    data = json.loads(res['text'])
                    for repo in data.get('items', []):
                        repo_url = repo.get('html_url', '')
                        if repo_url:
                            norm = URLNormalizer.normalize(repo_url)
                            if norm:
                                await self.db.insert_batch([{
                                    'url': norm,
                                    'domain': 'github.com',
                                    'path': URLNormalizer.get_path(norm),
                                    'depth': 0,
                                    'parent_url': 'github_discovery',
                                    'source': 'github',
                                    'priority': 2.0
                                }])
                                total += 1
                except json.JSONDecodeError:
                    pass
        if total:
            self.logger.info("GitHub: +%d repos", total)
        return total


class SitemapDiscovery:
    """Finds sitemaps via common paths AND robots.txt Sitemap: directives."""
    PATHS = ['/sitemap.xml', '/sitemap_index.xml', '/sitemap-index.xml']

    def __init__(self, db: Database, fetcher: Fetcher, cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.cfg = cfg
        self.logger = logger
        self.last_run = 0.0
        self.known: Set[str] = set()

    async def run(self) -> int:
        if time.time() - self.last_run < self.cfg.sitemap_interval:
            return 0
        self.last_run = time.time()
        total = 0
        top = [d[0] for d in self.db.top_domains(100)]
        for dom in top:
            if dom in self.known:
                continue
            self.known.add(dom)

            # 1. Try robots.txt to get Sitemap: lines
            sitemap_urls: Set[str] = set()
            robots_url = f"https://{dom}/robots.txt"
            res_robots = await self.fetcher.fetch(robots_url)
            if res_robots and res_robots['text']:
                for line in res_robots['text'].splitlines():
                    if line.lower().startswith('sitemap:'):
                        sitemap = line.split(':', 1)[1].strip()
                        if sitemap:
                            sitemap_urls.add(sitemap)

            # 2. Standard paths
            for path in self.PATHS:
                sitemap_urls.add(f"https://{dom}{path}")

            # Fetch and parse each candidate
            for sitemap_url in sitemap_urls:
                res = await self.fetcher.fetch(sitemap_url)
                if res and res['text'] and '<' in res['text']:
                    urls = Parser.sitemap(res['text'])
                    batch = [{'url': u, 'domain': URLNormalizer.get_domain(u),
                              'path': URLNormalizer.get_path(u), 'depth': 0,
                              'parent_url': sitemap_url, 'source': 'sitemap', 'priority': 7.0}
                             for u in urls if URLNormalizer.normalize(u)]
                    total += await self.db.insert_batch(batch)
        if total:
            self.logger.info("Sitemap: +%d URLs", total)
        return total


class RSSDiscovery:
    PATHS = ['/feed', '/rss', '/atom', '/feed.xml', '/rss.xml', '/atom.xml']

    def __init__(self, db: Database, fetcher: Fetcher, cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.cfg = cfg
        self.logger = logger
        self.last_run = 0.0
        self.known: Set[str] = set()

    async def run(self) -> int:
        if time.time() - self.last_run < self.cfg.rss_interval:
            return 0
        self.last_run = time.time()
        total = 0
        top = [d[0] for d in self.db.top_domains(50)]
        for dom in top:
            if dom in self.known:
                continue
            self.known.add(dom)
            for path in self.PATHS:
                url = f"https://{dom}{path}"
                res = await self.fetcher.fetch(url)
                if res and res['text'] and ('<rss' in res['text'] or '<feed' in res['text']):
                    urls = Parser.rss(res['text'])
                    batch = [{'url': u, 'domain': URLNormalizer.get_domain(u),
                              'path': URLNormalizer.get_path(u), 'depth': 0,
                              'parent_url': url, 'source': 'rss', 'priority': 5.0}
                             for u in urls if URLNormalizer.normalize(u)]
                    total += await self.db.insert_batch(batch)
        if total:
            self.logger.info("RSS: +%d URLs", total)
        return total


class WikipediaDumpImporter:
    LANGS = ['en', 'de', 'fr', 'es', 'ru', 'ja', 'zh']

    def __init__(self, db: Database, fetcher: Fetcher, cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.cfg = cfg
        self.logger = logger
        self.last_run = 0.0

    async def run(self) -> int:
        if time.time() - self.last_run < self.cfg.wikipedia_interval:
            return 0
        self.last_run = time.time()
        total = 0
        for lang in self.LANGS:
            dump = f"https://dumps.wikimedia.org/{lang}wiki/latest/{lang}wiki-latest-all-titles-in-ns0.gz"
            res = await self.fetcher.fetch(dump)
            if res and res['text']:
                urls: Set[str] = set()
                for line in res['text'].split('\n')[:500000]:
                    title = line.strip()
                    if title:
                        encoded = quote(title.replace(' ', '_'))
                        u = f"https://{lang}.wikipedia.org/wiki/{encoded}"
                        norm = URLNormalizer.normalize(u)
                        if norm:
                            urls.add(norm)
                batch = [{'url': u, 'domain': f'{lang}.wikipedia.org',
                          'path': URLNormalizer.get_path(u), 'depth': 0,
                          'parent_url': dump, 'source': 'wikipedia', 'priority': 5.0}
                         for u in urls]
                total += await self.db.insert_batch(batch)
        if total:
            self.logger.info("Wikipedia: +%d URLs", total)
        return total


class DatasetImporter:
    DATASETS = [
        "https://s3.amazonaws.com/alexa-static/top-1m.csv.zip",
        "http://s3-us-west-1.amazonaws.com/umbrella-static/top-1m.csv.zip",
        "https://downloads.majestic.com/majestic_million.csv",
        "https://raw.githubusercontent.com/cisagov/dotgov-data/main/current-federal.csv",
    ]

    def __init__(self, db: Database, fetcher: Fetcher, cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.cfg = cfg
        self.logger = logger
        self.last_run = 0.0

    async def run(self) -> int:
        if time.time() - self.last_run < self.cfg.dataset_interval:
            return 0
        self.last_run = time.time()
        total = 0
        for ds in self.DATASETS:
            res = await self.fetcher.fetch(ds)
            if res and res['text']:
                urls = Parser.extract_all(res['text'])
                batch = [{'url': u, 'domain': URLNormalizer.get_domain(u),
                          'path': URLNormalizer.get_path(u), 'depth': 0,
                          'parent_url': ds, 'source': 'dataset', 'priority': 7.0}
                         for u in urls if URLNormalizer.normalize(u)]
                total += await self.db.insert_batch(batch)
        if total:
            self.logger.info("Datasets: +%d URLs", total)
        return total


# ---------------------------------------------------------------------------
# 9. QUEUE MANAGER
# ---------------------------------------------------------------------------
class QueueManager:
    def __init__(self, maxsize: int) -> None:
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    async def put(self, item: Dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def get(self) -> Dict[str, Any]:
        return await self.queue.get()

    def qsize(self) -> int:
        return self.queue.qsize()

    async def join(self) -> None:
        await self.queue.join()


# ---------------------------------------------------------------------------
# 10. WORKER
# ---------------------------------------------------------------------------
class Worker:
    def __init__(self, wid: int, db: Database, fetcher: Fetcher,
                 queue_mgr: QueueManager, cfg: Config, logger: logging.Logger):
        self.wid = wid
        self.db = db
        self.fetcher = fetcher
        self.queue_mgr = queue_mgr
        self.cfg = cfg
        self.logger = logger
        self.processed = 0
        self.found = 0
        self.running = False

    async def run(self) -> None:
        self.running = True
        while self.running:
            try:
                task = await asyncio.wait_for(self.queue_mgr.get(), timeout=5)
            except asyncio.TimeoutError:
                continue
            try:
                await self._process(task)
            except Exception as exc:
                self.logger.debug("Worker %d error: %s", self.wid, exc)
            finally:
                self.queue_mgr.queue.task_done()

    async def _process(self, task: Dict[str, Any]) -> None:
        url = task['url']
        depth = task.get('depth', 0)
        if depth > self.cfg.max_depth:
            return

        res = await self.fetcher.fetch(url)
        if res:
            self.processed += 1
            ct = res['content_type']
            text = res['text']

            if 'html' in ct:
                found = Parser.html(text, url)
            elif 'json' in ct:
                found = Parser.json_parse(text, url)
            elif 'xml' in ct or 'rss' in ct or 'atom' in ct:
                found = Parser.xml(text, url)
            else:
                found = Parser.extract_all(text, url)   # covers JS, CSS, TXT, CSV, etc.

            new_urls: List[Dict[str, Any]] = []
            for u in found:
                norm = URLNormalizer.normalize(u)
                if norm and not await self.db.bloom.contains_async(norm):
                    new_urls.append({
                        'url': norm,
                        'domain': URLNormalizer.get_domain(norm),
                        'path': URLNormalizer.get_path(norm),
                        'depth': depth + 1,
                        'parent_url': url,
                        'source': 'crawled',
                        'priority': task.get('priority', 1.0) * 0.85
                    })
            if new_urls:
                added = await self.db.insert_batch(new_urls)
                self.found += added
                for nd in new_urls[:50]:
                    await self.queue_mgr.put({
                        'url': nd['url'],
                        'depth': nd['depth'],
                        'priority': nd['priority']
                    })
            self.db.mark_visited(url, success=True, content_type=ct,
                                 content_hash=res.get('hash', ''))
        else:
            self.db.mark_visited(url, success=False)

    def stop(self) -> None:
        self.running = False


# ---------------------------------------------------------------------------
# 11. STATISTICS
# ---------------------------------------------------------------------------
class Stats:
    def __init__(self, db: Database, fetcher: Fetcher, queue_mgr: QueueManager,
                 cfg: Config, logger: logging.Logger):
        self.db = db
        self.fetcher = fetcher
        self.queue_mgr = queue_mgr
        self.cfg = cfg
        self.logger = logger
        self.start_time = time.time()

    async def report_loop(self) -> None:
        while True:
            await asyncio.sleep(self.cfg.stats_interval)
            elapsed = time.time() - self.start_time
            total = self.db.total_urls()
            est_unique = self.db.bloom.estimate_count()
            db_mb = os.path.getsize(self.cfg.db_path) / (1024 * 1024)
            self.logger.info(
                "⏱ %.0f min | Total: %d (~%d unique) | DB: %.1f MB | Queue: %d | "
                "Req: %d | Err: %d | Timeout: %d",
                elapsed / 60, total, est_unique, db_mb,
                self.queue_mgr.qsize(),
                self.fetcher.requests, self.fetcher.errors, self.fetcher.timeouts)
            for domain, cnt in self.db.top_domains(10):
                self.logger.info("  🏆 %s: %d", domain, cnt)


# ---------------------------------------------------------------------------
# 12. CRAWLER (orchestrator)
# ---------------------------------------------------------------------------
class Crawler:
    def __init__(self):
        self.cfg = Config()
        self.logger = setup_logger(self.cfg)
        self.db = Database(self.cfg, self.logger)
        self.fetcher = Fetcher(self.cfg, self.logger)
        self.queue_mgr = QueueManager(self.cfg.max_queue_size)
        self.stats = Stats(self.db, self.fetcher, self.queue_mgr, self.cfg, self.logger)
        self.workers: List[Worker] = []
        self.discoverers = [
            CommonCrawlImporter(self.db, self.fetcher, self.cfg, self.logger),
            CDXImporter(self.db, self.fetcher, self.cfg, self.logger),
            CrtShDiscovery(self.db, self.fetcher, self.cfg, self.logger),
            GitHubDiscovery(self.db, self.fetcher, self.cfg, self.logger),
            SitemapDiscovery(self.db, self.fetcher, self.cfg, self.logger),   # includes robots.txt
            RSSDiscovery(self.db, self.fetcher, self.cfg, self.logger),
            WikipediaDumpImporter(self.db, self.fetcher, self.cfg, self.logger),
            DatasetImporter(self.db, self.fetcher, self.cfg, self.logger),
        ]

    async def _seed(self) -> None:
        seeds = [
            *[f"https://{lang}.wikipedia.org/wiki/Special:Random" for lang in
              ['en','de','fr','es','ru','ja','zh','ar','pt','it']],
            "https://github.com/trending", "https://news.ycombinator.com/",
            "https://www.reddit.com/r/all/hot.json?limit=100",
            "https://stackoverflow.com/questions?tab=votes",
            "https://medium.com/tag/technology",
            "https://www.bbc.com", "https://www.nytimes.com",
            "https://www.amazon.com", "https://www.youtube.com",
            "https://www.google.com", "https://www.bing.com",
            "https://www.yahoo.com", "https://www.duckduckgo.com",
            "https://curlie.org/", "https://archive.org/",
            "https://api.github.com/repositories",
            "https://api.publicapis.org/entries",
            *[f"https://{d}/sitemap.xml" for d in
              ['www.bbc.com','www.cnn.com','www.nytimes.com','www.wikipedia.org']],
        ]
        batch = []
        for s in seeds:
            norm = URLNormalizer.normalize(s)
            if norm and not await self.db.bloom.contains_async(norm):
                batch.append({
                    'url': norm,
                    'domain': URLNormalizer.get_domain(norm),
                    'path': URLNormalizer.get_path(norm),
                    'depth': 0,
                    'parent_url': '',
                    'source': 'seed',
                    'priority': 10.0
                })
        if batch:
            await self.db.insert_batch(batch)
        pending = self.db.get_pending(10000)
        for p in pending:
            await self.queue_mgr.put({'url': p['url'], 'depth': p['depth'], 'priority': p['priority']})

    async def run(self) -> None:
        self.logger.info("🪐 AWEC Planetary Crawler starting")
        await self.fetcher.start()

        asyncio.create_task(self.db.periodic_flush())
        asyncio.create_task(self.stats.report_loop())
        asyncio.create_task(self._discovery_loop())
        asyncio.create_task(self._feeder_loop())

        await self._seed()

        self.workers = [
            Worker(i, self.db, self.fetcher, self.queue_mgr, self.cfg, self.logger)
            for i in range(self.cfg.max_workers)
        ]
        for w in self.workers:
            asyncio.create_task(w.run())

        deadline = self.cfg.deadline
        self.logger.info("Working until %s", datetime.fromtimestamp(deadline).strftime('%H:%M:%S'))
        while time.time() < deadline:
            await asyncio.sleep(30)

        self.logger.info("Shutting down...")
        for w in self.workers:
            w.stop()
        try:
            await asyncio.wait_for(self.queue_mgr.join(), timeout=60)
        except asyncio.TimeoutError:
            pass
        await self.db._flush()
        await self.fetcher.stop()

        if self.cfg.ia_access and self.cfg.ia_secret:
            await self._archive()

        self.db.close()
        self.logger.info("Job finished. Total URLs: %d", self.db.total_urls())

    async def _discovery_loop(self) -> None:
        while True:
            for disc in self.discoverers:
                try:
                    await disc.run()
                except Exception as exc:
                    self.logger.error("Discovery %s error: %s", disc.__class__.__name__, exc)
            await asyncio.sleep(60)

    async def _feeder_loop(self) -> None:
        while True:
            if self.queue_mgr.qsize() < 50000:
                pending = self.db.get_pending(2000)
                for p in pending:
                    await self.queue_mgr.put({'url': p['url'], 'depth': p['depth'], 'priority': p['priority']})
            await asyncio.sleep(0.5)

    async def _archive(self) -> None:
        try:
            import internetarchive as ia
            now = datetime.now(timezone.utc)
            if now.hour != 23 or now.minute < 55:
                return
            urls = [r[0] for r in self.db.conn.execute(
                "SELECT url FROM urls WHERE status='visited'").fetchall()]
            if not urls:
                return
            content = '\n'.join(urls)
            gz = gzip.compress(content.encode())
            item_id = f"awec-{now.strftime('%Y-%m-%d')}-{random.randint(1000,9999)}"
            ia.configure(
                access_key=self.cfg.ia_access,
                secret_key=self.cfg.ia_secret
            ).upload(
                item_id,
                file_objects=[BytesIO(gz)],
                file_names=[f"links_{now.strftime('%Y-%m-%d')}.txt.gz"],
                metadata={
                    "collection": "awec_links_awe_o.s",
                    "title": f"AWEC Dump {now.strftime('%Y-%m-%d')}",
                    "creator": "AWEC-v8",
                    "date": now.strftime('%Y-%m-%d'),
                    "mediatype": "texts"
                }
            )
            self.logger.info("Archived %d URLs to %s", len(urls), item_id)
        except Exception as exc:
            self.logger.error("Archive error: %s", exc)


# ---------------------------------------------------------------------------
# 13. MAIN
# ---------------------------------------------------------------------------
async def main() -> None:
    crawler = Crawler()
    await crawler.run()

if __name__ == "__main__":
    asyncio.run(main())
