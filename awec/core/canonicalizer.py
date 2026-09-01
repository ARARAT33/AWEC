"""AWEC Core models, policy, canonicalizer, and records."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


@dataclass
class ResourceRecord:
    id: str
    requested_url: str
    final_url: str
    canonical_url: str
    parent_url: str
    discovery_type: str = "html_link"
    status: int = 0
    headers: Dict[str, str] = field(default_factory=dict)
    request_headers: Dict[str, str] = field(default_factory=dict)
    response_headers: Dict[str, str] = field(default_factory=dict)
    content_type: str = ""
    charset: str = "utf-8"
    content_encoding: str = "identity"
    wire_size: int = 0
    decoded_size: int = 0
    sha256_wire: str = ""
    sha256_decoded: str = ""
    sha512_wire: str = ""
    sha512_decoded: str = ""
    first_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    downloaded_at: str = ""
    duration_ms: float = 0.0
    retry_count: int = 0
    error: str = ""
    archive_path: str = ""
    warc_file: str = ""
    warc_offset: int = 0
    warc_length: int = 0
    challenge_detected: bool = False
    challenge_reason: str = ""


@dataclass
class CrawlPolicy:
    user_agent: str = "AWEC/3.0 (+https://github.com/ARARAT33/AWEC; Archival Engine)"
    robots_mode: str = "standard"  # strict, standard, permissive
    max_depth: int = 8
    max_urls: int = 0
    max_bytes: int = 0
    max_duration_sec: int = 0
    max_file_size: int = -1
    concurrency_per_host: int = 4
    global_concurrency: int = 32
    request_rate_per_sec: float = 2.0
    max_retries: int = 8
    request_timeout: int = 30
    max_redirects: int = 20
    scope_mode: str = "same_origin"  # same_url, same_origin, same_site, allowlist, explicit_multi_domain
    fidelity: str = "maximum"  # maximum, standard, basic
    archive_target: str = "both"  # none, local, internet-archive, both
    strip_tracking_params: bool = False
    allowlist_domains: List[str] = field(default_factory=list)
    download_files: bool = True
    allowed_mime_types: List[str] = field(default_factory=lambda: ["*"])
    verify_ssl: bool = True
    proxy_url: str = ""
    custom_headers: Dict[str, str] = field(default_factory=dict)


class URLCanonicalizer:
    @staticmethod
    def canonicalize(url: str, strip_tracking: bool = False) -> str:
        if not url:
            return ""
        url = url.strip()
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url

        try:
            parts = urlsplit(url)
        except Exception:
            return url

        scheme = parts.scheme.lower()
        if scheme not in ("http", "https"):
            return url

        netloc = parts.netloc.lower()
        if "@" in netloc:
            auth, host_port = netloc.split("@", 1)
        else:
            auth, host_port = "", netloc

        if ":" in host_port:
            host, port = host_port.split(":", 1)
        else:
            host, port = host_port, ""

        try:
            host = host.encode("idna").decode("ascii")
        except Exception:
            pass

        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            port = ""

        new_netloc = f"{auth}@{host}" if auth else host
        if port:
            new_netloc = f"{new_netloc}:{port}"

        path = parts.path
        if not path:
            path = "/"
        else:
            trailing_slash = path.endswith("/")
            segments = path.split("/")
            resolved: List[str] = []
            for seg in segments:
                if not seg or seg == ".":
                    continue
                elif seg == "..":
                    if resolved:
                        resolved.pop()
                else:
                    resolved.append(seg)
            path = "/" + "/".join(resolved)
            if trailing_slash and not path.endswith("/"):
                path += "/"

        query = parts.query
        if query:
            q_pairs = parse_qsl(query, keep_blank_values=True)
            if strip_tracking:
                q_pairs = [(k, v) for k, v in q_pairs if k.lower() not in TRACKING_PARAMS]
            q_pairs.sort(key=lambda x: (x[0], x[1]))
            new_query = urlencode(q_pairs)
        else:
            new_query = ""

        return urlunsplit((scheme, new_netloc, path, new_query, ""))
