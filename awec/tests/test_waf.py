import unittest
from awec.safety.waf import WAFDetector

class TestWAFDetector(unittest.TestCase):
    def test_cloudflare_challenge_detection(self):
        body = "<html><head><title>Just a moment...</title></head><body><div class='cf-browser-verification'></div></body></html>"
        detected, reason = WAFDetector.detect_challenge(503, {"Server": "cloudflare"}, body)
        self.assertTrue(detected)
        self.assertIn("Cloudflare", reason)

    def test_turnstile_detection(self):
        body = "<script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script>"
        detected, reason = WAFDetector.detect_challenge(200, {}, body)
        self.assertTrue(detected)
        self.assertIn("Turnstile", reason)

    def test_normal_html(self):
        body = "<html><body><h1>Welcome to Example</h1></body></html>"
        detected, reason = WAFDetector.detect_challenge(200, {"Server": "nginx"}, body)
        self.assertFalse(detected)

if __name__ == "__main__":
    unittest.main()
