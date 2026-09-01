"""Rate Limiting, Adaptive Backoff, and Domain Circuit Breaker for AWEC."""
from __future__ import annotations

import asyncio
import email.utils
import math
import random
import time
from enum import Enum
from typing import Dict, Optional


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()

    def record_success(self) -> None:
        if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            self.state = CircuitState.CLOSED
        self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold and self.state == CircuitState.CLOSED:
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_state_change >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = time.time()
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True
        return False


class RateLimiter:
    def __init__(self, rate_per_sec: float = 2.0, concurrency_limit: int = 4):
        self.rate_per_sec = rate_per_sec
        self.concurrency_limit = concurrency_limit
        self.next_time: Dict[str, float] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.active_requests: Dict[str, int] = {}
        self.lock = asyncio.Lock()

    def get_circuit_breaker(self, domain: str) -> CircuitBreaker:
        if domain not in self.circuit_breakers:
            self.circuit_breakers[domain] = CircuitBreaker()
        return self.circuit_breakers[domain]

    async def acquire(self, domain: str) -> bool:
        async with self.lock:
            cb = self.get_circuit_breaker(domain)
            if not cb.can_execute():
                return False

            active = self.active_requests.get(domain, 0)
            if active >= self.concurrency_limit:
                return False

            now = time.time()
            nxt = self.next_time.get(domain, 0.0)
            delay = max(0.0, nxt - now)

            self.next_time[domain] = max(now, nxt) + (1.0 / max(0.1, self.rate_per_sec))
            self.active_requests[domain] = active + 1

        if delay > 0:
            await asyncio.sleep(delay)
        return True

    async def release(self, domain: str) -> None:
        async with self.lock:
            active = self.active_requests.get(domain, 1)
            self.active_requests[domain] = max(0, active - 1)


def parse_retry_after(header_val: str) -> Optional[float]:
    if not header_val:
        return None
    val = header_val.strip()
    if val.isdigit():
        return float(val)
    try:
        parsed_date = email.utils.parsedate_to_datetime(val)
        if parsed_date:
            delay = (parsed_date.timestamp() - time.time())
            return max(0.0, delay)
    except Exception:
        pass
    return None


def calculate_backoff(attempt: int, base: float = 1.0, max_delay: float = 60.0, jitter: bool = True) -> float:
    delay = min(max_delay, base * (2 ** attempt))
    if jitter:
        delay = delay * random.uniform(0.5, 1.5)
    return delay
