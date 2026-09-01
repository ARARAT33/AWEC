"""Large File Streaming Download Manager with Disk Quota Safety and Online Hashing."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple


@dataclass
class DownloadResult:
    local_path: Path
    file_size: int
    sha256: str
    sha512: str


class DiskSafetyError(Exception):
    pass


class DownloadManager:
    def __init__(self, storage_dir: Path | str, min_free_disk_bytes: int = 100 * 1024 * 1024):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.min_free_disk_bytes = min_free_disk_bytes

    def check_disk_space(self) -> None:
        usage = shutil.disk_usage(self.storage_dir)
        if usage.free < self.min_free_disk_bytes:
            raise DiskSafetyError(f"Insufficient disk space: {usage.free} bytes free < {self.min_free_disk_bytes} minimum required")

    async def save_stream(
        self,
        stream_reader,
        target_relative_path: str,
        chunk_size: int = 64 * 1024,
        max_bytes: int = -1
    ) -> DownloadResult:
        self.check_disk_space()

        target_file = self.storage_dir / target_relative_path
        target_file.parent.mkdir(parents=True, exist_ok=True)

        temp_file = tempfile.NamedTemporaryFile(delete=False, dir=target_file.parent)
        temp_path = Path(temp_file.name)

        hasher256 = hashlib.sha256()
        hasher512 = hashlib.sha512()
        total_written = 0

        try:
            while True:
                chunk = await stream_reader.read(chunk_size)
                if not chunk:
                    break

                if max_bytes > 0 and (total_written + len(chunk)) > max_bytes:
                    raise ValueError(f"Download size exceeded maximum allowed limit ({max_bytes} bytes)")

                temp_file.write(chunk)
                hasher256.update(chunk)
                hasher512.update(chunk)
                total_written += len(chunk)

            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()

            # Atomic rename
            temp_path.replace(target_file)

            return DownloadResult(
                local_path=target_file,
                file_size=total_written,
                sha256=hasher256.hexdigest(),
                sha512=hasher512.hexdigest()
            )
        except Exception:
            temp_file.close()
            if temp_path.exists():
                temp_path.unlink()
            raise
