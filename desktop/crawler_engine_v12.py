"""AWEC v12 resumable crawler with broad resource discovery and live IA publishing."""
from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from awec.archive.ia import IAUploader
from awec.core.frontier import Frontier
from awec.core.canonicalizer import ResourceRecord
from awec.discovery.parsers import ContentExtractor
from awec.resources.site_mirror import SiteMirror
from awec.search.indexer import LinkGraphManager, SearchIndexer
from awec.storage.state_store import StateStore
from desktop.crawler_engine import AWECrawler as BaseCrawler


class ResumableAWECrawler(BaseCrawler):
    """Base crawler plus durable resume, storage guard and non-blocking live IA publication."""

    def __init__(self, seeds, policy, on_event=None, output_dir=None, resume_dir=None,
                 ia_uploader=None, archive_verify=True, purge_after_upload=False,
                 min_free_space_mb=2048, max_local_mb=0, keep_local_mirror=True):
        super().__init__(seeds, policy, on_event=on_event, output_dir=output_dir)
        self.ia_uploader = ia_uploader
        self.archive_verify = archive_verify
        self.purge_after_upload = purge_after_upload
        self.min_free_space_mb = max(256, int(min_free_space_mb or 2048))
        self.keep_local_mirror = bool(keep_local_mirror)
        self.max_local_mb = max(0, int(max_local_mb or 0))
        self.uploaded = 0
        self.upload_failed = 0
        self._upload_pool = ThreadPoolExecutor(max_workers=8) if ia_uploader else None
        if resume_dir:
            root = Path(resume_dir)
            self.crawl_id = root.name
            self.output_dir = root.parent.parent
            self.store = StateStore(root / "state.db")
            self.frontier = Frontier(self.store)
            self.mirror = SiteMirror(root / "site")
            self.warc_generator.close()
            from awec.archive.warc import WARCGenerator
            self.warc_generator = WARCGenerator(root / "WARC", self.crawl_id)
            self.indexer = SearchIndexer(self.store)
            self.link_graph = LinkGraphManager(self.store)
            self.store.recover_interrupted_frontier()
            self.on_event("crawl_resumed", {"crawl_id": self.crawl_id, "path": str(root)})

    def _disk_ok(self, extra_bytes=0):
        try:
            usage = shutil.disk_usage(self.mirror.root)
            if usage.free - extra_bytes <= self.min_free_space_mb * 1024 * 1024:
                return False
            if self.max_local_mb:
                current = sum(p.stat().st_size for p in self.mirror.root.rglob("*") if p.is_file())
                if current + extra_bytes > self.max_local_mb * 1024 * 1024:
                    return False
            return True
        except OSError:
            return True

    def _remote_key(self, url):
        import hashlib
        p = urlparse(url)
        host = (p.hostname or "unknown").lower()
        path = p.path.lstrip("/") or "index.html"
        key = f"site/{host}/{path}"
        if p.query:
            key += "__q-" + hashlib.sha256(p.query.encode()).hexdigest()[:16]
        return key.replace("//", "/")

    def _publish(self, local_path, url, content_type, size):
        if not self.ia_uploader or not local_path or not local_path.exists():
            return
        remote = self._remote_key(url)
        try:
            ok, msg = self.ia_uploader.upload_file_s3(local_path, remote, content_type=content_type)
            if ok and self.archive_verify:
                ok = self.ia_uploader.verify_remote_object(remote, size)
                msg = msg + " • VERIFIED" if ok else msg + " • VERIFY_FAILED"
            if ok:
                self.uploaded += 1
                self.on_event("archive_uploaded", {"url": url, "remote_key": remote, "size": size})
                if self.purge_after_upload and not self.keep_local_mirror:
                    try: local_path.unlink(missing_ok=True)
                    except OSError: pass
            else:
                self.upload_failed += 1
                self.on_event("archive_upload_failed", {"url": url, "message": msg})
        except Exception as exc:
            self.upload_failed += 1
            self.on_event("archive_upload_failed", {"url": url, "message": str(exc)})

    async def run(self):
        self.stats["status"] = "AWEC Running"
        for seed in self.seeds:
            if self._in_scope(seed):
                self.frontier.add_url(seed, depth=0, parent_url="", discovery_type="seed")
                self.stats["enqueued"] += 1
        # v12 engine historically seeds bootstrap URLs from desktop/engine.py.
        # Keep the crawler itself self-contained for direct callers too.
        await self._seed_bootstrap()
        self.on_event("crawl_started", {"crawl_id": self.crawl_id, "seeds": self.seeds, "workers": self.policy.workers})
        try:
            while not self.stopped:
                if self.paused:
                    await asyncio.sleep(0.15)
                    continue
                if not self._disk_ok():
                    self.stats["status"] = "AWEC Storage Guard"
                    self.on_event("storage_guard", {"message": "Temporary storage limit/free-space reserve reached."})
                    break
                batch = []
                for _ in range(max(1, min(self.policy.workers, 64))):
                    item = self.frontier.pop_next()
                    if not item:
                        break
                    batch.append(item)
                if not batch:
                    break
                results = await asyncio.gather(*(self._fetch_one(item) for item in batch), return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        self.stats["errors"] += 1
                        self.on_event("crawler_error", {"message": str(result)})
                self.stats["queued"] = self.frontier.get_stats().get("pending", 0)
                self.stats["uploaded"] = self.uploaded
        finally:
            if self._upload_pool:
                await asyncio.get_running_loop().run_in_executor(None, self._upload_pool.shutdown, True)
            self.mirror.write_manifest()
            self.warc_generator.close()
            await self.fetcher.close()
            self.stats["uploaded"] = self.uploaded
            self.stats["upload_failed"] = self.upload_failed
            self.stats["status"] = "AWEC Stopped" if self.stopped else "AWEC Completed"
            self.on_event("crawl_finished", dict(self.stats))

    async def _fetch_one(self, item):
        url = item["url"]
        res = await self.fetcher.fetch(url, parent_url=item.get("parent_url", ""), depth=item.get("depth", 0))
        if not (200 <= res.status < 400):
            self.stats["errors"] += 1
            self.stats["retries"] += 1
            self.frontier.mark_failed(item["id"], retry_delay=3.0)
            self.on_event("request_failed", {"url": url, "status": res.status})
            return
        payload = res.wire_bytes
        if not self._disk_ok(len(payload)):
            self.frontier.mark_failed(item["id"], retry_delay=60.0)
            self.on_event("storage_guard", {"url": url, "message": "Not enough temporary storage for this resource."})
            return
        ct = res.content_type.lower()
        self.stats["pages" if "html" in ct else "files"] += 1
        self.stats["bytes"] += len(payload)
        local_path = self.mirror.save(res.final_url, payload, res.content_type, res.status, res.response_headers)
        self.stats["mirrored"] += 1
        self.stats["mirror_bytes"] += len(payload)
        rec = ResourceRecord(
            id=uuid.uuid4().hex, requested_url=url, final_url=res.final_url, canonical_url=res.canonical_url,
            parent_url=item.get("parent_url", ""), discovery_type=item.get("discovery_type", "html_link"),
            status=res.status, request_headers=res.request_headers, response_headers=res.response_headers,
            content_type=res.content_type, wire_size=len(payload), decoded_size=len(res.decoded_bytes),
            sha256_wire=res.wire_hash, sha256_decoded=res.decoded_hash,
            downloaded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), duration_ms=res.duration_ms,
            archive_path=str(local_path), challenge_detected=res.challenge_detected,
            challenge_reason=res.challenge_reason, network_mode=self.policy.network_mode)
        w_offset, w_len = self.warc_generator.write_warc_response(rec, payload)
        rec.warc_file = self.warc_generator.warc_path.name
        rec.warc_offset = w_offset
        rec.warc_length = w_len
        self.store.save_resource(rec)
        self.frontier.mark_completed(item["id"])

        # Never wait for IA on the critical crawl path. Local/WARC persistence is complete
        # first; the publisher drains independently and failures remain visible.
        if self.ia_uploader and self._upload_pool:
            self._upload_pool.submit(self._publish, local_path, res.final_url, res.content_type, len(payload))

        body = res.decoded_bytes.decode("utf-8", errors="ignore")
        discovered = []
        if "html" in ct:
            self.indexer.index_resource(rec.id, res.final_url, item["domain"], body)
            if self.policy.follow_links and item["depth"] < self.policy.max_depth:
                discovered = ContentExtractor.extract_html_links(res.final_url, body)
        elif "css" in ct:
            discovered = ContentExtractor.extract_css_links(res.final_url, body)
        elif "javascript" in ct or "ecmascript" in ct:
            discovered = ContentExtractor.extract_js_links(res.final_url, body)
        elif "xml" in ct or urlparse(res.final_url).path.lower().endswith((".xml", ".xml.gz")):
            discovered = [(u, "sitemap_url", "text/html") for u in ContentExtractor.parse_sitemap(payload, res.final_url.lower().endswith(".gz"))]
        if "robots" in urlparse(res.final_url).path.lower():
            for line in body.splitlines():
                if line.strip().lower().startswith("sitemap:"):
                    discovered.append((line.split(":", 1)[1].strip(), "sitemap", "application/xml"))
        self.stats["discovered"] += len(discovered)
        for ext_url, disc_type, mime_hint in discovered:
            if self._should_queue(ext_url, mime_hint, disc_type):
                self.link_graph.add_edge(res.final_url, ext_url, disc_type, self.crawl_id)
                next_depth = item["depth"] + (1 if "html" in ct and disc_type not in self.EMBEDDED_RESOURCE_KINDS else 0)
                self.frontier.add_url(ext_url, depth=next_depth, parent_url=res.final_url, discovery_type=disc_type)
                self.stats["enqueued"] += 1
        self.on_event("discovery", {"url": res.final_url, "found": len(discovered), "queued": self.stats["enqueued"], "rejected": self.stats.get("rejected", 0)})
        self.on_event("page_fetched", {"url": res.final_url, "status": res.status, "size": len(payload), "local_path": str(local_path), "content_type": res.content_type})
        self.stats["active_domain"] = urlparse(res.final_url).hostname or ""


def find_resumable_crawls(root: Path):
    out = []
    for db in sorted(root.glob("crawls/*/state.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            store = StateStore(db)
            counts = store.frontier_counts()
            if counts.get("pending", 0) or counts.get("in_progress", 0):
                out.append({"path": str(db.parent), "crawl_id": db.parent.name, "counts": counts})
        except Exception:
            continue
    return out
