import unittest
from awec.core.canonicalizer import URLCanonicalizer, CrawlPolicy, ResourceRecord

class TestCanonicalizer(unittest.TestCase):
    def test_canonicalize_basic(self):
        self.assertEqual(
            URLCanonicalizer.canonicalize("HTTP://EXAMPLE.COM:80/foo/../bar/"),
            "http://example.com/bar/"
        )

    def test_canonicalize_query_sorting(self):
        self.assertEqual(
            URLCanonicalizer.canonicalize("https://example.com?b=2&a=1#fragment"),
            "https://example.com/?a=1&b=2"
        )

    def test_canonicalize_idna(self):
        self.assertEqual(
            URLCanonicalizer.canonicalize("https://münchen.de"),
            "https://xn--mnchen-3ya.de/"
        )

    def test_record_defaults(self):
        rec = ResourceRecord(id="1", requested_url="u1", final_url="u1", canonical_url="u1", parent_url="")
        self.assertEqual(rec.status, 0)
        self.assertEqual(rec.charset, "utf-8")

if __name__ == "__main__":
    unittest.main()
