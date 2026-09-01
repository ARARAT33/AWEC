import unittest
import asyncio
from awec.http.compression import process_payload, HAS_BROTLI
from awec.safety.waf import WAFDetector
from awec.safety.policy import SSRFGuard

if HAS_BROTLI:
    import brotli

class TestFullRegression(unittest.TestCase):
    def test_brotli_decoding_regression(self):
        if not HAS_BROTLI:
            self.skipTest("Brotli module not installed")
        data = b"GitHub assets and Brotli compressed text test"
        compressed = brotli.compress(data)
        payload = process_payload(compressed, "br")
        self.assertEqual(payload.decoded_bytes, data)
        self.assertEqual(payload.content_encoding, "br")

    def test_403_access_denied_classification(self):
        detected, reason = WAFDetector.detect_challenge(403, {}, "Forbidden")
        self.assertTrue(detected)
        self.assertEqual(reason, "HTTP 403 Forbidden Access Control")

    def test_ssrf_blocking(self):
        valid, reason = SSRFGuard.validate_url("http://127.0.0.1/metadata")
        self.assertFalse(valid)
        self.assertEqual(reason, "SSRF_PRIVATE_IP")

if __name__ == "__main__":
    unittest.main()
