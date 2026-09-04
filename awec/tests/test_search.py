"""Unit tests for FTS5 Search Engine, Armenian Unicode search, and Link Graph."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from awec.search.api import SearchAPI
from awec.search.indexer import LinkGraphManager, SearchIndexer
from awec.storage.state_store import StateStore


class TestSearchSubsystem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.store = StateStore(self.tmp.name)
        self.indexer = SearchIndexer(self.store)
        self.api = SearchAPI(self.store)
        self.graph = LinkGraphManager(self.store)

    def test_search_and_armenian_text(self):
        html_hy = """<html><head><title>Հայաստանի Լուրեր</title></head><body><h1>Հայաստան</h1><p>Այս էջը Հայաստանի մասին է։</p></body></html>"""
        html_en = """<html><head><title>Armenia News</title></head><body><h1>Armenia Page</h1><p>This is about Armenia.</p></body></html>"""

        self.indexer.index_resource("rec-1", "https://hy.wikipedia.org/wiki/Armenia", "hy.wikipedia.org", html_hy)
        self.indexer.index_resource("rec-2", "https://en.wikipedia.org/wiki/Armenia", "en.wikipedia.org", html_en)

        # Search Armenian text
        res_hy = self.api.search("Հայաստան")
        self.assertGreaterEqual(len(res_hy), 1)
        self.assertEqual(res_hy[0]["domain"], "hy.wikipedia.org")

        # Search English text
        res_en = self.api.search("Armenia")
        self.assertGreaterEqual(len(res_en), 1)

    def test_link_graph(self):
        self.graph.add_edge("https://a.com", "https://b.com", "html_link", "crawl-123")
        # Ensure edge added without error
        with self.store._get_conn() as conn:
            cur = conn.execute("SELECT COUNT(*) as cnt FROM link_graph")
            self.assertEqual(cur.fetchone()["cnt"], 1)


if __name__ == "__main__":
    unittest.main()
