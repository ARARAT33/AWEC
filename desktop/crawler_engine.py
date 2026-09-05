"""AWEC crawler engine: broad, resumable site/resource graph mirroring."""
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

USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/133.0.0.0 Chrome/133.0.0.0 Safari/537.36",
]


@dataclass
class CrawlPolicy:
    network_mode: str = "standard"
    follow_links: bool = True
    follow_external_domains: bool = False
    include_subdomains: bool = True
    download_files: bool = True
    respect_robots: bool = True
    max_depth: int = 100000
    max_file_size: int = -1
    file_types: list[str] = field(default_factory=lambda: ["*"])
    workers: int = 48
    rate_limit_per_host: float = 8.0
    retry_delays: list[int] = field(default_factory=lambda: [1, 3, 8, 20])
    ua_rotation: bool = True
    delay_jitter: float = 0.15
    auto_headers: bool = True
    verify_ssl: bool = True
    proxy_url: str = ""
    custom_headers: dict = field(default_factory=dict)
    max_local_mb: int = 0
    purge_after_upload: bool = False
    mirror_all_resources: bool = True
    fanti_user_agent_profile: str = "archive"
    fanti_custom_user_agent: str = ""
    fanti_header_profile: str = "Default Archive"
    fanti_min_delay: float = 0.05
    fanti_max_delay: float = 8.0
    fanti_initial_delay: float = 0.15
    fanti_adaptive_pacing: bool = True
    fanti_min_concurrency: int = 1
    fanti_max_concurrency: int = 32
    fanti_initial_concurrency: int = 8
    fanti_adaptive_concurrency: bool = True
    fanti_max_retries: int = 5
    fanti_backoff_strategy: str = "full_jitter"
    fanti_base_retry_delay: float = 1.0
    fanti_max_retry_delay: float = 60.0
    fanti_circuit_breaker_enabled: bool = True
    fanti_circuit_breaker_threshold: int = 5
    fanti_circuit_breaker_cooldown: float = 30.0
    fanti_max_connections: int = 160
    fanti_max_connections_per_host: int = 32
    fanti_keepalive_timeout: float = 30.0
    fanti_dns_timeout: float = 10.0
    fanti_connect_timeout: float = 10.0
    fanti_read_timeout: float = 30.0
    fanti_total_timeout: float = 60.0
    fanti_max_redirects: int = 10
    fanti_allow_cross_domain_redirects: bool = True
    fanti_cookie_policy: str = "per-job"
    fanti_bandwidth_limit_bytes_per_sec: int = 0
    fanti_enable_browser_rendering: bool = False
    fanti_browser_timeout: float = 30.0
    fanti_diagnostic_mode: bool = False


class AWECrawler:
    """Mirror the reachable resource graph, not just HTML pages."""

    EMBEDDED_RESOURCE_KINDS = {"stylesheet", "icon", "image", "script", "media", "css_resource", "js_literal"}

    def __init__(self, seeds: list[str], policy: CrawlPolicy, on_event=None, output_dir=None):
        self.seeds = seeds
        self.policy = policy
        self.on_event = on_event or (lambda *_: None)
        self.output_dir = Path(output_dir) if output_dir else Path.home() / "AWEC" / "tmpcrawl"
        self.crawl_id = f"crawl-{uuid.uuid4().hex[:10]}"
        crawl_root = self.output_dir / "crawls" / self.crawl_id
        self.store = StateStore(crawl_root / "state.db")
        self.frontier = Frontier(self.store)
        self.warc_generator = WARCGenerator(crawl_root / "WARC", self.crawl_id)
        self.mirror = SiteMirror(crawl_root / "site")
        self.indexer = SearchIndexer(self.store)
        self.link_graph = LinkGraphManager(self.store)
        core_policy = CorePolicy(
            user_agent=policy.fanti_custom_user_agent or "AWEC/12.0 (+https://github.com/ARARAT33/AWEC; archival crawler)",
            network_mode=policy.network_mode,
            robots_mode="standard" if policy.respect_robots else "permissive",
            max_depth=policy.max_depth,
            max_file_size=policy.max_file_size,
            verify_ssl=policy.verify_ssl,
            proxy_url=policy.proxy_url,
            custom_headers=policy.custom_headers,
            download_files=True,
            allowed_mime_types=["*"],
            global_concurrency=max(1, policy.workers),
            concurrency_per_host=min(24, max(4, policy.workers // 2)),
            request_rate_per_sec=max(0.1, policy.rate_limit_per_host),
            max_retries=max(0, policy.fanti_max_retries if policy.network_mode == "fanti" else 8),
            request_timeout=max(1, int(policy.fanti_total_timeout if policy.network_mode == "fanti" else 45)),
            max_redirects=max(0, policy.fanti_max_redirects),
        )
        fanti_cfg = FANTIConfig(
            network_mode="fanti",
            user_agent_profile=policy.fanti_user_agent_profile,
            custom_user_agent=policy.fanti_custom_user_agent or core_policy.user_agent,
            header_profile=policy.fanti_header_profile,
            custom_headers=policy.custom_headers,
            min_delay=max(0.0, policy.fanti_min_delay),
            max_delay=max(policy.fanti_min_delay, policy.fanti_max_delay),
            initial_delay=max(0.0, policy.fanti_initial_delay),
            delay_jitter=max(0.0, policy.delay_jitter),
            adaptive_pacing=policy.fanti_adaptive_pacing,
            min_concurrency=max(1, policy.fanti_min_concurrency),
            max_concurrency=max(policy.fanti_min_concurrency, policy.fanti_max_concurrency),
            initial_concurrency=max(policy.fanti_min_concurrency, min(policy.fanti_initial_concurrency, policy.fanti_max_concurrency)),
            adaptive_concurrency=policy.fanti_adaptive_concurrency,
            max_retries=max(0, policy.fanti_max_retries),
            backoff_strategy=policy.fanti_backoff_strategy,
            base_retry_delay=max(0.0, policy.fanti_base_retry_delay),
            max_retry_delay=max(policy.fanti_base_retry_delay, policy.fanti_max_retry_delay),
            circuit_breaker_enabled=policy.fanti_circuit_breaker_enabled,
            circuit_breaker_threshold=max(1, policy.fanti_circuit_breaker_threshold),
            circuit_breaker_cooldown=max(0.0, policy.fanti_circuit_breaker_cooldown),
            max_connections=max(1, policy.fanti_max_connections),
            max_connections_per_host=max(1, policy.fanti_max_connections_per_host),
            keepalive_timeout=max(0.0, policy.fanti_keepalive_timeout),
            dns_timeout=max(0.1, policy.fanti_dns_timeout),
            connect_timeout=max(0.1, policy.fanti_connect_timeout),
            read_timeout=max(0.1, policy.fanti_read_timeout),
            total_timeout=max(0.1, policy.fanti_total_timeout),
            max_redirects=max(0, policy.fanti_max_redirects),
            allow_cross_domain_redirects=policy.fanti_allow_cross_domain_redirects,
            cookie_policy=policy.fanti_cookie_policy,
            proxy_url=policy.proxy_url,
            verify_tls=policy.verify_ssl,
            bandwidth_limit_bytes_per_sec=max(0, policy.fanti_bandwidth_limit_bytes_per_sec),
            enable_browser_rendering=policy.fanti_enable_browser_rendering,
            browser_timeout=max(0.1, policy.fanti_browser_timeout),
            diagnostic_mode=policy.fanti_diagnostic_mode,
        )
        self.fetcher = FANTIFetcher(fanti_cfg, self.store) if policy.network_mode == "fanti" else StandardFetcher(core_policy, self.store)
        self.paused = False
        self.stopped = False
        self.stats = {"status": "AWEC Stopped", "pages": 0, "files": 0, "bytes": 0, "errors": 0,
                      "queued": 0, "enqueued": 0, "retries": 0, "mirrored": 0, "mirror_bytes": 0,
                      "discovered": 0, "rejected": 0, "active_domain": ""}

    @staticmethod
    def _registrable_host(host: str) -> str:
        host = (host or "").lower().rstrip(".")
        return host[4:] if host.startswith("www.") else host

    def _same_site(self, host: str, seed_host: str) -> bool:
        host = self._registrable_host(host); seed_host = self._registrable_host(seed_host)
        return bool(host and seed_host and (host == seed_host or host.endswith("." + seed_host)))

    def _in_scope(self, url: str, embedded_kind: str = "") -> bool:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        if embedded_kind in self.EMBEDDED_RESOURCE_KINDS:
            return True
        if self.policy.follow_external_domains:
            return True
        for seed in self.seeds:
            seed_host = (urlparse(seed).hostname or "").lower()
            if self.policy.include_subdomains:
                if self._same_site(host, seed_host):
                    return True
            elif self._registrable_host(host) == self._registrable_host(seed_host):
                return True
        return False

    def _should_queue(self, url: str, mime_hint: str = "", discovery_type: str = "") -> bool:
        if not self._in_scope(url, discovery_type): self.stats["rejected"] += 1; return False
        if not self.policy.download_files and discovery_type not in {"html_link", "form", "meta_refresh"}: return False
        return True

    async def _seed_bootstrap(self):
        for seed in self.seeds:
            p = urlparse(seed); origin = f"{p.scheme}://{p.netloc}"
            for candidate, kind in ((origin + "/robots.txt", "robots"), (origin + "/sitemap.xml", "sitemap")):
                if self._in_scope(candidate): self.frontier.add_url(candidate, depth=0, parent_url=seed, discovery_type=kind); self.stats["enqueued"] += 1

    async def run(self) -> None:
        self.stats["status"] = "AWEC Running"
        for seed in self.seeds:
            if self._in_scope(seed): self.frontier.add_url(seed, depth=0, parent_url="", discovery_type="seed"); self.stats["enqueued"] += 1
        await self._seed_bootstrap()
        self.on_event("crawl_started", {"crawl_id": self.crawl_id, "seeds": self.seeds, "workers": self.policy.workers})
        try:
            while not self.stopped:
                if self.paused: await asyncio.sleep(0.15); continue
                batch = []
                for _ in range(max(1, min(self.policy.workers, 64))):
                    item = self.frontier.pop_next()
                    if not item: break
                    batch.append(item)
                if not batch: break
                results = await asyncio.gather(*(self._fetch_one(item) for item in batch), return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception): self.stats["errors"] += 1; self.on_event("crawler_error", {"message": str(result)})
                self.stats["queued"] = self.frontier.get_stats().get("pending", 0)
        finally:
            self.mirror.write_manifest(); self.warc_generator.close(); await self.fetcher.close()
            self.stats["status"] = "AWEC Stopped" if self.stopped else "AWEC Completed"
            self.on_event("crawl_finished", dict(self.stats))

    async def _fetch_one(self, item):
        url = item["url"]; res = await self.fetcher.fetch(url, parent_url=item.get("parent_url", ""), depth=item.get("depth", 0))
        if not (200 <= res.status < 400):
            self.stats["errors"] += 1; self.stats["retries"] += 1; self.frontier.mark_failed(item["id"], retry_delay=3.0); self.on_event("request_failed", {"url": url, "status": res.status}); return
        payload = res.wire_bytes; self.stats["pages" if "html" in res.content_type.lower() else "files"] += 1; self.stats["bytes"] += len(payload)
        local_path = self.mirror.save(res.final_url, payload, res.content_type, res.status, res.response_headers); self.stats["mirrored"] += 1; self.stats["mirror_bytes"] += len(payload)
        rec = ResourceRecord(id=uuid.uuid4().hex, requested_url=url, final_url=res.final_url, canonical_url=res.canonical_url, parent_url=item.get("parent_url", ""), discovery_type=item.get("discovery_type", "html_link"), status=res.status, request_headers=res.request_headers, response_headers=res.response_headers, content_type=res.content_type, wire_size=len(payload), decoded_size=len(res.decoded_bytes), sha256_wire=res.wire_hash, sha256_decoded=res.decoded_hash, downloaded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), duration_ms=res.duration_ms, archive_path=str(local_path), challenge_detected=res.challenge_detected, challenge_reason=res.challenge_reason, network_mode=self.policy.network_mode)
        w_offset, w_len = self.warc_generator.write_warc_response(rec, payload); rec.warc_file = self.warc_generator.warc_path.name; rec.warc_offset = w_offset; rec.warc_length = w_len; self.store.save_resource(rec); self.frontier.mark_completed(item["id"])
        body = res.decoded_bytes.decode("utf-8", errors="ignore"); discovered = []; ct = res.content_type.lower()
        if "html" in ct:
            self.indexer.index_resource(rec.id, res.final_url, item["domain"], body)
            if self.policy.follow_links and (self.policy.max_depth <= 0 or item["depth"] < self.policy.max_depth): discovered = ContentExtractor.extract_html_links(res.final_url, body)
        elif "css" in ct: discovered = ContentExtractor.extract_css_links(res.final_url, body)
        elif "javascript" in ct or "ecmascript" in ct: discovered = ContentExtractor.extract_js_links(res.final_url, body)
        elif "xml" in ct or urlparse(res.final_url).path.lower().endswith((".xml", ".xml.gz")): discovered = [(u, "sitemap_url", "text/html") for u in ContentExtractor.parse_sitemap(payload, res.final_url.lower().endswith(".gz"))]
        if "robots" in urlparse(res.final_url).path.lower():
            for line in body.splitlines():
                if line.strip().lower().startswith("sitemap:"): discovered.append((line.split(":", 1)[1].strip(), "sitemap", "application/xml"))
        self.stats["discovered"] += len(discovered)
        for ext_url, disc_type, mime_hint in discovered:
            if self._should_queue(ext_url, mime_hint, disc_type):
                self.link_graph.add_edge(res.final_url, ext_url, disc_type, self.crawl_id)
                next_depth = item["depth"] + (1 if "html" in ct and disc_type not in self.EMBEDDED_RESOURCE_KINDS else 0)
                self.frontier.add_url(ext_url, depth=next_depth, parent_url=res.final_url, discovery_type=disc_type); self.stats["enqueued"] += 1
        self.on_event("discovery", {"url": res.final_url, "found": len(discovered), "queued": self.stats["enqueued"], "rejected": self.stats.get("rejected", 0)})
        self.on_event("page_fetched", {"url": res.final_url, "status": res.status, "size": len(payload), "local_path": str(local_path), "content_type": res.content_type}); self.stats["active_domain"] = urlparse(res.final_url).hostname or ""
