import unittest
import time
from awec.http.retries import CircuitBreaker, CircuitState, parse_retry_after, calculate_backoff

class TestRetries(unittest.TestCase):
    def test_circuit_breaker(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)
        self.assertTrue(cb.can_execute())

        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())

        time.sleep(0.15)
        self.assertTrue(cb.can_execute())
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_retry_after_parser(self):
        self.assertEqual(parse_retry_after("120"), 120.0)
        self.assertIsNone(parse_retry_after(""))

    def test_backoff_calculation(self):
        delay = calculate_backoff(attempt=2, base=1.0, max_delay=60.0, jitter=False)
        self.assertEqual(delay, 4.0)

if __name__ == "__main__":
    unittest.main()
