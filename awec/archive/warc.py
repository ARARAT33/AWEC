"""WARC File Generation and Archive Package Builder for AWEC."""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

from awec.core.canonicalizer import ResourceRecord


class WARCGenerator:
    def __init__(self, warc_dir: Path | str, crawl_id: str):
        self.warc_dir = Path(warc_dir)
        self.warc_dir.mkdir(parents=True, exist_ok=True)
        self.crawl_id = crawl_id
        self.warc_path = self.warc_dir / f"AWEC-{crawl_id}.warc.gz"
        self._f = open(self.warc_path, "wb")
        self.writer = WARCWriter(self._f, gzip=True)

    def write_warc_response(self, rec: ResourceRecord, wire_payload: bytes) -> Tuple[int, int]:
        offset = self._f.tell()

        http_headers = [(k, v) for k, v in rec.response_headers.items()]
        status_line = f"{rec.status} OK" if rec.status == 200 else f"{rec.status} Response"
        status_and_headers = StatusAndHeaders(status_line, http_headers, protocol="HTTP/1.1")

        warc_headers = {
            "WARC-Target-URI": rec.final_url,
            "WARC-Date": rec.downloaded_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "WARC-Record-ID": f"<urn:uuid:{rec.id}>",
            "WARC-Payload-Digest": f"sha256:{rec.sha256_wire}",
            "Content-Type": "application/http; msgtype=response"
        }

        record = self.writer.create_warc_record(
            rec.final_url,
            "response",
            payload=io.BytesIO(wire_payload),
            length=len(wire_payload),
            http_headers=status_and_headers,
            warc_headers_dict=warc_headers
        )
        self.writer.write_record(record)
        self._f.flush()

        length = self._f.tell() - offset
        return offset, length

    def close(self) -> None:
        if self._f and not self._f.closed:
            self._f.close()


class ArchivePackageBuilder:
    def __init__(self, archive_dir: Path | str, crawl_id: str, seed_url: str):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.crawl_id = crawl_id
        self.seed_url = seed_url

    def build_package(self, records: List[ResourceRecord], started_at: str, finished_at: str) -> Path:
        manifest_data = {
            "crawl_id": self.crawl_id,
            "seed": self.seed_url,
            "started_at": started_at,
            "finished_at": finished_at,
            "total_resources": len(records),
            "successful_resources": sum(1 for r in records if 200 <= r.status < 400),
            "failed_resources": sum(1 for r in records if r.status >= 400 or r.error),
            "resources": [
                {
                    "url": r.final_url,
                    "requested_url": r.requested_url,
                    "status": r.status,
                    "content_type": r.content_type,
                    "wire_size": r.wire_size,
                    "sha256_wire": r.sha256_wire,
                    "sha256_decoded": r.sha256_decoded,
                    "archive_path": r.archive_path,
                    "warc": {
                        "file": r.warc_file,
                        "offset": r.warc_offset,
                        "length": r.warc_length
                    },
                    "error": r.error
                }
                for r in records
            ]
        }

        manifest_file = self.archive_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        # Report HTML
        report_html = f"""<!DOCTYPE html>
<html>
<head><title>AWEC Crawl Report - {self.crawl_id}</title></head>
<body>
<h1>AWEC Crawl Report</h1>
<p><strong>Crawl ID:</strong> {self.crawl_id}</p>
<p><strong>Seed:</strong> {self.seed_url}</p>
<p><strong>Total Resources:</strong> {len(records)}</p>
</body>
</html>"""
        (self.archive_dir / "crawl-report.html").write_text(report_html, encoding="utf-8")

        return manifest_file
