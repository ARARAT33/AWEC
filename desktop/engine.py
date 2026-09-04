"""AWEC desktop engine bridge.

The v11 desktop UI uses the same AWECrawler implementation that owns the
complete reachable-resource mirror, while keeping the Qt signal contract used
by the existing desktop UI.
"""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from desktop.crawler_engine import AWECrawler, CrawlPolicy


class Engine(QObject):
    log = Signal(str)
    stats = Signal(dict)
    finished = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.is_paused = False
        self.stop_event = threading.Event()
        self._crawler: AWECrawler | None = None

    def _policy(self) -> CrawlPolicy:
        return CrawlPolicy(
            network_mode=getattr(self.cfg, "network_mode", "standard"),
            follow_links=True,
            follow_external_domains=not getattr(self.cfg, "same_domain_only", True),
            include_subdomains=True,
            download_files=True,
            respect_robots=getattr(self.cfg, "respect_robots", True),
            max_depth=getattr(self.cfg, "max_depth", 8),
            max_file_size=getattr(self.cfg, "max_file_size", -1),
            file_types=getattr(self.cfg, "file_types", ["*"]) or ["*"],
            workers=max(1, getattr(self.cfg, "workers", 32)),
            rate_limit_per_host=max(0.0, getattr(self.cfg, "per_host_delay", 0.5)),
            retry_delays=[5, 15, 30],
            ua_rotation=getattr(self.cfg, "ua_rotation_enabled", False),
            delay_jitter=max(0.0, getattr(self.cfg, "delay_jitter_sec", 0.25)),
            auto_headers=True,
            verify_ssl=getattr(self.cfg, "verify_ssl", True),
            proxy_url=getattr(self.cfg, "proxy_url", ""),
            custom_headers={},
            max_local_mb=getattr(self.cfg, "max_local_storage_mb", 50),
            purge_after_upload=False,
            mirror_all_resources=True,
        )

    def _event(self, name, payload):
        if name == "crawl_started":
            self.log.emit("🚀 v11 crawl started — downloading the reachable site resource graph")
            self.log.emit("📂 Local mirror: AWEC/crawls/<crawl-id>/site/")
        elif name == "page_fetched":
            self.log.emit(
                f"⬇️ [{payload.get('status', 0)}] {payload.get('url', '')} "
                f"→ {payload.get('local_path', '')} ({payload.get('size', 0):,} bytes)"
            )
        elif name == "crawl_finished":
            self.log.emit(
                "🏁 Site download finished: "
                f"{payload.get('mirrored', 0):,} resources / "
                f"{payload.get('mirror_bytes', 0):,} bytes mirrored"
            )

    async def _run(self):
        seeds = list(getattr(self.cfg, "seeds", []) or [])
        if not seeds:
            self.log.emit("❌ No seed URL configured — crawl not started")
            return

        output_dir = Path(getattr(self.cfg, "fallback_dir", Path.home() / "AWEC"))
        self._crawler = AWECrawler(
            seeds=seeds,
            policy=self._policy(),
            on_event=self._event,
            output_dir=output_dir,
        )
        self.log.emit(f"🌐 Seeds: {', '.join(seeds)}")
        self.log.emit("🔎 Resource mode: ALL reachable HTML/CSS/JS/media/files")
        await self._crawler.run()
        s = self._crawler.stats
        self.stats.emit({
            "queued": s.get("queued", 0),
            "enqueued": s.get("enqueued", 0),
            "fetched": s.get("pages", 0) + s.get("files", 0),
            "pages": s.get("pages", 0),
            "found": s.get("files", 0),
            "files": s.get("files", 0),
            "downloaded": s.get("mirrored", 0),
            "uploaded": 0,
            "mirrored": s.get("mirrored", 0),
            "mirror_bytes": s.get("mirror_bytes", 0),
            "errors": s.get("errors", 0),
            "active": 0,
            "speed": s.get("status", "Completed"),
            "active_domain": seeds[0],
        })

    def start(self):
        try:
            self.log.emit("▶ Starting AWEC v11 crawler engine NOW")
            asyncio.run(self._run())
        except Exception as exc:
            self.log.emit(f"💥 Fatal crawler error: {type(exc).__name__}: {exc}")
        finally:
            self.finished.emit(json.dumps({
                "status": "stopped" if self.stop_event.is_set() else "completed"
            }))

    def stop(self):
        self.stop_event.set()
        if self._crawler:
            self._crawler.stop()

    def pause(self):
        self.is_paused = True
        if self._crawler:
            self._crawler.pause()

    def resume(self):
        self.is_paused = False
        if self._crawler:
            self._crawler.resume()
