"""First-run safety gate and OS-specific preflight for AWEC."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QDoubleSpinBox, QVBoxLayout

from storage_layout import app_root, ensure_layout, migrate_legacy, disk_free_bytes

SAFETY_VERSION = 1


def platform_name() -> str:
    if sys.platform.startswith("win"):
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("linux"):
        return "Linux"
    return platform.system() or "Unknown OS"


def platform_rules() -> list[str]:
    os_name = platform_name()
    if os_name == "Windows":
        return [
            "AWEC data must be in a writable folder outside system-protected directories.",
            "TLS certificate verification stays enabled.",
            "Respect robots.txt is enabled by default.",
            "A storage quota and free-space reserve are mandatory.",
        ]
    if os_name == "macOS":
        return [
            "AWEC data must be in a writable folder; macOS may require Files & Folders permission.",
            "TLS certificate verification stays enabled.",
            "Respect robots.txt is enabled by default.",
            "A storage quota and free-space reserve are mandatory.",
        ]
    if os_name == "Linux":
        return [
            "AWEC data must be in a writable folder owned by the current user.",
            "TLS certificate verification stays enabled.",
            "Respect robots.txt is enabled by default.",
            "A storage quota and free-space reserve are mandatory.",
        ]
    return ["AWEC will use conservative TLS, robots, quota, and writable-path checks."]


def preflight(root: Path, max_gb: float, reserve_gb: float) -> tuple[bool, str]:
    root = Path(root).resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".awec-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return False, f"AWEC storage folder is not writable: {exc}"
    if max_gb <= 0:
        return False, "Storage limit must be greater than 0 GB."
    if reserve_gb < 0:
        return False, "Free-space reserve cannot be negative."
    if disk_free_bytes(root) <= reserve_gb * 1024**3:
        return False, f"Not enough free disk space for the configured {reserve_gb:g} GB reserve."
    if platform_name() == "Windows" and str(root).lower().startswith(str(Path(os.environ.get("WINDIR", r"C:\Windows"))).lower()):
        return False, "Do not use the Windows system directory for AWEC data."
    return True, "Safety checks passed."


class SafetySetupDialog(QDialog):
    """Blocking first-run setup: the user must explicitly accept safe defaults."""
    def __init__(self, root: Path, current_gb: float = 10.0, reserve_gb: float = 1.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AWEC • Required Safety Setup")
        self.setMinimumWidth(620)
        self.root = Path(root)
        l = QVBoxLayout(self)
        title = QLabel("🛡️ AWEC Safety Setup is required before crawling")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        l.addWidget(title)
        info = QLabel(f"Platform: {platform_name()}\nStorage root: {self.root}\n\n" + "\n".join("• " + x for x in platform_rules()))
        info.setWordWrap(True); l.addWidget(info)

        form = QFormLayout()
        self.limit = QDoubleSpinBox(); self.limit.setRange(0.1, 1048576); self.limit.setDecimals(2); self.limit.setValue(current_gb); self.limit.setSuffix(" GB")
        self.reserve = QDoubleSpinBox(); self.reserve.setRange(0, 1048576); self.reserve.setDecimals(2); self.reserve.setValue(reserve_gb); self.reserve.setSuffix(" GB")
        form.addRow("Maximum AWEC data", self.limit)
        form.addRow("Minimum free disk reserve", self.reserve)
        l.addLayout(form)
        self.accepted = QCheckBox("I understand and accept these storage/network safety settings.")
        l.addWidget(self.accepted)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject); l.addWidget(buttons)

    def _accept(self):
        if not self.accepted.isChecked():
            QMessageBox.warning(self, "AWEC Safety Setup", "You must accept the safety settings before continuing.")
            return
        ok, msg = preflight(self.root, self.limit.value(), self.reserve.value())
        if not ok:
            QMessageBox.critical(self, "AWEC Safety Setup", msg)
            return
        self.done(QDialog.DialogCode.Accepted)

    def values(self) -> tuple[float, float]:
        return self.limit.value(), self.reserve.value()


def initialize_storage(root: Path) -> list[str]:
    ensure_layout(root)
    return migrate_legacy(root)
