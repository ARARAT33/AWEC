"""AWEC storage sinks: local filesystem with zero/quota management and optional Internet Archive S3.
"""
from __future__ import annotations
import os
from pathlib import Path
import hashlib

class LocalSink:
    def __init__(self, root: str | Path, max_storage_mb: int = 50):
        self.root = Path(root)
        self.max_bytes = max_storage_mb * 1024 * 1024 if max_storage_mb >= 0 else -1

    def get_current_storage_size(self) -> int:
        if not self.root.exists():
            return 0
        total = 0
        for p in self.root.rglob('*'):
            if p.is_file():
                total += p.stat().st_size
        return total

    def enforce_quota(self):
        if self.max_bytes < 0:
            return
        if self.max_bytes == 0:
            if self.root.exists():
                for p in self.root.rglob('*'):
                    if p.is_file():
                        try:
                            p.unlink()
                        except Exception:
                            pass
            return

        files = []
        if self.root.exists():
            for p in self.root.rglob('*'):
                if p.is_file():
                    files.append((p.stat().st_mtime, p.stat().st_size, p))

        files.sort(key=lambda x: x[0])
        current_size = sum(f[1] for f in files)

        for mtime, size, p in files:
            if current_size <= self.max_bytes:
                break
            try:
                p.unlink()
                current_size -= size
            except Exception:
                pass

    def put(self, domain: str, url: str, data: bytes) -> str | None:
        if self.max_bytes == 0:
            return None

        self.enforce_quota()
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        suffix = Path(url.split('?', 1)[0]).suffix or '.bin'
        folder = self.root / domain
        folder.mkdir(parents=True, exist_ok=True)
        p = folder / (digest + suffix)
        p.write_bytes(data)
        self.enforce_quota()
        return str(p)

class InternetArchiveSink:
    def __init__(self, access_key: str, secret_key: str, endpoint_url: str, bucket: str):
        import boto3
        self.client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url or "https://s3.us.archive.org",
            region_name='us-east-1'
        )
        self.bucket = bucket

    def put(self, key: str, data: bytes, content_type: str = 'application/octet-stream') -> str:
        body_bytes = bytes(data)
        file_len = len(body_bytes)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body_bytes,
            ContentType=content_type or 'application/octet-stream'
        )
        return key
