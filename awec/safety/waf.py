"""WAF, CAPTCHA, and Security Challenge Detection Module for AWEC."""
from __future__ import annotations

import re
from typing import Dict, Tuple


CHALLENGE_SIGNALS = [
    # Cloudflare
    (re.compile(r"cf-browser-verification|cf_challenge|cf-turnstile|cf-cloudflare", re.I), "Cloudflare Challenge Page"),
    (re.compile(r"just a moment\.\.\.|attention required! \| cloudflare", re.I), "Cloudflare JS Challenge"),
    # Turnstile
    (re.compile(r"challenges\.cloudflare\.com/turnstile", re.I), "Cloudflare Turnstile"),
    # Akamai / Imperva / WAFs
    (re.compile(r"access denied|request blocked|incapsula|imperva|akamai_bot_manager", re.I), "WAF Access Denied"),
    # Generic CAPTCHA
    (re.compile(r"g-recaptcha|hcaptcha|fun-captcha|captcha-container", re.I), "CAPTCHA Barrier"),
    # Bot / Human Verification
    (re.compile(r"verify you are human|pardon our interruption|security check", re.I), "Human Verification Barrier")
]


class WAFDetector:
    @staticmethod
    def detect_challenge(status: int, headers: Dict[str, str], body_text: str) -> Tuple[bool, str]:
        # Check HTTP status signals
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}

        # Check Cloudflare Server header + 403/503
        if headers_lower.get("server") in ("cloudflare", "cloudflare-nginx"):
            if status in (403, 503, 429):
                for pattern, reason in CHALLENGE_SIGNALS:
                    if pattern.search(body_text):
                        return True, reason
                return True, f"Cloudflare WAF Response (HTTP {status})"

        # Check explicit server / WAF headers
        if "x-cdn" in headers_lower and "incapsula" in headers_lower.get("x-cdn", ""):
            return True, "Imperva/Incapsula WAF"

        # Check body markup signals
        for pattern, reason in CHALLENGE_SIGNALS:
            if pattern.search(body_text):
                return True, reason

        if status == 403:
            return True, "HTTP 403 Forbidden Access Control"

        return False, ""
