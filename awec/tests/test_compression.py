import unittest
import gzip
import zlib
from awec.http.compression import CompressionDecoder, process_payload, HAS_BROTLI

if HAS_BROTLI:
    import brotli

class TestCompression(unittest.TestCase):
    def test_gzip_decoding(self):
        original = b"Hello, AWEC Web Archive Engine Gzip!"
        compressed = gzip.compress(original)
        payload = process_payload(compressed, "gzip")
        self.assertEqual(payload.decoded_bytes, original)
        self.assertEqual(payload.wire_bytes, compressed)
        self.assertEqual(payload.content_encoding, "gzip")
        self.assertNotEqual(payload.sha256_wire, payload.sha256_decoded)

    def test_brotli_decoding(self):
        if not HAS_BROTLI:
            self.skipTest("Brotli module not installed")
        original = b"Hello, Brotli Compression Test for AWEC!"
        compressed = brotli.compress(original)
        payload = process_payload(compressed, "br")
        self.assertEqual(payload.decoded_bytes, original)
        self.assertEqual(payload.content_encoding, "br")

    def test_deflate_decoding(self):
        original = b"Deflate payload text"
        compressed = zlib.compress(original)
        payload = process_payload(compressed, "deflate")
        self.assertEqual(payload.decoded_bytes, original)

if __name__ == "__main__":
    unittest.main()
