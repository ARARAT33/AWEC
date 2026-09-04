"""Reliable Internet Archive uploader with an explicit IAS3 PUT path."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

import boto3
import requests
from internetarchive.auth import S3Auth


def generate_ia_identifier(domain: str, crawl_id: str, prefix: str = "awecrawl") -> str:
    clean_domain = re.sub(r"[^a-z0-9]", "-", domain.lower()).strip("-")
    clean_prefix = re.sub(r"[^a-z0-9]", "-", prefix.lower()).strip("-")
    return re.sub(r"-+", "-", f"{clean_prefix}-{clean_domain}-{crawl_id}".lower())[:80]


def _metadata_url(identifier: str) -> str:
    return "https://archive.org/metadata/" + urllib.parse.quote(identifier, safe="")


def _get_metadata(identifier: str) -> tuple[bool, dict | None, str]:
    try:
        req = urllib.request.Request(_metadata_url(identifier), headers={"User-Agent": "AWEC/12.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        return True, data, "FOUND"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, None, "NOT_FOUND"
        return False, None, f"HTTP_{e.code}"
    except Exception as e:
        return False, None, f"CHECK_ERROR: {e}"


class IAUploader:
    """IAS3 publisher with deterministic request length and remote verification."""
    PREFLIGHT_TTL = 60.0
    MAX_RETRIES = 8
    REQUEST_TIMEOUT = (15, 300)

    def __init__(self, access_key: str, secret_key: str, identifier: str,
                 endpoint_url: str = "https://s3.us.archive.org", collection: str = "",
                 title: str = "", creator: str = "", description: str = ""):
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
        self.identifier = identifier.strip()
        self.endpoint_url = endpoint_url.rstrip("/")
        self.collection = (collection or os.getenv("AWEC_IA_COLLECTION", "")).strip()
        self.title = (title or os.getenv("AWEC_IA_TITLE", "")).strip()
        self.creator = (creator or os.getenv("AWEC_IA_CREATOR", "")).strip()
        self.description = (description or os.getenv("AWEC_IA_DESCRIPTION", "")).strip()
        self._collection_cache: Optional[Tuple[float, bool, str]] = None
        self._item_cache: Optional[Tuple[float, bool, str]] = None

    def check_collection(self, force=False):
        if not self.collection:
            return False, "COLLECTION_NAME_REQUIRED"
        now = time.monotonic()
        if not force and self._collection_cache and now - self._collection_cache[0] < self.PREFLIGHT_TTL:
            return self._collection_cache[1], self._collection_cache[2]
        exists, meta, msg = _get_metadata(self.collection)
        if not exists:
            result = (False, f"COLLECTION_NOT_FOUND: {self.collection}" if msg == "NOT_FOUND" else f"COLLECTION_CHECK_FAILED: {msg}")
        else:
            mediatype = str((meta or {}).get("metadata", {}).get("mediatype", ""))
            result = ((False, f"NOT_A_COLLECTION: {self.collection}") if mediatype and mediatype != "collection"
                      else (True, f"COLLECTION_FOUND: {self.collection}"))
        self._collection_cache = (now, result[0], result[1])
        return result

    def check_item(self, force=False):
        if not self.identifier:
            return False, "ITEM_NAME_REQUIRED"
        now = time.monotonic()
        if not force and self._item_cache and now - self._item_cache[0] < self.PREFLIGHT_TTL:
            return self._item_cache[1], self._item_cache[2]
        exists, _, msg = _get_metadata(self.identifier)
        result = ((True, f"ITEM_FOUND: {self.identifier}") if exists else
                  (False, f"ITEM_NOT_FOUND: {self.identifier}") if msg == "NOT_FOUND" else
                  (False, f"ITEM_CHECK_FAILED: {msg}"))
        self._item_cache = (now, result[0], result[1])
        return result

    def invalidate_item_cache(self):
        self._item_cache = None

    def validate_destination(self, force=False):
        if not self.access_key or not self.secret_key:
            return False, "IA_CREDENTIALS_MISSING"
        ok, msg = self.check_collection(force)
        if not ok:
            return False, msg
        item_ok, item_msg = self.check_item(force)
        if item_ok:
            return True, f"{msg} • {item_msg}"
        if item_msg.startswith("ITEM_NOT_FOUND:"):
            return True, f"{msg} • ITEM_MISSING_WILL_BE_CREATED: {self.identifier}"
        return False, item_msg

    def _metadata(self):
        md = {"mediatype": "data", "collection": self.collection}
        if self.title:
            md["title"] = self.title
        if self.creator:
            md["creator"] = self.creator
        if self.description:
            md["description"] = self.description
        return md

    def _ia_url(self, remote_key: str) -> str:
        encoded_key = urllib.parse.quote(remote_key.lstrip("/"), safe="/-_.~")
        return f"{self.endpoint_url}/{self.identifier}/{encoded_key}"

    def _upload_once(self, local_p: Path, remote_key: str, content_type: str, md5_b64: str) -> requests.Response:
        size = local_p.stat().st_size
        headers = {
            "User-Agent": "AWEC/12.0",
            "Content-Type": content_type or "application/octet-stream",
            "Content-Length": str(size),
            "Content-MD5": md5_b64,
            "x-archive-size-hint": str(size),
            "x-archive-queue-derive": "0",
            # IAS3 requires this when the target item bucket has not yet been
            # materialized for S3 writes. It is harmless for an existing item.
            "x-amz-auto-make-bucket": "1",
            "x-archive-keep-old-version": "1",
        }
        for name, value in self._metadata().items():
            if value:
                headers[f"x-archive-meta-{name}"] = str(value)
        with local_p.open("rb") as fh:
            response = requests.put(
                self._ia_url(remote_key),
                data=fh,
                headers=headers,
                auth=S3Auth(self.access_key, self.secret_key),
                timeout=self.REQUEST_TIMEOUT,
            )
        response.raise_for_status()
        return response

    def upload_file_s3(self, local_path: Path | str, remote_key: str,
                       content_type="application/octet-stream", metadata_headers=None):
        local_p = Path(local_path)
        if not local_p.exists():
            return False, "LOCAL_FILE_NOT_FOUND"
        if not local_p.is_file():
            return False, "LOCAL_PATH_NOT_A_FILE"
        ok, msg = self.validate_destination()
        if not ok:
            return False, msg
        try:
            size = local_p.stat().st_size
            md5 = hashlib.md5(usedforsecurity=False)
            with local_p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    md5.update(chunk)
            md5_b64 = base64.b64encode(md5.digest()).decode("ascii")
            if metadata_headers and metadata_headers.get("Content-Type"):
                content_type = metadata_headers["Content-Type"]

            last_error = None
            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    self._upload_once(local_p, remote_key, content_type, md5_b64)
                    self._item_cache = (time.monotonic(), True, f"ITEM_FOUND: {self.identifier}")
                    return True, f"ITEM_EXISTS/CREATED: {self.identifier} • UPLOAD_SUCCESS • {size} bytes"
                except requests.HTTPError as exc:
                    last_error = exc
                    response = exc.response
                    if response is None or response.status_code != 503 or attempt >= self.MAX_RETRIES:
                        raise
                except (requests.ConnectionError, requests.Timeout) as exc:
                    last_error = exc
                    if attempt >= self.MAX_RETRIES:
                        raise
                time.sleep(min(30, 2 ** min(attempt, 4)))
            if last_error:
                raise last_error
            return False, "IA_UPLOAD_FAILED"
        except Exception as e:
            err = str(e)
            if "411" in err or "Length Required" in err:
                return False, "IA_411_LENGTH_REQUIRED"
            return False, f"IA_UPLOAD_ERROR_{err}"

    def _client(self):
        return boto3.client("s3", endpoint_url=self.endpoint_url,
                            aws_access_key_id=self.access_key,
                            aws_secret_access_key=self.secret_key,
                            region_name="us-east-1")

    def verify_remote_object(self, remote_key, expected_size, retries=5):
        for attempt in range(max(1, retries)):
            try:
                size = self._client().head_object(Bucket=self.identifier, Key=remote_key).get("ContentLength")
                if size == expected_size:
                    return True
            except Exception:
                pass
            if attempt + 1 < retries:
                time.sleep(0.8 * (attempt + 1))
        return False


class SpoolPublisher:
    def __init__(self, uploader, store):
        self.uploader, self.store = uploader, store

    def process_pending_uploads(self):
        stats = {"success": 0, "failed": 0, "skipped": 0}
        for item in self.store.get_pending_uploads():
            p = Path(item["local_path"])
            if not p.exists():
                self.store.update_upload_spool_status(item["id"], "failed", "Local spool file missing")
                stats["failed"] += 1
                continue
            self.store.update_upload_spool_status(item["id"], "uploading")
            ok, msg = self.uploader.upload_file_s3(p, item["remote_key"])
            if ok:
                try:
                    expected_size = p.stat().st_size
                except OSError as exc:
                    self.store.update_upload_spool_status(item["id"], "failed", f"Local file stat failed before verification: {exc}")
                    stats["failed"] += 1
                    continue
                if self.uploader.verify_remote_object(item["remote_key"], expected_size):
                    try:
                        p.unlink()
                    except OSError as exc:
                        self.store.update_upload_spool_status(item["id"], "failed", f"IA verified but local delete failed: {exc}")
                        stats["failed"] += 1
                        continue
                    self.store.update_upload_spool_status(item["id"], "verified")
                    stats["success"] += 1
                    continue
            self.store.update_upload_spool_status(item["id"], "failed", msg)
            stats["failed"] += 1
        return stats
