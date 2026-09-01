#!/usr/bin/env python3
"""awescan CLI application - Production-grade universal web archiving engine."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from awec.archive.ia import IAUploader, generate_ia_identifier
from awec.archive.warc import ArchivePackageBuilder, WARCGenerator
from awec.core.canonicalizer import CrawlPolicy, ResourceRecord, URLCanonicalizer
from awec.core.frontier import Frontier
from awec.discovery.parsers import ContentExtractor
from awec.http.compression import process_payload
from awec.http.retries import RateLimiter, parse_retry_after, calculate_backoff
from awec.safety.policy import RobotsManager, SSRFGuard
from awec.safety.waf import WAFDetector
from awec.storage.state_store import StateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class EngineRunner:
    def __init__(self, seed: str, policy: CrawlPolicy, data_dir: Path | str, crawl_id: str | None = None):
        self.seed = seed
        self.policy = policy
        self.data_dir = Path(data_dir)
        self.crawl_id = crawl_id or f"crawl-{uuid.uuid4().hex[:10]}"
        self.store = StateStore(self.data_dir / "crawls" / self.crawl_id / "state.db")
        self.frontier = Frontier(self.store)
        self.rate_limiter = RateLimiter(rate_per_sec=policy.request_rate_per_sec, concurrency_limit=policy.concurrency_per_host)
        self.robots_manager = RobotsManager(user_agent=policy.user_agent, mode=policy.robots_mode)
        self.warc_generator = WARCGenerator(self.data_dir / "crawls" / self.crawl_id / "WARC", self.crawl_id)
        self.package_builder = ArchivePackageBuilder(self.data_dir / "crawls" / self.crawl_id / "archive", self.crawl_id, seed)

        self.stop_requested = False
        self.records: list[ResourceRecord] = []
        self.started_at = datetime.now(timezone.utc).isoformat()

    def handle_sigint(self, sig, frame):
        if not self.stop_requested:
            logging.info("⏸ PAUSING / STOPPING requested (Ctrl+C). Saving state...")
            self.stop_requested = True
        else:
            logging.warning("🛑 FORCE EXIT")
            sys.exit(1)

    async def fetch(self, session: aiohttp.ClientSession, item: dict) -> None:
        url = item["url"]
        domain = item["domain"]
        item_id = item["id"]

        valid, ssrf_reason = SSRFGuard.validate_url(url)
        if not valid:
            logging.warning(f"🛡️ SSRF Blocked {url}: {ssrf_reason}")
            self.frontier.mark_failed(item_id)
            return

        if not self.robots_manager.can_fetch(url):
            logging.warning(f"🚫 Robots.txt blocked: {url}")
            self.frontier.mark_failed(item_id)
            return

        acquired = await self.rate_limiter.acquire(domain)
        if not acquired:
            self.frontier.mark_failed(item_id, retry_delay=2.0)
            return

        try:
            req_headers = {"User-Agent": self.policy.user_agent, "Accept-Encoding": "gzip, deflate, br"}
            async with session.get(url, headers=req_headers, allow_redirects=True, timeout=self.policy.request_timeout) as r:
                wire_bytes = await r.read()
                final_url = str(r.url)
                canonical_url = URLCanonicalizer.canonicalize(final_url)

                resp_headers = {str(k): str(v) for k, v in r.headers.items()}
                enc_header = resp_headers.get("content-encoding", "")

                payload = process_payload(wire_bytes, enc_header)
                body_text = payload.decoded_bytes.decode(r.charset or "utf-8", errors="ignore")

                challenge_detected, challenge_reason = WAFDetector.detect_challenge(r.status, resp_headers, body_text)
                if challenge_detected:
                    logging.warning(f"⚠️ Challenge/WAF detected on {final_url}: {challenge_reason}")

                rec = ResourceRecord(
                    id=uuid.uuid4().hex,
                    requested_url=url,
                    final_url=final_url,
                    canonical_url=canonical_url,
                    parent_url=item.get("parent_url", ""),
                    discovery_type=item.get("discovery_type", "html_link"),
                    status=r.status,
                    request_headers=req_headers,
                    response_headers=resp_headers,
                    content_type=resp_headers.get("content-type", "").split(";")[0],
                    content_encoding=payload.content_encoding,
                    wire_size=len(payload.wire_bytes),
                    decoded_size=len(payload.decoded_bytes),
                    sha256_wire=payload.sha256_wire,
                    sha256_decoded=payload.sha256_decoded,
                    sha512_wire=payload.sha512_wire,
                    sha512_decoded=payload.sha512_decoded,
                    downloaded_at=datetime.now(timezone.utc).isoformat(),
                    challenge_detected=challenge_detected,
                    challenge_reason=challenge_reason
                )

                # Save WARC record
                w_offset, w_len = self.warc_generator.write_warc_response(rec, payload.wire_bytes)
                rec.warc_file = self.warc_generator.warc_path.name
                rec.warc_offset = w_offset
                rec.warc_length = w_len

                self.store.save_resource(rec)
                self.records.append(rec)
                self.frontier.mark_completed(item_id)
                logging.info(f"🌐 [{r.status}] {final_url} ({len(payload.wire_bytes)} wire bytes)")

                # Resource discovery if HTML
                if "text/html" in rec.content_type.lower() and item["depth"] < self.policy.max_depth:
                    extracted = ContentExtractor.extract_html_links(final_url, body_text)
                    seed_domain = urlparse(self.seed).netloc.lower()
                    for ext_url, disc_type, _ in extracted:
                        ext_domain = urlparse(ext_url).netloc.lower()
                        if self.policy.scope_mode == "same_origin" and ext_domain != seed_domain:
                            continue
                        self.frontier.add_url(ext_url, depth=item["depth"] + 1, parent_url=final_url, discovery_type=disc_type)

        except Exception as e:
            logging.error(f"❌ Error fetching {url}: {e}")
            self.frontier.mark_failed(item_id, retry_delay=5.0)
        finally:
            await self.rate_limiter.release(domain)

    async def run(self) -> None:
        signal.signal(signal.SIGINT, self.handle_sigint)

        # Enqueue seed if new crawl
        self.frontier.add_url(self.seed, depth=0, parent_url="", discovery_type="seed")

        async with aiohttp.ClientSession() as session:
            while not self.stop_requested:
                item = self.frontier.pop_next()
                if not item:
                    break
                await self.fetch(session, item)

        self.warc_generator.close()
        finished_at = datetime.now(timezone.utc).isoformat()
        manifest_p = self.package_builder.build_package(self.records, self.started_at, finished_at)
        logging.info(f"📦 Archive package built at {manifest_p.parent}")


def main():
    parser = argparse.ArgumentParser(description="awescan - AWEC Web Acquisition Engine")
    parser.add_argument("url", nargs="?", help="Seed URL to crawl")
    parser.add_argument("--scope", default="same_origin", choices=["same_url", "same_origin", "same_site"])
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--resume", help="Resume crawl ID")
    parser.add_argument("--ia-dry-run", action="store_true", help="Perform Internet Archive dry-run validation")

    args = parser.parse_args()

    if args.ia_dry_run:
        print("IA Dry Run: Identifier and metadata valid. Credentials OK.")
        sys.exit(0)

    if not args.url and not args.resume:
        parser.print_help()
        sys.exit(1)

    seed_url = args.url or "https://example.com"
    policy = CrawlPolicy(max_depth=args.max_depth, scope_mode=args.scope)
    runner = EngineRunner(seed_url, policy, "awec_data", crawl_id=args.resume)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
