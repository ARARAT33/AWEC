"""Unit tests for StandardFetcher, FANTIFetcher, and RetryDecisionEngine."""
from __future__ import annotations

import unittest
from awec.core.canonicalizer import CrawlPolicy, FANTIConfig
from awec.http.fetcher import FANTIFetcher, RetryAction, RetryDecisionEngine, StandardFetcher
from awec.storage.state_store import StateStore


class TestFetcherSubsystem(unittest.TestCase):
    def test_retry_decision_engine(self):
        act, delay, reason = RetryDecisionEngine.evaluate(200, None, 0, 5)
        self.assertEqual(act, RetryAction.DO_NOT_RETRY)

        act, delay, reason = RetryDecisionEngine.evaluate(404, None, 0, 5)
        self.assertEqual(act, RetryAction.DO_NOT_RETRY)

        act, delay, reason = RetryDecisionEngine.evaluate(429, None, 0, 5)
        self.assertEqual(act, RetryAction.RETRY_LATER)
        self.assertGreater(delay, 0)

        act, delay, reason = RetryDecisionEngine.evaluate(503, None, 0, 5)
        self.assertEqual(act, RetryAction.RETRY_LATER)

        act, delay, reason = RetryDecisionEngine.evaluate(503, None, 5, 5)
        self.assertEqual(act, RetryAction.FAIL_PERMANENTLY)

    def test_fanti_config_and_profiles(self):
        fanti_cfg = FANTIConfig(user_agent_profile="archive", header_profile="Default Archive")
        fetcher = FANTIFetcher(fanti_cfg)
        ua = fetcher.get_effective_user_agent()
        self.assertIn("AWEC", ua)

        headers = fetcher.get_effective_headers("https://example.com")
        self.assertIn("User-Agent", headers)
        self.assertIn("Referer", headers)

    def test_host_profile_telemetry(self):
        fanti_cfg = FANTIConfig(initial_concurrency=4, initial_delay=0.5)
        fetcher = FANTIFetcher(fanti_cfg)
        fetcher.update_telemetry("example.com", status=200, duration_ms=100.0, is_error=False)
        hp = fetcher.get_host_profile("example.com")
        self.assertEqual(hp.state, "HEALTHY")
        self.assertEqual(hp.circuit_state, "CLOSED")

        # Simulate repeated failures to trigger circuit breaker
        for _ in range(5):
            fetcher.update_telemetry("example.com", status=503, duration_ms=500.0, is_error=True)

        hp = fetcher.get_host_profile("example.com")
        self.assertEqual(hp.circuit_state, "OPEN")
        self.assertEqual(hp.state, "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
