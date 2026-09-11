#!/usr/bin/env python3
"""awescan CLI application - Production-grade universal web archiving engine with IA integration."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import uuid
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List

from awec.archive.ia import IAUploader, SpoolPublisher, generate_ia_identifier
from awec.archive.warc import ArchivePackageBuilder, WARCGenerator
from awec.core.canonicalizer import CrawlPolicy, FANTIConfig, ResourceRecord, URLCanonicalizer
from awec.core.frontier import Frontier
from awec.discovery.parsers import ContentExtractor
from awec.http.fetcher import FANTIFetcher, StandardFetcher
from awec.search.api import SearchAPI
from awec.search.indexer import LinkGraphManager, SearchIndexer
from awec.storage.state_store import StateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class AWECConfig:
    """Advanced configuration for AWEC with deep customization options."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        if config_path and config_path.exists():
            self.load_config(config_path)
    
    def load_config(self, path: Path) -> None:
        """Load configuration from JSON file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load config from {path}: {e}")
            self.config = {}
    
    def save_config(self, path: Path) -> None:
        """Save current configuration to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation support."""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value with dot notation support."""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value
    
    @property
    def ia_access_key(self) -> str:
        return self.get('internet_archive.access_key', '') or os.getenv('IA_ACCESS_KEY', '')
    
    @property
    def ia_secret_key(self) -> str:
        return self.get('internet_archive.secret_key', '') or os.getenv('IA_SECRET_KEY', '')
    
    @property
    def ia_collection(self) -> str:
        return self.get('internet_archive.collection', 'awec_archives') or os.getenv('AWEC_IA_COLLECTION', 'awec_archives')
    
    @property
    def ia_endpoint(self) -> str:
        return self.get('internet_archive.endpoint', 'https://s3.us.archive.org')
    
    @property
    def auto_upload_to_ia(self) -> bool:
        return self.get('internet_archive.auto_upload', False)
    
    @property
    def awec_format_version(self) -> str:
        return self.get('archive.format_version', '1.0')
    
    @property
    def compression_level(self) -> int:
        return self.get('archive.compression_level', 6)
    
    @property
    def enable_deduplication(self) -> bool:
        return self.get('archive.deduplication', True)
    
    @property
    def max_concurrent_uploads(self) -> int:
        return self.get('internet_archive.max_concurrent_uploads', 4)


class EngineRunner:
    def __init__(self, seed: str, policy: CrawlPolicy, fanti_config: FANTIConfig, 
                 data_dir: Path | str, crawl_id: str | None = None,
                 awec_config: Optional[AWECConfig] = None):
        self.seed = seed
        self.policy = policy
        self.fanti_config = fanti_config
        self.data_dir = Path(data_dir)
        self.crawl_id = crawl_id or f"crawl-{uuid.uuid4().hex[:10]}"
        self.awec_config = awec_config or AWECConfig()
        
        crawl_path = self.data_dir / "crawls" / self.crawl_id
        self.store = StateStore(crawl_path / "state.db")
        self.frontier = Frontier(self.store)
        self.warc_generator = WARCGenerator(crawl_path / "WARC", self.crawl_id, 
                                            compression_level=self.awec_config.compression_level)
        self.package_builder = ArchivePackageBuilder(
            crawl_path / "archive", 
            self.crawl_id, 
            seed,
            awec_config=self.awec_config
        )
        self.indexer = SearchIndexer(self.store)
        self.link_graph = LinkGraphManager(self.store)

        if self.policy.network_mode == "fanti":
            self.fetcher = FANTIFetcher(self.fanti_config, self.store)
        else:
            self.fetcher = StandardFetcher(self.policy, self.store)

        self.stop_requested = False
        self.records: list[ResourceRecord] = []
        self.started_at = datetime.now(timezone.utc).isoformat()
        
        # IA Uploader initialization
        self.ia_uploader: Optional[IAUploader] = None
        self.spool_publisher: Optional[SpoolPublisher] = None
        self._init_ia_uploader()
        
        # Concurrency control for uploads
        self.upload_semaphore = asyncio.Semaphore(self.awec_config.max_concurrent_uploads)

    def _init_ia_uploader(self) -> None:
        """Initialize Internet Archive uploader if credentials are available."""
        access_key = self.awec_config.ia_access_key
        secret_key = self.awec_config.ia_secret_key
        
        if access_key and secret_key:
            identifier = generate_ia_identifier(
                urlparse(self.seed).netloc,
                self.crawl_id,
                prefix="awecrawl"
            )
            self.ia_uploader = IAUploader(
                access_key=access_key,
                secret_key=secret_key,
                identifier=identifier,
                endpoint_url=self.awec_config.ia_endpoint,
                collection=self.awec_config.ia_collection,
                title=f"AWEC Crawl: {self.seed}",
                creator="AWEC Web Archiver",
                description=f"Automated web crawl of {self.seed} using AWEC"
            )
            self.spool_publisher = SpoolPublisher(self.ia_uploader, self.store)
            logging.info(f"📤 IA Uploader initialized for collection '{self.awec_config.ia_collection}'")
        else:
            logging.warning("⚠️  IA credentials not configured. Upload to Internet Archive disabled.")

    def handle_sigint(self, sig, frame):
        if not self.stop_requested:
            logging.info("⏸ PAUSING / STOPPING requested (Ctrl+C). Saving state...")
            self.stop_requested = True
        else:
            logging.warning("🛑 FORCE EXIT")
            sys.exit(1)

    async def fetch_item(self, item: dict) -> None:
        url = item["url"]
        item_id = item["id"]

        res = await self.fetcher.fetch(
            url,
            parent_url=item.get("parent_url", ""),
            depth=item.get("depth", 0)
        )

        if res.status >= 200 and res.status < 400:
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
                content_encoding=res.encoding,
                wire_size=len(res.wire_bytes),
                decoded_size=len(res.decoded_bytes),
                sha256_wire=res.wire_hash,
                sha256_decoded=res.decoded_hash,
                downloaded_at=datetime.now(timezone.utc).isoformat(),
                duration_ms=res.duration_ms,
                challenge_detected=res.challenge_detected,
                challenge_reason=res.challenge_reason,
                network_mode=self.policy.network_mode
            )

            w_offset, w_len = self.warc_generator.write_warc_response(rec, res.wire_bytes)
            rec.warc_file = self.warc_generator.warc_path.name
            rec.warc_offset = w_offset
            rec.warc_length = w_len

            self.store.save_resource(rec)
            self.records.append(rec)
            self.frontier.mark_completed(item_id)
            logging.info(f"🌐 [{res.status}] [{self.policy.network_mode.upper()}] {res.final_url} ({len(res.wire_bytes)} wire bytes)")

            # Index for search & extract links
            body_text = res.decoded_bytes.decode("utf-8", errors="ignore")
            if "text/html" in res.content_type.lower():
                self.indexer.index_resource(rec.id, res.final_url, item["domain"], body_text)

                if item["depth"] < self.policy.max_depth:
                    extracted = ContentExtractor.extract_html_links(res.final_url, body_text)
                    seed_domain = urlparse(self.seed).netloc.lower()
                    for ext_url, disc_type, _ in extracted:
                        ext_domain = urlparse(ext_url).netloc.lower()
                        if self.policy.scope_mode == "same_origin" and ext_domain != seed_domain:
                            continue
                        self.link_graph.add_edge(res.final_url, ext_url, disc_type, self.crawl_id)
                        self.frontier.add_url(ext_url, depth=item["depth"] + 1, parent_url=res.final_url, discovery_type=disc_type)
        else:
            logging.warning(f"❌ Failed fetch for {url}: {res.error or res.status}")
            self.frontier.mark_failed(item_id, retry_delay=5.0)

    async def upload_to_ia(self, file_path: Path, remote_key: str) -> bool:
        """Upload a file to Internet Archive with semaphore control."""
        async with self.upload_semaphore:
            if not self.ia_uploader:
                return False
            
            loop = asyncio.get_event_loop()
            success, msg = await loop.run_in_executor(
                None,
                self.ia_uploader.upload_file_s3,
                file_path,
                remote_key,
                "application/octet-stream",
                None
            )
            
            if success:
                logging.info(f"✅ Uploaded to IA: {remote_key} ({msg})")
            else:
                logging.error(f"❌ IA upload failed: {remote_key} - {msg}")
            
            return success

    async def process_ia_uploads(self) -> None:
        """Process pending uploads to Internet Archive."""
        if not self.spool_publisher:
            return
        
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(None, self.spool_publisher.process_pending_uploads)
        logging.info(f"📊 IA Upload Stats: {stats}")

    async def run(self) -> None:
        signal.signal(signal.SIGINT, self.handle_sigint)
        self.frontier.add_url(self.seed, depth=0, parent_url="", discovery_type="seed")

        while not self.stop_requested:
            item = self.frontier.pop_next()
            if not item:
                break
            await self.fetch_item(item)

        self.warc_generator.close()
        await self.fetcher.close()
        finished_at = datetime.now(timezone.utc).isoformat()
        manifest_p = self.package_builder.build_package(self.records, self.started_at, finished_at)
        logging.info(f"📦 Archive package built at {manifest_p.parent}")
        
        # Auto-upload to Internet Archive if enabled and credentials available
        if self.awec_config.auto_upload_to_ia and self.ia_uploader:
            logging.info("🚀 Starting automatic upload to Internet Archive...")
            
            # Upload WARC file
            warc_path = self.warc_generator.warc_path
            if warc_path.exists():
                remote_key = f"warc/{warc_path.name}"
                await self.upload_to_ia(warc_path, remote_key)
            
            # Upload manifest
            if manifest_p.exists():
                remote_key = f"manifest/{manifest_p.name}"
                await self.upload_to_ia(manifest_p, remote_key)
            
            # Upload any additional archive files
            archive_dir = self.package_builder.archive_dir
            if archive_dir.exists():
                for file_path in archive_dir.rglob("*"):
                    if file_path.is_file():
                        relative_path = file_path.relative_to(archive_dir)
                        remote_key = f"archive/{relative_path}"
                        await self.upload_to_ia(file_path, remote_key)
            
            # Process any spooled uploads
            await self.process_ia_uploads()
            
            logging.info("✅ Internet Archive upload complete!")


def main():
    parser = argparse.ArgumentParser(
        description="awescan - AWEC Web Acquisition Engine with Internet Archive Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  awescan https://example.com --network-mode standard --max-depth 5
  awescan https://example.com --network-mode fanti --scope same_site
  awescan --resume crawl-abc123 --upload-to-ia
  awescan https://example.com --config awec_config.json --auto-upload-ia
  
Configuration:
  Create a JSON config file for advanced settings:
  {
    "internet_archive": {
      "access_key": "your_access_key",
      "secret_key": "your_secret_key",
      "collection": "my_collection",
      "endpoint": "https://s3.us.archive.org",
      "auto_upload": true,
      "max_concurrent_uploads": 4
    },
    "archive": {
      "format_version": "1.0",
      "compression_level": 6,
      "deduplication": true
    }
  }
        """
    )
    parser.add_argument("url", nargs="?", help="Seed URL to crawl")
    parser.add_argument("--network-mode", default="standard", choices=["standard", "fanti"], 
                       help="Network mode (standard or fanti)")
    parser.add_argument("--scope", default="same_origin", 
                       choices=["same_url", "same_origin", "same_site", "allowlist"],
                       help="Crawl scope policy")
    parser.add_argument("--max-depth", type=int, default=8, help="Maximum crawl depth")
    parser.add_argument("--max-urls", type=int, default=0, help="Maximum URLs to crawl (0=unlimited)")
    parser.add_argument("--max-bytes", type=int, default=0, help="Maximum bytes to download (0=unlimited)")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrency per host")
    parser.add_argument("--global-concurrency", type=int, default=32, help="Global concurrency limit")
    parser.add_argument("--user-agent", type=str, default=None, help="Custom User-Agent string")
    parser.add_argument("--resume", help="Resume crawl ID")
    parser.add_argument("--search", help="Perform FTS search on local state database")
    parser.add_argument("--config", type=Path, help="Path to AWEC configuration JSON file")
    parser.add_argument("--ia-dry-run", action="store_true", 
                       help="Perform Internet Archive dry-run validation")
    parser.add_argument("--ia-validate", action="store_true",
                       help="Validate IA credentials and collection before crawling")
    parser.add_argument("--auto-upload-ia", action="store_true",
                       help="Automatically upload completed crawl to Internet Archive")
    parser.add_argument("--ia-collection", type=str, help="Internet Archive collection name")
    parser.add_argument("--ia-endpoint", type=str, default="https://s3.us.archive.org",
                       help="Internet Archive S3 endpoint URL")
    parser.add_argument("--generate-config", type=Path, metavar="PATH",
                       help="Generate a sample configuration file at the specified path")
    parser.add_argument("--show-stats", action="store_true",
                       help="Show detailed crawl statistics after completion")
    parser.add_argument("--enable-dedup", action="store_true", default=True,
                       help="Enable content deduplication (default: enabled)")
    parser.add_argument("--compression-level", type=int, default=6, choices=range(0,10),
                       help="WARC compression level 0-9 (default: 6)")
    parser.add_argument("--output-format", default="awec", choices=["awec", "warc-only", "both"],
                       help="Output format: awec (package+manifest), warc-only, or both")

    args = parser.parse_args()

    # Generate sample config if requested
    if args.generate_config:
        sample_config = {
            "internet_archive": {
                "access_key": os.getenv("IA_ACCESS_KEY", ""),
                "secret_key": os.getenv("IA_SECRET_KEY", ""),
                "collection": "awec_archives",
                "endpoint": "https://s3.us.archive.org",
                "auto_upload": False,
                "max_concurrent_uploads": 4
            },
            "archive": {
                "format_version": "1.0",
                "compression_level": 6,
                "deduplication": True
            },
            "crawl": {
                "default_max_depth": 8,
                "default_scope": "same_origin",
                "default_network_mode": "standard"
            },
            "performance": {
                "concurrency_per_host": 4,
                "global_concurrency": 32,
                "request_timeout": 30,
                "max_retries": 8
            }
        }
        args.generate_config.parent.mkdir(parents=True, exist_ok=True)
        with open(args.generate_config, 'w', encoding='utf-8') as f:
            json.dump(sample_config, f, indent=2, ensure_ascii=False)
        print(f"✅ Sample configuration generated at: {args.generate_config}")
        sys.exit(0)

    # Load configuration
    awec_config = AWECConfig(args.config)
    
    # Override config with command-line arguments
    if args.ia_collection:
        awec_config.set('internet_archive.collection', args.ia_collection)
    if args.ia_endpoint:
        awec_config.set('internet_archive.endpoint', args.ia_endpoint)
    if args.auto_upload_ia:
        awec_config.set('internet_archive.auto_upload', True)
    if args.compression_level is not None:
        awec_config.set('archive.compression_level', args.compression_level)

    if args.search:
        store = StateStore("awec_data/crawls/latest/state.db")
        api = SearchAPI(store)
        results = api.search(args.search)
        print(f"Search Results for '{args.search}': {len(results)} found")
        for r in results[:10]:
            print(f"- [{r.get('title') or 'No Title'}] {r.get('url')}")
        sys.exit(0)

    if args.ia_dry_run or args.ia_validate:
        access_key = awec_config.ia_access_key
        secret_key = awec_config.ia_secret_key
        collection = awec_config.ia_collection
        
        if not access_key or not secret_key:
            print("❌ IA Credentials Missing: Set IA_ACCESS_KEY and IA_SECRET_KEY environment variables or use --config")
            sys.exit(1)
        
        identifier = generate_ia_identifier("example.com", "test", prefix="awecrawl")
        uploader = IAUploader(
            access_key=access_key,
            secret_key=secret_key,
            identifier=identifier,
            endpoint_url=awec_config.ia_endpoint,
            collection=collection
        )
        
        valid, msg = uploader.validate_destination(force=True)
        if valid or "ITEM_MISSING_WILL_BE_CREATED" in msg:
            print(f"✅ IA Validation Successful: {msg}")
            if args.ia_dry_run:
                print("ℹ️  Use --auto-upload-ia to enable automatic uploads")
        else:
            print(f"❌ IA Validation Failed: {msg}")
            sys.exit(1)
        sys.exit(0)

    if not args.url and not args.resume:
        parser.print_help()
        sys.exit(1)

    seed_url = args.url or "https://example.com"
    
    # Build advanced crawl policy
    policy = CrawlPolicy(
        user_agent=args.user_agent or "AWEC/12.0 (+https://github.com/ARARAT33/AWEC; Advanced Web Archiver)",
        network_mode=args.network_mode,
        robots_mode="standard",
        max_depth=args.max_depth,
        max_urls=args.max_urls,
        max_bytes=args.max_bytes,
        concurrency_per_host=args.concurrency,
        global_concurrency=args.global_concurrency,
        max_retries=8,
        request_timeout=30,
        max_redirects=20,
        scope_mode=args.scope,
        fidelity="maximum",
        archive_target="both" if args.auto_upload_ia else "local",
        strip_tracking_params=False,
        download_files=True,
        verify_ssl=True
    )
    
    fanti_cfg = FANTIConfig(
        network_mode=args.network_mode,
        user_agent_profile="archive",
        max_concurrency=args.global_concurrency,
        max_retries=8,
        adaptive_concurrency=True,
        circuit_breaker_enabled=True
    )
    
    runner = EngineRunner(
        seed_url, 
        policy, 
        fanti_cfg, 
        "awec_data", 
        crawl_id=args.resume,
        awec_config=awec_config
    )
    asyncio.run(runner.run())
    
    if args.show_stats:
        print("\n" + "="*60)
        print("📊 CRAWL STATISTICS")
        print("="*60)
        print(f"Crawl ID: {runner.crawl_id}")
        print(f"Seed URL: {runner.seed}")
        print(f"Total Resources: {len(runner.records)}")
        print(f"Successful: {sum(1 for r in runner.records if 200 <= r.status < 400)}")
        print(f"Failed: {sum(1 for r in runner.records if r.status >= 400)}")
        total_bytes = sum(r.wire_size for r in runner.records)
        print(f"Total Data: {total_bytes / (1024*1024):.2f} MB")
        print(f"Duration: {(datetime.fromisoformat(runner.records[-1].downloaded_at) if runner.records else datetime.now(timezone.utc)) - datetime.fromisoformat(runner.started_at)}")
        print("="*60)


if __name__ == "__main__":
    main()
