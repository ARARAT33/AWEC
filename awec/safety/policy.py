"""Safety modules: SSRF Protection, DNS Safety, and Robots Policy Manager."""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional, List, Dict, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser


PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFGuard:
    @staticmethod
    def is_ip_private(ip_str: str) -> bool:
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in net for net in PRIVATE_NETWORKS) or ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return False

    @classmethod
    def validate_url(cls, url: str) -> Tuple[bool, str]:
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            if not host:
                return False, "INVALID_HOST"

            if cls.is_ip_private(host):
                return False, "SSRF_PRIVATE_IP"

            addr_info = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            for family, kind, proto, canonname, sockaddr in addr_info:
                ip = sockaddr[0]
                if cls.is_ip_private(ip):
                    return False, f"SSRF_PRIVATE_IP_RESOLVED_{ip}"

            return True, "OK"
        except Exception as e:
            return False, f"DNS_FAILURE_{e}"


class RobotsManager:
    def __init__(self, user_agent: str = "AWEC/3.0", mode: str = "standard"):
        self.user_agent = user_agent
        self.mode = mode.lower()  # strict, standard, permissive
        self.parsers: Dict[str, Optional[RobotFileParser]] = {}

    def parse_robots(self, origin: str, content: str) -> None:
        if self.mode == "permissive":
            self.parsers[origin] = None
            return

        rp = RobotFileParser()
        rp.parse(content.splitlines())
        self.parsers[origin] = rp

    def can_fetch(self, url: str) -> bool:
        if self.mode == "permissive":
            return True

        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        rp = self.parsers.get(origin)
        if rp is None:
            return True

        return rp.can_fetch(self.user_agent, url) or rp.can_fetch("*", url)
