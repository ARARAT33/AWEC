import unittest
import tempfile
import os
from pathlib import Path
from awec.storage.state_store import StateStore
from awec.core.frontier import Frontier

class TestFrontier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.store = StateStore(self.tmp.name)
        self.frontier = Frontier(self.store)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.unlink(self.tmp.name)

    def test_frontier_queue(self):
        self.assertTrue(self.frontier.add_url("https://example.com/page1"))
        self.assertFalse(self.frontier.add_url("https://example.com/page1"))  # duplicate

        item = self.frontier.pop_next()
        self.assertIsNotNone(item)
        self.assertEqual(item["url"], "https://example.com/page1")

        stats = self.frontier.get_stats()
        self.assertEqual(stats["in_progress"], 1)

        self.frontier.mark_completed(item["id"])
        stats2 = self.frontier.get_stats()
        self.assertEqual(stats2["completed"], 1)

    def test_checkpoint(self):
        self.store.save_checkpoint("run1", {"status": "paused", "count": 42})
        data = self.store.get_checkpoint("run1")
        self.assertEqual(data["status"], "paused")
        self.assertEqual(data["count"], 42)

if __name__ == "__main__":
    unittest.main()
