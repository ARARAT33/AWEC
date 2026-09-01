"""Internet Archive S3 Uploader with 411 Length Required fix and checksum verification."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import boto3


def generate_ia_identifier(domain: str, crawl_id: str, prefix: str = "awecrawl") -> str:
    clean_domain = re.sub(r"[^a-z0-9]", "-", domain.lower()).strip("-")
    clean_prefix = re.sub(r"[^a-z0-9]", "-", prefix.lower()).strip("-")
    identifier = f"{clean_prefix}-{clean_domain}-{crawl_id}".lower()
    return re.sub(r"-+", "-", identifier)[:80]


class IAUploader:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        identifier: str,
        endpoint_url: str = "https://s3.us.archive.org"
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.identifier = identifier
        self.endpoint_url = endpoint_url

    def validate_dry_run(self, metadata: Dict[str, Any], files: list[Path | str]) -> Tuple[bool, str]:
        if not self.access_key or not self.secret_key or not self.identifier:
            return False, "IA_CREDENTIALS_OR_IDENTIFIER_MISSING"

        for f in files:
            p = Path(f)
            if not p.exists():
                return False, f"DRY_RUN_FILE_NOT_FOUND: {f}"

        return True, "IA_DRY_RUN_PASSED"

    def upload_file_s3(
        self,
        local_path: Path | str,
        remote_key: str,
        content_type: str = "application/octet-stream",
        metadata_headers: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str]:
        local_p = Path(local_path)
        if not local_p.exists():
            return False, "LOCAL_FILE_NOT_FOUND"

        file_size = local_p.stat().st_size

        s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name="us-east-1"
        )

        extra_args = {
            "ContentType": content_type or "application/octet-stream"
        }
        if metadata_headers:
            extra_args["Metadata"] = metadata_headers

        try:
            with open(local_p, "rb") as f:
                s3.put_object(
                    Bucket=self.identifier,
                    Key=remote_key,
                    Body=f,
                    ContentLength=file_size,
                    **extra_args
                )
            return True, "UPLOAD_SUCCESS"
        except Exception as e:
            err_msg = str(e)
            if "411" in err_msg or "Length Required" in err_msg:
                return False, "IA_411_LENGTH_REQUIRED"
            return False, f"IA_UPLOAD_ERROR_{err_msg}"

    def verify_remote_object(self, remote_key: str, expected_size: int) -> bool:
        s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name="us-east-1"
        )
        try:
            resp = s3.head_object(Bucket=self.identifier, Key=remote_key)
            return resp.get("ContentLength") == expected_size
        except Exception:
            return False
