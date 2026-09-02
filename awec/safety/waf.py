"""WAF, CAPTCHA, and Security Challenge Detection Module for AWEC."""
from __future__ import annotations

import re
from typing import Dict, Tuple


CHALLENGE_SIGNALS = [
    # Cloudflare
    (re.compile(r"cf-browser-verification|cf_challenge|cf-turnstile|cf-cloudflare", re.I), "Cloudflare Challenge Page"),
    (re.compile(r"just a moment\.\.\.|attention required! \| cloudflare", re.I), "Cloudflare JS Challenge"),
    (re.compile(r"challenges\.cloudflare\.com/turnstile", re.I), "Cloudflare Turnstile"),
    # Datadome / PerimeterX / Kasada / AWS WAF / SuCuri / Akamai / Imperva
    (re.compile(r"datadome", re.I), "DataDome Bot Detection"),
    (re.compile(r"_pxhd|perimeterx|human security", re.I), "PerimeterX/HUMAN Security Barrier"),
    (re.compile(r"kpsdk|kasada", re.I), "Kasada Bot Mitigation"),
    (re.compile(r"aws-waf|awswaf", re.I), "AWS WAF Challenge"),
    (re.compile(r"sucuri_cloudproxy|sucuri", re.I), "SuCuri Firewall Challenge"),
    (re.compile(r"access denied|request blocked|incapsula|imperva|akamai_bot_manager", re.I), "WAF Access Denied"),
    # Generic CAPTCHA & Bot Check
    (re.compile(r"g-recaptcha|hcaptcha|fun-captcha|captcha-container|geetest", re.I), "CAPTCHA Barrier"),
    (re.compile(r"verify you are human|pardon our interruption|security check|are you a robot", re.I), "Human Verification Barrier")
]


class WAFDetector:
    @staticmethod
    def detect_challenge(status: int, headers: Dict[str, str], body_text: str) -> Tuple[bool, str]:
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}

        # Cloudflare server header + blocked status
        if headers_lower.get("server") in ("cloudflare", "cloudflare-nginx"):
            if status in (403, 429, 503):
                for pattern, reason in CHALLENGE_SIGNALS:
                    if pattern.search(body_text):
                        return True, reason
                return True, f"Cloudflare WAF Response (HTTP {status})"

        # Datadome cookie or header
        if "datadome" in headers_lower.get("set-cookie", "") or "x-datadome" in headers_lower:
            return True, "DataDome Anti-Bot Challenge"

        # PerimeterX / Imperva / Akamai headers
        if "x-px" in headers_lower or "x-px-authorization" in headers_lower:
            return True, "PerimeterX Protection"
        if "x-cdn" in headers_lower and "incapsula" in headers_lower.get("x-cdn", ""):
            return True, "Imperva/Incapsula WAF"
        if "x-akamai-transformed" in headers_lower and status in (403, 429):
            return True, "Akamai Bot Manager Challenge"

        # Check body markup signals
        for pattern, reason in CHALLENGE_SIGNALS:
            if pattern.search(body_text):
                return True, reason

        if status == 403:
            return True, "HTTP 403 Forbidden Access Control"
        if status == 429:
            return True, "HTTP 429 Too Many Requests Rate Limit"

        return False, ""
