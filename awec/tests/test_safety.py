import unittest
from awec.safety.policy import SSRFGuard, RobotsManager

class TestSafetyPolicy(unittest.TestCase):
    def test_ssrf_private_ip(self):
        valid, reason = SSRFGuard.validate_url("http://127.0.0.1/admin")
        self.assertFalse(valid)
        self.assertEqual(reason, "SSRF_PRIVATE_IP")

        valid, reason = SSRFGuard.validate_url("http://10.0.0.5:8080/internal")
        self.assertFalse(valid)
        self.assertEqual(reason, "SSRF_PRIVATE_IP")

    def test_robots_manager(self):
        rm = RobotsManager(user_agent="AWEC/3.0", mode="standard")
        robots_txt = """
User-agent: *
Disallow: /private/
Allow: /public/
"""
        rm.parse_robots("https://example.com", robots_txt)
        self.assertFalse(rm.can_fetch("https://example.com/private/data"))
        self.assertTrue(rm.can_fetch("https://example.com/public/data"))

if __name__ == "__main__":
    unittest.main()
