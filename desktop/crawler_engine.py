"""AWEC desktop crawler adapter with complete local resource mirroring."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from awec.archive.warc import WARCGenerator
from awec.core.canonicalizer import CrawlPolicy as CorePolicy, FANTIConfig, ResourceRecord
from awec.core.frontier import Frontier
from awec.discovery.parsers import ContentExtractor
from awec.http.fetcher import FANTIFetcher, StandardFetcher
from awec.resources.site_mirror import SiteMirror
from awec.search.indexer import LinkGraphManager, SearchIndexer
from awec.storage.state_store import StateStore


@dataclass
class CrawlPolicy:
    network_mode: str = "standard"
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
    purge_after_upload: bool = False
    mirror_all_resources: bool = True


class AWECrawler:
    """Crawl pages and persist every successful response as a local mirror + WARC."""

    def __init__(self, seeds: list[str], policy: CrawlPolicy, on_event=None, output_dir=None):
        self.seeds = seeds
        self.policy = policy
        self.on_event = on_event or (lambda *_: None)
        self.output_dir = Path(output_dir) if output_dir else Path("fallback")
        self.crawl_id = f"crawl-{uuid.uuid4().hex[:10]}"
        crawl_root = self.output_dir / "crawls" / self.crawl_id
        self.store = StateStore(crawl_root / "state.db")
        self.frontier = Frontier(self.store)
        self.warc_generator = WARCGenerator(crawl_root / "WARC", self.crawl_id)
        self.mirror = SiteMirror(crawl_root / "site")
        self.indexer = SearchIndexer(self.store)
        self.link_graph = LinkGraphManager(self.store)

        core_policy = CorePolicy(
            user_agent="AWEC/11.0 (+https://github.com/ARARAT33/AWEC; archival crawler)",
            network_mode=policy.network_mode,
            robots_mode="standard" if policy.respect_robots else "permissive",
            max_depth=policy.max_depth,
            max_file_size=policy.max_file_size,
            verify_ssl=policy.verify_ssl,
            proxy_url=policy.proxy_url,
            custom_headers=policy.custom_headers,
            download_files=policy.download_files,
            allowed_mime_types=["*"] if policy.mirror_all_resources else policy.file_types,
            global_concurrency=policy.workers,
        )
        fanti_cfg = FANTIConfig(
            network_mode="fanti",
            delay_jitter=policy.delay_jitter,
            verify_tls=policy.verify_ssl,
            proxy_url=policy.proxy_url,
            custom_headers=policy.custom_headers,
            max_connections=max(32, policy.workers * 2),
        )
        self.fetcher = FANTIFetcher(fanti_cfg, self.store) if policy.network_mode == "fanti" else StandardFetcher(core_policy, self.store)
        self.paused = False
        self.stopped = False
        self.stats = {"status": "AWEC Stopped", "pages": 0, "files": 0, "bytes": 0, "errors": 0, "queued": 0, "enqueued": 0, "retries": 0, "mirrored": 0, "mirror_bytes": 0}

    def _in_scope(self, url: str) -> bool:
        if self.policy.follow_external_domains:
            return True
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        for seed in self.seeds:
            seed_host = (urlparse(seed).hostname or "").lower()
            if host == seed_host or (self.policy.include_subdomains and seed_host and host.endswith("." + seed_host)):
                return True
        return False

    def _should_queue(self, url: str, mime_hint: str = "") -> bool:
        if not self._in_scope(url):
            return False
        if not self.policy.download_files and mime_hint and not mime_hint.startswith("text/html"):
            return False
        return True

    async def run(self) -> None:
        self.stats["status"] = "AWEC Running"
        for seed in self.seeds:
            if self._in_scope(seed):
                self.frontier.add_url(seed, depth=0, parent_url="", discovery_type="seed")
                self.stats["enqueued"] += 1
        try:
            while not self.stopped:
                if self.paused:
                    await asyncio.sleep(0.25)
                    continue
                item = self.frontier.pop_next()
                if not item:
                    break
                url = item["url"]
                res = await self.fetcher.fetch(url, parent_url=item.get("parent_url", ""), depth=item.get("depth", 0))
                if 200 <= res.status < 400:
                    payload = res.wire_bytes
                    if "html" in res.content_type.lower():
                        self.stats["pages"] += 1
                    else:
                        self.stats["files"] += 1
                    self.stats["bytes"] += len(payload)
                    local_path = self.mirror.save(res.final_url, payload, res.content_type, res.status, res.response_headers) if self.policy.mirror_all_resources else None
                    if local_path:
                        self.stats["mirrored"] += 1
                        self.stats["mirror_bytes"] += len(payload)
                    rec = ResourceRecord(
                        id=uuid.uuid4().hex, requested_url=url, final_url=res.final_url,
                        canonical_url=res.canonical_url, parent_url=item.get("parent_url", ""),
                        discovery_type=item.get("discovery_type", "html_link"), status=res.status,
                        request_headers=res.request_headers, response_headers=res.response_headers,
                        content_type=res.content_type, wire_size=len(res.wire_bytes), decoded_size=len(res.decoded_bytes),
                        sha256_wire=res.wire_hash, sha256_decoded=res.decoded_hash,
                        downloaded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), duration_ms=res.duration_ms,
                        archive_path=str(local_path) if local_path else "", challenge_detected=res.challenge_detected,
                        challenge_reason=res.challenge_reason, network_mode=self.policy.network_mode,
                    )
                    w_offset, w_len = self.warc_generator.write_warc_response(rec, res.wire_bytes)
                    rec.warc_file = self.warc_generator.warc_path.name
                    rec.warc_offset, rec.warc_length = w_offset, w_len
                    self.store.save_resource(rec)
                    self.frontier.mark_completed(item["id"])
                    body = res.decoded_bytes.decode("utf-8", errors="ignore")
                    discovered = []
                    ct = res.content_type.lower()
                    if "html" in ct:
                        self.indexer.index_resource(rec.id, res.final_url, item["domain"], body)
                        if self.policy.follow_links and item["depth"] < self.policy.max_depth:
                            discovered = ContentExtractor.extract_html_links(res.final_url, body)
                    elif "css" in ct:
                        discovered = ContentExtractor.extract_css_links(res.final_url, body)
                    elif "javascript" in ct or "ecmascript" in ct:
                        discovered = ContentExtractor.extract_js_links(res.final_url, body)
                    for ext_url, disc_type, mime_hint in discovered:
                        if self._should_queue(ext_url, mime_hint):
                            self.link_graph.add_edge(res.final_url, ext_url, disc_type, self.crawl_id)
                            self.frontier.add_url(ext_url, depth=item["depth"] + (1 if "html" in ct else 0), parent_url=res.final_url, discovery_type=disc_type)
                            self.stats["enqueued"] += 1
                    self.on_event("page_fetched", {"url": res.final_url, "status": res.status, "size": len(payload), "local_path": str(local_path) if local_path else ""})
                else:
                    self.stats["errors"] += 1
                    self.stats["retries"] += 1
                    self.frontier.mark_failed(item["id"], retry_delay=5.0)
                self.stats["queued"] = self.frontier.get_stats().get("pending", 0)
        finally:
            self.mirror.write_manifest()
            self.warc_generator.close()
            await self.fetcher.close()
            self.stats["status"] = "AWEC Stopped" if self.stopped else "AWEC Completed"

    def pause(self):
        self.paused = True
        self.stats["status"] = "AWEC Paused"

    def resume(self):
        self.paused = False
        self.stats["status"] = "AWEC Running"

    def stop(self):
        self.stopped = True
        self.stats["status"] = "AWEC Stopped"
