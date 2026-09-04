"""AWEC portable storage layout, quota accounting, and one-time legacy migration."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable


PROTECTED_DIRS = {"config", "ia"}
DATA_DIRS = ("fallback", "temp", "crawls", "checkpoints", "logs", "cache")
SYNC_NAMES = {"sync", ".sync", "synchronization", "sync-data", "sync_data", "cloud-sync", "cloud_sync"}


def app_root() -> Path:
    """Return the directory beside the running executable when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    env = os.environ.get("AWEC_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent


def layout(root: Path | None = None) -> dict[str, Path]:
    root = Path(root or app_root()).resolve()
    out = {"root": root}
    for name in ("config", "ia", *DATA_DIRS):
        out[name] = root / name
    return out


def ensure_layout(root: Path | None = None) -> dict[str, Path]:
    paths = layout(root)
    for key in ("config", "ia", *DATA_DIRS):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def config_path(root: Path | None = None) -> Path:
    return ensure_layout(root)["config"] / "config.json"


def _is_sync(name: str) -> bool:
    return name.lower() in SYNC_NAMES or "sync" in name.lower()


def migrate_legacy(root: Path | None = None) -> list[str]:
    """Move old user-profile AWEC data into the portable root once.

    Config is kept persistent; IA-looking data goes to ia; all other non-sync
    data goes to fallback/legacy. Sync data is deliberately left untouched.
    """
    paths = ensure_layout(root)
    legacy = Path.home() / "AWEC"
    if not legacy.exists() or legacy.resolve() == paths["root"].resolve():
        return []
    marker = paths["config"] / ".legacy-migration-complete"
    if marker.exists():
        return []

    moved: list[str] = []
    legacy_backup = paths["fallback"] / "legacy"
    legacy_backup.mkdir(parents=True, exist_ok=True)

    for item in legacy.iterdir():
        if _is_sync(item.name):
            continue
        try:
            if item.name.lower() == "config.json":
                dest = paths["config"] / "config.json"
            elif item.name.lower() in {"ia", "internet_archive", "internet-archive", "archive"}:
                dest = paths["ia"] / item.name
            else:
                dest = legacy_backup / item.name
            if dest.exists():
                if item.is_dir() and dest.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                    shutil.rmtree(item)
                else:
                    shutil.copy2(item, dest)
                    item.unlink()
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(dest))
            moved.append(f"{item.name} -> {dest}")
        except (OSError, shutil.Error) as exc:
            moved.append(f"SKIPPED {item.name}: {exc}")

    marker.write_text("AWEC legacy migration completed\n", encoding="utf-8")
    return moved


def data_usage_bytes(root: Path | None = None) -> int:
    paths = ensure_layout(root)
    total = 0
    for name in DATA_DIRS:
        base = paths[name]
        for p in base.rglob("*"):
            try:
                if p.is_file():
                    total += p.stat().st_size
            except OSError:
                pass
    return total


def disk_free_bytes(root: Path | None = None) -> int:
    return shutil.disk_usage(Path(root or app_root())).free


def quota_ok(root: Path, limit_gb: float, extra_bytes: int = 0, reserve_gb: float = 1.0) -> bool:
    if limit_gb <= 0:
        return False
    limit = int(limit_gb * 1024**3)
    reserve = max(0, int(reserve_gb * 1024**3))
    return data_usage_bytes(root) + max(0, extra_bytes) <= limit and disk_free_bytes(root) - max(0, extra_bytes) >= reserve
