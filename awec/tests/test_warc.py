import unittest
import tempfile
import os
import json
from pathlib import Path
from awec.core.canonicalizer import ResourceRecord
from awec.archive.warc import WARCGenerator, ArchivePackageBuilder

class TestWARC(unittest.TestCase):
    def test_warc_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wg = WARCGenerator(tmpdir, "test1234")
            rec = ResourceRecord(
                id="rec1",
                requested_url="https://example.com",
                final_url="https://example.com",
                canonical_url="https://example.com/",
                parent_url="",
                status=200,
                response_headers={"Content-Type": "text/html"},
                wire_size=11,
                sha256_wire="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            )
            offset, length = wg.write_warc_response(rec, b"Hello World")
            wg.close()

            self.assertGreater(length, 0)
            rec.warc_file = wg.warc_path.name
            rec.warc_offset = offset
            rec.warc_length = length

            ab = ArchivePackageBuilder(tmpdir, "test1234", "https://example.com")
            mfile = ab.build_package([rec], "2026-09-01T00:00:00Z", "2026-09-01T00:01:00Z")
            self.assertTrue(mfile.exists())

            data = json.loads(mfile.read_text())
            self.assertEqual(data["crawl_id"], "test1234")
            self.assertEqual(len(data["resources"]), 1)

if __name__ == "__main__":
    unittest.main()
