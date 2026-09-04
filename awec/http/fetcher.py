"""Unified Fetcher Architecture: StandardFetcher and FANTIFetcher."""
from __future__ import annotations

import abc
import asyncio
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import aiohttp

from awec.core.canonicalizer import CrawlPolicy, FANTIConfig, FetchResult, HostProfile, URLCanonicalizer
from awec.http.compression import CompressionDecoder, process_payload
from awec.http.retries import RateLimiter, calculate_backoff, parse_retry_after
from awec.safety.policy import RobotsManager, SSRFGuard
from awec.safety.waf import WAFDetector
from awec.storage.state_store import StateStore

logger = logging.getLogger("awec.http.fetcher")

USER_AGENT_PROFILES = {
    "archive": "AWEC/3.0 (+https://github.com/ARARAT33/AWEC; Archival Crawler)",
    "desktop": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 AWEC/3.0",
}

HEADER_PROFILES = {
    "Default Archive": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hy;q=0.8,ru;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
    },
    "Browser-Compatible": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,hy;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Ch-Ua": '"Not(A:Brand";v="99", "Chromium";v="133"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1"
    }
}


class RetryAction(Enum):
    RETRY_NOW = "RETRY_NOW"
    RETRY_LATER = "RETRY_LATER"
    DO_NOT_RETRY = "DO_NOT_RETRY"
    PAUSE_HOST = "PAUSE_HOST"
    FAIL_PERMANENTLY = "FAIL_PERMANENTLY"


class RetryDecisionEngine:
    @staticmethod
    def evaluate(status: int, exception: Optional[Exception], attempt: int, max_retries: int, retry_after: Optional[float] = None) -> Tuple[RetryAction, float, str]:
        if attempt >= max_retries:
            return RetryAction.FAIL_PERMANENTLY, 0.0, f"Max retries reached ({max_retries})"

        if status in (401, 403, 404, 410, 451):
            return RetryAction.DO_NOT_RETRY, 0.0, f"Permanent HTTP error status {status}"

        if status == 429:
            delay = retry_after if retry_after is not None else calculate_backoff(attempt, base=2.0, max_delay=60.0)
            return RetryAction.RETRY_LATER, delay, f"Throttled HTTP 429 (backoff {delay:.1f}s)"

        if status in (500, 502, 503, 504) or status == 408:
            delay = retry_after if retry_after is not None else calculate_backoff(attempt, base=1.0, max_delay=30.0)
            return RetryAction.RETRY_LATER, delay, f"Transient HTTP {status} (backoff {delay:.1f}s)"

        if exception:
            err_str = str(exception).lower()
            if "ssrf" in err_str or "certificate" in err_str or "ssl" in err_str:
                return RetryAction.FAIL_PERMANENTLY, 0.0, f"Security/SSL error: {exception}"
            delay = calculate_backoff(attempt, base=1.0, max_delay=30.0)
            return RetryAction.RETRY_LATER, delay, f"Network exception: {exception}"

        if 200 <= status < 300 or status in (301, 302, 303, 304, 307, 308):
            return RetryAction.DO_NOT_RETRY, 0.0, "Success or redirect handleable"

        return RetryAction.DO_NOT_RETRY, 0.0, f"Unhandled HTTP status {status}"


class Fetcher(abc.ABC):
    @abc.abstractmethod
    async def fetch(self, url: str, parent_url: str = "", depth: int = 0, etag: str = "", last_modified: str = "") -> FetchResult:
        pass


class StandardFetcher(Fetcher):
    """MODE A - Standard, simple, transparent, honest AWEC crawler network layer."""

    def __init__(self, policy: CrawlPolicy, store: Optional[StateStore] = None):
        self.policy = policy
        self.store = store
        self.rate_limiter = RateLimiter(rate_per_sec=policy.request_rate_per_sec, concurrency_limit=policy.concurrency_per_host)
        self.robots_manager = RobotsManager(user_agent=policy.user_agent, mode=policy.robots_mode)
        self.session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.policy.request_timeout)
            connector = aiohttp.TCPConnector(ssl=self.policy.verify_ssl)
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self.session

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch(self, url: str, parent_url: str = "", depth: int = 0, etag: str = "", last_modified: str = "") -> FetchResult:
        start_ts = time.time()
        canonical_url = URLCanonicalizer.canonicalize(url)
        domain = urlparse(canonical_url).netloc.lower()

        valid, ssrf_reason = SSRFGuard.validate_url(url)
        if not valid:
            return FetchResult(
                requested_url=url, final_url=url, canonical_url=canonical_url, status=0,
                error=f"SSRF Blocked: {ssrf_reason}", network_mode="standard"
            )

        if not self.robots_manager.can_fetch(url):
            return FetchResult(
                requested_url=url, final_url=url, canonical_url=canonical_url, status=403,
                error="Robots.txt restricted", network_mode="standard"
            )

        acquired = await self.rate_limiter.acquire(domain)
        if not acquired:
            return FetchResult(
                requested_url=url, final_url=url, canonical_url=canonical_url, status=429,
                error="Host rate limit / circuit breaker active", network_mode="standard"
            )

        headers = {
            "User-Agent": self.policy.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": CompressionDecoder.get_supported_encodings(),
        }
        if parent_url:
            headers["Referer"] = parent_url
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        if self.policy.custom_headers:
            headers.update(self.policy.custom_headers)

        session = await self.get_session()
        try:
            proxy = self.policy.proxy_url if self.policy.proxy_url else None
            async with session.get(url, headers=headers, allow_redirects=True, proxy=proxy) as r:
                duration_ms = (time.time() - start_ts) * 1000
                wire_bytes = await r.read()
                final_url = str(r.url)
                resp_headers = {str(k): str(v) for k, v in r.headers.items()}
                enc_header = resp_headers.get("content-encoding", "")

                payload = process_payload(wire_bytes, enc_header)
                body_text = payload.decoded_bytes.decode(r.charset or "utf-8", errors="ignore")

                challenge, challenge_reason = WAFDetector.detect_challenge(r.status, resp_headers, body_text)

                if r.status < 400:
                    self.rate_limiter.get_circuit_breaker(domain).record_success()
                else:
                    self.rate_limiter.get_circuit_breaker(domain).record_failure()

                return FetchResult(
                    requested_url=url,
                    final_url=final_url,
                    canonical_url=URLCanonicalizer.canonicalize(final_url),
                    status=r.status,
                    request_headers=headers,
                    response_headers=resp_headers,
                    wire_bytes=payload.wire_bytes,
                    decoded_bytes=payload.decoded_bytes,
                    wire_hash=payload.sha256_wire,
                    decoded_hash=payload.sha256_decoded,
                    content_type=resp_headers.get("content-type", "").split(";")[0],
                    encoding=payload.content_encoding,
                    duration_ms=duration_ms,
                    network_mode="standard",
                    challenge_detected=challenge,
                    challenge_reason=challenge_reason
                )

        except Exception as e:
            self.rate_limiter.get_circuit_breaker(domain).record_failure()
            duration_ms = (time.time() - start_ts) * 1000
            return FetchResult(
                requested_url=url, final_url=url, canonical_url=canonical_url, status=0,
                duration_ms=duration_ms, error=str(e), network_mode="standard"
            )
        finally:
            await self.rate_limiter.release(domain)


class FANTIFetcher(Fetcher):
    """MODE B - FANTI (Flexible Adaptive Network Transport & Integrity)."""

    def __init__(self, config: FANTIConfig, store: Optional[StateStore] = None):
        self.config = config
        self.store = store
        self.robots_manager = RobotsManager(user_agent=self.get_effective_user_agent(), mode="standard")
        self.session: Optional[aiohttp.ClientSession] = None
        self.cookie_jar: Optional[aiohttp.CookieJar] = None
        self.host_states: Dict[str, HostProfile] = {}
        self.active_concurrency: Dict[str, int] = {}
        self.next_request_time: Dict[str, float] = {}
        self.lock = asyncio.Lock()

    def get_effective_user_agent(self) -> str:
        if self.config.user_agent_profile == "custom" and self.config.custom_user_agent:
            return self.config.custom_user_agent
        return USER_AGENT_PROFILES.get(self.config.user_agent_profile, USER_AGENT_PROFILES["archive"])

    def get_effective_headers(self, parent_url: str = "") -> Dict[str, str]:
        profile_headers = HEADER_PROFILES.get(self.config.header_profile, HEADER_PROFILES["Default Archive"]).copy()
        profile_headers["User-Agent"] = self.get_effective_user_agent()
        if parent_url:
            profile_headers["Referer"] = parent_url
        if self.config.custom_headers:
            profile_headers.update(self.config.custom_headers)
        return profile_headers

    def get_host_profile(self, domain: str) -> HostProfile:
        if domain not in self.host_states:
            if self.store:
                p_data = self.store.get_host_profile(domain)
                if p_data:
                    self.host_states[domain] = HostProfile(**p_data)
                    return self.host_states[domain]

            self.host_states[domain] = HostProfile(
                domain=domain,
                concurrency=self.config.initial_concurrency,
                delay=self.config.initial_delay,
                timeout=self.config.total_timeout,
                retries=self.config.max_retries,
                ua_profile=self.config.user_agent_profile
            )
        return self.host_states[domain]

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            if self.cookie_jar is None:
                self.cookie_jar = aiohttp.CookieJar()
            timeout = aiohttp.ClientTimeout(
                total=self.config.total_timeout,
                connect=self.config.connect_timeout,
                sock_read=self.config.read_timeout
            )
            connector = aiohttp.TCPConnector(
                limit=self.config.max_connections,
                limit_per_host=self.config.max_connections_per_host,
                ssl=self.config.verify_tls
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                cookie_jar=self.cookie_jar if self.config.cookie_policy != "disabled" else aiohttp.DummyCookieJar()
            )
        return self.session

    async def acquire_slot(self, domain: str) -> bool:
        async with self.lock:
            hp = self.get_host_profile(domain)
            if hp.circuit_state == "OPEN":
                if time.time() - hp.last_failure_ts >= self.config.circuit_breaker_cooldown:
                    hp.circuit_state = "HALF_OPEN"
                else:
                    return False

            active = self.active_concurrency.get(domain, 0)
            if active >= hp.concurrency:
                return False

            now = time.time()
            nxt = self.next_request_time.get(domain, 0.0)
            delay = max(0.0, nxt - now)

            # Apply pacing with jitter
            jitter = hp.delay * random.uniform(0, self.config.delay_jitter)
            self.next_request_time[domain] = max(now, nxt) + hp.delay + jitter
            self.active_concurrency[domain] = active + 1

        if delay > 0:
            await asyncio.sleep(delay)
        return True

    async def release_slot(self, domain: str) -> None:
        async with self.lock:
            active = self.active_concurrency.get(domain, 1)
            self.active_concurrency[domain] = max(0, active - 1)

    def update_telemetry(self, domain: str, status: int, duration_ms: float, is_error: bool) -> None:
        hp = self.get_host_profile(domain)
        hp.avg_latency_ms = (hp.avg_latency_ms * 0.8) + (duration_ms * 0.2)

        if is_error or status in (429, 500, 502, 503, 504):
            hp.consecutive_failures += 1
            hp.last_failure_ts = time.time()

            if self.config.adaptive_concurrency:
                hp.concurrency = max(self.config.min_concurrency, hp.concurrency - 1)
            if self.config.adaptive_pacing:
                hp.delay = min(self.config.max_delay, hp.delay * 1.5)

            if hp.consecutive_failures >= self.config.circuit_breaker_threshold:
                hp.circuit_state = "OPEN"
                hp.state = "THROTTLED" if status == 429 else "UNAVAILABLE"
        else:
            hp.consecutive_failures = 0
            if hp.circuit_state in ("OPEN", "HALF_OPEN"):
                hp.circuit_state = "CLOSED"
                hp.state = "HEALTHY"

            if self.config.adaptive_concurrency and hp.concurrency < self.config.max_concurrency:
                hp.concurrency += 1
            if self.config.adaptive_pacing and hp.delay > self.config.min_delay:
                hp.delay = max(self.config.min_delay, hp.delay * 0.9)

        if self.store:
            self.store.save_host_profile(hp.__dict__)

    async def fetch(self, url: str, parent_url: str = "", depth: int = 0, etag: str = "", last_modified: str = "") -> FetchResult:
        start_ts = time.time()
        canonical_url = URLCanonicalizer.canonicalize(url)
        domain = urlparse(canonical_url).netloc.lower()

        valid, ssrf_reason = SSRFGuard.validate_url(url)
        if not valid:
            return FetchResult(
                requested_url=url, final_url=url, canonical_url=canonical_url, status=0,
                error=f"SSRF Blocked: {ssrf_reason}", network_mode="fanti"
            )

        if not self.robots_manager.can_fetch(url):
            return FetchResult(
                requested_url=url, final_url=url, canonical_url=canonical_url, status=403,
                error="Robots.txt restricted", network_mode="fanti"
            )

        acquired = await self.acquire_slot(domain)
        if not acquired:
            return FetchResult(
                requested_url=url, final_url=url, canonical_url=canonical_url, status=429,
                error="FANTI Circuit Breaker or Host Concurrency Active", network_mode="fanti"
            )

        headers = self.get_effective_headers(parent_url)
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        session = await self.get_session()
        proxy = self.config.proxy_url if self.config.proxy_url else None

        try:
            async with session.get(url, headers=headers, allow_redirects=True, proxy=proxy) as r:
                duration_ms = (time.time() - start_ts) * 1000
                wire_bytes = await r.read()
                final_url = str(r.url)
                resp_headers = {str(k): str(v) for k, v in r.headers.items()}
                enc_header = resp_headers.get("content-encoding", "")

                payload = process_payload(wire_bytes, enc_header)
                body_text = payload.decoded_bytes.decode(r.charset or "utf-8", errors="ignore")

                challenge, challenge_reason = WAFDetector.detect_challenge(r.status, resp_headers, body_text)

                self.update_telemetry(domain, r.status, duration_ms, is_error=r.status >= 400)

                return FetchResult(
                    requested_url=url,
                    final_url=final_url,
                    canonical_url=URLCanonicalizer.canonicalize(final_url),
                    status=r.status,
                    request_headers=headers,
                    response_headers=resp_headers,
                    wire_bytes=payload.wire_bytes,
                    decoded_bytes=payload.decoded_bytes,
                    wire_hash=payload.sha256_wire,
                    decoded_hash=payload.sha256_decoded,
                    content_type=resp_headers.get("content-type", "").split(";")[0],
                    encoding=payload.content_encoding,
                    duration_ms=duration_ms,
                    host_state=self.get_host_profile(domain).state,
                    network_mode="fanti",
                    challenge_detected=challenge,
                    challenge_reason=challenge_reason
                )

        except Exception as e:
            duration_ms = (time.time() - start_ts) * 1000
            self.update_telemetry(domain, status=0, duration_ms=duration_ms, is_error=True)
            return FetchResult(
                requested_url=url, final_url=url, canonical_url=canonical_url, status=0,
                duration_ms=duration_ms, error=str(e), network_mode="fanti"
            )
        finally:
            await self.release_slot(domain)

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
