"""Internet Archive S3 uploader with destination preflight and item creation flow."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import boto3


def generate_ia_identifier(domain: str, crawl_id: str, prefix: str = "awecrawl") -> str:
    clean_domain = re.sub(r"[^a-z0-9]", "-", domain.lower()).strip("-")
    clean_prefix = re.sub(r"[^a-z0-9]", "-", prefix.lower()).strip("-")
    identifier = f"{clean_prefix}-{clean_domain}-{crawl_id}".lower()
    return re.sub(r"-+", "-", identifier)[:80]


def _metadata_url(identifier: str) -> str:
    return "https://archive.org/metadata/" + urllib.parse.quote(identifier, safe="")


def _get_metadata(identifier: str) -> tuple[bool, dict | None, str]:
    try:
        with urllib.request.urlopen(_metadata_url(identifier), timeout=12) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        return True, data, "FOUND"
    except urllib.error.HTTPError as e:
        if e.code == 404: return False, None, "NOT_FOUND"
        return False, None, f"HTTP_{e.code}"
    except Exception as e:
        return False, None, f"CHECK_ERROR: {e}"


class IAUploader:
    def __init__(self, access_key: str, secret_key: str, identifier: str,
                 endpoint_url: str = "https://s3.us.archive.org", collection: str = "",
                 title: str = "", creator: str = "", description: str = ""):
        self.access_key = access_key
        self.secret_key = secret_key
        self.identifier = identifier.strip()
        self.endpoint_url = endpoint_url.rstrip("/")
        self.collection = (collection or os.getenv("AWEC_IA_COLLECTION", "")).strip()
        self.title = (title or os.getenv("AWEC_IA_TITLE", "")).strip()
        self.creator = (creator or os.getenv("AWEC_IA_CREATOR", "")).strip()
        self.description = (description or os.getenv("AWEC_IA_DESCRIPTION", "")).strip()

    def check_collection(self) -> Tuple[bool, str]:
        if not self.collection: return False, "COLLECTION_NAME_REQUIRED"
        exists, meta, msg = _get_metadata(self.collection)
        if not exists:
            if msg == "NOT_FOUND": return False, f"COLLECTION_NOT_FOUND: {self.collection}"
            return False, f"COLLECTION_CHECK_FAILED: {msg}"
        mediatype = str((meta or {}).get("metadata", {}).get("mediatype", ""))
        if mediatype and mediatype != "collection": return False, f"NOT_A_COLLECTION: {self.collection}"
        return True, f"COLLECTION_FOUND: {self.collection}"

    def check_item(self) -> Tuple[bool, str]:
        if not self.identifier: return False, "ITEM_NAME_REQUIRED"
        exists, _, msg = _get_metadata(self.identifier)
        if exists: return True, f"ITEM_FOUND: {self.identifier}"
        if msg == "NOT_FOUND": return False, f"ITEM_NOT_FOUND: {self.identifier}"
        return False, f"ITEM_CHECK_FAILED: {msg}"

    def validate_destination(self) -> Tuple[bool, str]:
        if not self.access_key or not self.secret_key: return False, "IA_CREDENTIALS_MISSING"
        ok, msg = self.check_collection()
        if not ok: return False, msg
        item_ok, item_msg = self.check_item()
        if item_ok: return True, f"{msg} • {item_msg}"
        if item_msg.startswith("ITEM_NOT_FOUND:"): return True, f"{msg} • ITEM_MISSING_WILL_BE_CREATED: {self.identifier}"
        return False, item_msg

    def validate_dry_run(self, metadata: Dict[str, Any], files: list[Path | str]) -> Tuple[bool, str]:
        ok, msg = self.validate_destination()
        if not ok: return False, msg
        for f in files:
            if not Path(f).exists(): return False, f"DRY_RUN_FILE_NOT_FOUND: {f}"
        return True, "IA_DRY_RUN_PASSED"

    def _client(self):
        return boto3.client("s3", endpoint_url=self.endpoint_url, aws_access_key_id=self.access_key,
                            aws_secret_access_key=self.secret_key, region_name="us-east-1")

    def upload_file_s3(self, local_path: Path | str, remote_key: str,
                       content_type: str = "application/octet-stream",
                       metadata_headers: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
        local_p = Path(local_path)
        if not local_p.exists(): return False, "LOCAL_FILE_NOT_FOUND"
        if not self.collection: return False, "COLLECTION_NAME_REQUIRED"
        collection_ok, collection_msg = self.check_collection()
        if not collection_ok: return False, collection_msg
        item_exists, item_msg = self.check_item()
        if not item_exists and not item_msg.startswith("ITEM_NOT_FOUND:"): return False, item_msg

        extra_args: Dict[str, Any] = {"ContentType": content_type or "application/octet-stream"}
        meta = dict(metadata_headers or {})
        meta.setdefault("collection", self.collection)
        if self.title: meta.setdefault("title", self.title)
        if self.creator: meta.setdefault("creator", self.creator)
        if self.description: meta.setdefault("description", self.description)
        extra_args["Metadata"] = meta
        try:
            status = f"ITEM_EXISTS: {self.identifier}" if item_exists else f"ITEM_CREATED: {self.identifier}"
            with local_p.open("rb") as f:
                self._client().put_object(Bucket=self.identifier, Key=remote_key, Body=f,
                                          ContentLength=local_p.stat().st_size, **extra_args)
            return True, status + " • UPLOAD_SUCCESS"
        except Exception as e:
            err = str(e)
            if "411" in err or "Length Required" in err: return False, "IA_411_LENGTH_REQUIRED"
            return False, f"IA_UPLOAD_ERROR_{err}"

    def verify_remote_object(self, remote_key: str, expected_size: int) -> bool:
        try:
            return self._client().head_object(Bucket=self.identifier, Key=remote_key).get("ContentLength") == expected_size
        except Exception:
            return False


class SpoolPublisher:
    """Manages upload spooling and background retry worker for IA / S3 publishing."""
    def __init__(self, uploader: IAUploader, store: Any): self.uploader, self.store = uploader, store
    def process_pending_uploads(self) -> Dict[str, int]:
        stats = {"success": 0, "failed": 0, "skipped": 0}
        for item in self.store.get_pending_uploads():
            p = Path(item["local_path"])
            if not p.exists():
                self.store.update_upload_spool_status(item["id"], "failed", "Local spool file missing"); stats["failed"] += 1; continue
            self.store.update_upload_spool_status(item["id"], "uploading")
            ok, msg = self.uploader.upload_file_s3(p, item["remote_key"])
            if ok and self.uploader.verify_remote_object(item["remote_key"], p.stat().st_size):
                self.store.update_upload_spool_status(item["id"], "verified"); stats["success"] += 1
            else:
                self.store.update_upload_spool_status(item["id"], "failed", msg); stats["failed"] += 1
        return stats
