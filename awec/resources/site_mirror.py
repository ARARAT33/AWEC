"""Complete same-origin site mirroring helpers for AWEC.

The mirror stores every successfully fetched response as a real local file while
preserving URL-derived paths. It is intentionally an archival downloader: it
never attempts to defeat authentication, CAPTCHA, paywalls, or access controls.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from awec.discovery.parsers import ContentExtractor


class SiteMirror:
    """Map fetched web resources to deterministic local files."""

    def __init__(self, root: str | Path, max_path_length: int = 220):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_path_length = max_path_length
        self.manifest: dict[str, dict] = {}

    @staticmethod
    def _safe_segment(value: str) -> str:
        value = unquote(value or "").strip()
        value = re.sub(r"[<>:\"|?*\x00-\x1f]", "_", value)
        return value or "_"

    def local_path(self, url: str, content_type: str = "") -> Path:
        p = urlparse(url)
        host = self._safe_segment(p.netloc.lower())
        raw = p.path or "/index.html"
        segments = [self._safe_segment(x) for x in raw.split("/") if x]
        if not segments:
            segments = ["index.html"]
        filename = segments[-1]
        if "." not in filename and "html" in content_type.lower():
            filename += ".html"
        if p.query:
            digest = hashlib.sha256(p.query.encode("utf-8")).hexdigest()[:12]
            stem, dot, ext = filename.rpartition(".")
            filename = f"{stem or filename}__q_{digest}{('.' + ext) if dot else ''}"
        segments[-1] = filename
        target = self.root / host / Path(*segments)
        if len(str(target)) > self.max_path_length:
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            target = self.root / host / "_long" / f"{digest}.bin"
        return target

    def save(self, url: str, payload: bytes, content_type: str = "", status: int = 200, headers: dict | None = None) -> Path:
        target = self.local_path(url, content_type)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(payload)
        tmp.replace(target)
        self.manifest[url] = {
            "url": url,
            "path": str(target.relative_to(self.root)),
            "status": status,
            "content_type": content_type,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "headers": headers or {},
        }
        return target

    def discover(self, url: str, payload: bytes, content_type: str) -> list[tuple[str, str, str]]:
        """Discover first-class HTML/CSS/JS resources from a fetched response."""
        text = payload.decode("utf-8", errors="ignore")
        ct = content_type.lower()
        if "html" in ct:
            return ContentExtractor.extract_html_links(url, text)
        if "css" in ct:
            return ContentExtractor.extract_css_links(url, text)
        if "javascript" in ct or "ecmascript" in ct:
            return ContentExtractor.extract_js_links(url, text)
        return []

    def write_manifest(self) -> Path:
        import json
        out = self.root / "_awec_manifest.json"
        out.write_text(json.dumps({"resources": list(self.manifest.values())}, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
