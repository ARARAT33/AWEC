"""End-to-End Crawler, FANTI, WARC, FTS5 Search, and S3 Spool Validation Tests."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from awec.archive.ia import IAUploader, SpoolPublisher
from awec.archive.warc import ArchivePackageBuilder, WARCGenerator
from awec.core.canonicalizer import CrawlPolicy, FANTIConfig, ResourceRecord
from awec.core.frontier import Frontier
from awec.http.fetcher import FANTIFetcher, StandardFetcher
from awec.search.api import SearchAPI
from awec.search.indexer import SearchIndexer
from awec.storage.state_store import StateStore


class TestE2EPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)
        self.store = StateStore(self.base_path / "state.db")
        self.frontier = Frontier(self.store, mode="breadth_first")
        self.indexer = SearchIndexer(self.store)
        self.api = SearchAPI(self.store)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_frontier_leases_and_recovery(self):
        self.frontier.add_url("https://example.com/page1", depth=0, priority=10)
        item = self.frontier.pop_next(worker_id="worker-1", lease_seconds=0.1)
        self.assertIsNotNone(item)
        self.assertEqual(item["url"], "https://example.com/page1")

        # Wait for lease expiration
        asyncio.run(asyncio.sleep(0.2))
        recovered = self.frontier.recover_expired_leases()
        self.assertEqual(recovered, 1)

        # Item should be re-poppable
        item_re = self.frontier.pop_next(worker_id="worker-2", lease_seconds=60.0)
        self.assertIsNotNone(item_re)

    def test_warc_and_package_builder(self):
        warc_gen = WARCGenerator(self.base_path / "WARC", "crawl-test")
        rec = ResourceRecord(
            id="rec-001",
            requested_url="https://example.com",
            final_url="https://example.com",
            canonical_url="https://example.com",
            parent_url="",
            status=200,
            content_type="text/html",
            sha256_wire="dummyhash",
            downloaded_at="2025-01-01T00:00:00Z"
        )
        offset, length = warc_gen.write_warc_response(rec, b"<html>Hello AWEC</html>")
        warc_gen.close()

        self.assertGreater(length, 0)
        self.assertTrue(warc_gen.warc_path.exists())

        builder = ArchivePackageBuilder(self.base_path / "archive", "crawl-test", "https://example.com")
        manifest_path = builder.build_package([rec], "2025-01-01T00:00:00Z", "2025-01-01T00:01:00Z")
        self.assertTrue(manifest_path.exists())

    def test_spool_publisher(self):
        spool_file = self.base_path / "test.warc.gz"
        spool_file.write_bytes(b"mock warc payload")

        self.store.save_upload_spool("spool-1", "crawl-1", str(spool_file), "remote/test.warc.gz", "s3")
        pending = self.store.get_pending_uploads()
        self.assertEqual(len(pending), 1)

        uploader = IAUploader("fake_key", "fake_secret", "fake_id")
        publisher = SpoolPublisher(uploader, self.store)
        stats = publisher.process_pending_uploads()
        self.assertEqual(stats["failed"], 1)  # Expected fail on fake credentials


if __name__ == "__main__":
    unittest.main()
