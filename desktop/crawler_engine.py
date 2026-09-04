"""AWEC Desktop Crawler Adapter - Bridges PySide6 UI and awec core pipeline."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from awec.archive.ia import IAUploader, SpoolPublisher
from awec.archive.warc import ArchivePackageBuilder, WARCGenerator
from awec.core.canonicalizer import CrawlPolicy as CorePolicy, FANTIConfig, ResourceRecord, URLCanonicalizer
from awec.core.frontier import Frontier
from awec.discovery.parsers import ContentExtractor
from awec.http.fetcher import FANTIFetcher, StandardFetcher
from awec.search.indexer import LinkGraphManager, SearchIndexer
from awec.storage.state_store import StateStore

USER_AGENT_POOL = [
    "AWEC/3.0 (+https://github.com/ARARAT33/AWEC; Archival Crawler)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 AWEC/3.0",
]


@dataclass
class CrawlPolicy:
    network_mode: str = "standard"  # standard or fanti
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
    ua_rotation: bool = False
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
        self.crawl_id = f"crawl-{uuid.uuid4().hex[:10]}"
        self.store = StateStore(self.output_dir / "crawls" / self.crawl_id / "state.db")
        self.frontier = Frontier(self.store)
        self.warc_generator = WARCGenerator(self.output_dir / "crawls" / self.crawl_id / "WARC", self.crawl_id)
        self.indexer = SearchIndexer(self.store)
        self.link_graph = LinkGraphManager(self.store)

        core_policy = CorePolicy(
            user_agent="AWEC/3.0 (+https://github.com/ARARAT33/AWEC; Archival Crawler)",
            network_mode=policy.network_mode,
            max_depth=policy.max_depth,
            verify_ssl=policy.verify_ssl,
            proxy_url=policy.proxy_url,
            custom_headers=policy.custom_headers
        )
        fanti_cfg = FANTIConfig(network_mode=policy.network_mode)

        if policy.network_mode == "fanti":
            self.fetcher = FANTIFetcher(fanti_cfg, self.store)
        else:
            self.fetcher = StandardFetcher(core_policy, self.store)

        self.paused = False
        self.stopped = False
        self.stats = {'status': 'AWEC Stopped', 'pages': 0, 'files': 0, 'bytes': 0, 'errors': 0, 'queued': 0}

    def get_headers(self, source_url: str = "") -> dict:
        headers = {
            "User-Agent": "AWEC/3.0 (+https://github.com/ARARAT33/AWEC; Archival Crawler)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hy;q=0.8,ru;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if source_url else "none"
        }
        if source_url:
            headers["Referer"] = source_url
        return headers

    async def run(self) -> None:
        self.stats['status'] = 'AWEC Running'
        for seed in self.seeds:
            self.frontier.add_url(seed, depth=0, parent_url="", discovery_type="seed")

        while not self.stopped:
            if self.paused:
                await asyncio.sleep(0.5)
                continue

            item = self.frontier.pop_next()
            if not item:
                break

            url = item["url"]
            res = await self.fetcher.fetch(url, parent_url=item.get("parent_url", ""), depth=item.get("depth", 0))

            if res.status >= 200 and res.status < 400:
                self.stats['pages'] += 1
                self.stats['bytes'] += len(res.wire_bytes)

                rec = ResourceRecord(
                    id=uuid.uuid4().hex,
                    requested_url=url,
                    final_url=res.final_url,
                    canonical_url=res.canonical_url,
                    parent_url=item.get("parent_url", ""),
                    discovery_type=item.get("discovery_type", "html_link"),
                    status=res.status,
                    request_headers=res.request_headers,
                    response_headers=res.response_headers,
                    content_type=res.content_type,
                    wire_size=len(res.wire_bytes),
                    decoded_size=len(res.decoded_bytes),
                    sha256_wire=res.wire_hash,
                    sha256_decoded=res.decoded_hash,
                    downloaded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    duration_ms=res.duration_ms,
                    network_mode=self.policy.network_mode
                )

                w_offset, w_len = self.warc_generator.write_warc_response(rec, res.wire_bytes)
                rec.warc_file = self.warc_generator.warc_path.name
                rec.warc_offset = w_offset
                rec.warc_length = w_len
                self.store.save_resource(rec)
                self.frontier.mark_completed(item["id"])

                body_text = res.decoded_bytes.decode("utf-8", errors="ignore")
                if "text/html" in res.content_type.lower():
                    self.indexer.index_resource(rec.id, res.final_url, item["domain"], body_text)
                    if item["depth"] < self.policy.max_depth:
                        extracted = ContentExtractor.extract_html_links(res.final_url, body_text)
                        for ext_url, disc_type, _ in extracted:
                            self.link_graph.add_edge(res.final_url, ext_url, disc_type, self.crawl_id)
                            self.frontier.add_url(ext_url, depth=item["depth"] + 1, parent_url=res.final_url, discovery_type=disc_type)

                self.on_event("page_fetched", {"url": res.final_url, "status": res.status, "size": len(res.wire_bytes)})
            else:
                self.stats['errors'] += 1
                self.frontier.mark_failed(item["id"], retry_delay=5.0)

            f_stats = self.frontier.get_stats()
            self.stats['queued'] = f_stats.get("pending", 0)

        self.warc_generator.close()
        await self.fetcher.close()
        self.stats['status'] = 'AWEC Completed'

    def pause(self):
        self.paused = True
        self.stats['status'] = 'AWEC Paused'

    def resume(self):
        self.paused = False
        self.stats['status'] = 'AWEC Running'

    def stop(self):
        self.stopped = True
        self.stats['status'] = 'AWEC Stopped'
