"""AWEC Desktop v11 — modern command center.

v11 keeps the v10 custom-language/naming system and adds whole-program runtime
localization, mirror telemetry, quick actions, and a more polished command-center
surface. The crawler remains an archival client and does not bypass authentication,
CAPTCHA, paywalls, or other access controls.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QFrame, QHBoxLayout, QPushButton, QVBoxLayout

from desktop.app_window_v10 import AWECMainWindow as V10MainWindow
from desktop.runtime_i18n import apply_to_widget_tree, translate_value


class AWECMainWindow(V10MainWindow):
    """AWEC v11 command center."""

    def __init__(self):
        super().__init__()
        self.v10_language.currentIndexChanged.connect(self._translate_program)
        self._translate_program()
        self.setWindowTitle("AWEC Desktop — High-Speed Web Archive Engine")

    def _dashboard(self):
        super()._dashboard()
        page = self.pages.widget(0)
        if not page or not page.layout():
            return
        hero = QFrame()
        hero.setObjectName("v11Hero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(20, 18, 20, 18)
        title = QLabel("AWEC 11 • ARCHIVE COMMAND CENTER")
        title.setObjectName("v11HeroTitle")
        subtitle = QLabel("Mirror the complete reachable site resource graph • WARC + local files • adaptive FANTI transport")
        subtitle.setObjectName("v11HeroSubtitle")
        hl.addWidget(title)
        hl.addWidget(subtitle)
        page.layout().insertWidget(0, hero)

        row = QHBoxLayout()
        self.v11_mirror_card = QLabel("Mirror: ready")
        self.v11_mirror_card.setObjectName("v11Card")
        self.v11_archive_card = QLabel("Archive: WARC + local mirror")
        self.v11_archive_card.setObjectName("v11Card")
        self.v11_network_card = QLabel("Network: adaptive FANTI / standard")
        self.v11_network_card.setObjectName("v11Card")
        for card in (self.v11_mirror_card, self.v11_archive_card, self.v11_network_card):
            row.addWidget(card, 1)
        page.layout().insertLayout(1, row)

        actions = QHBoxLayout()
        open_btn = QPushButton("📂 Open Crawl Storage")
        open_btn.clicked.connect(self._open_storage)
        reset_btn = QPushButton("↻ Reset View")
        reset_btn.clicked.connect(self._translate_program)
        actions.addWidget(open_btn)
        actions.addWidget(reset_btn)
        actions.addStretch()
        page.layout().insertLayout(4, actions)

    def _translate_program(self):
        """Switch the whole visible application to the selected language."""
        if not hasattr(self, "v10_language"):
            return
        lang = str(self.v10_language.currentData() or "en")
        overrides = getattr(self, "_name_overrides", {}).get(lang, {})
        # Use immutable English originals so switching HY -> RU -> FR never loses the source key.
        for key, widget in getattr(self, "_name_widgets", {}).items():
            original = getattr(self, "_original_text", {}).get(key, "")
            if not original:
                continue
            value = overrides.get(key, translate_value(original, lang))
            try:
                if hasattr(widget, "setText"):
                    widget.setText(value)
                elif hasattr(widget, "setPlaceholderText"):
                    widget.setPlaceholderText(value)
            except Exception:
                pass
        # Cover group boxes, tabs, and labels that were not in the v10 index.
        try:
            apply_to_widget_tree(self.centralWidget(), lang, overrides)
        except Exception:
            pass
        if hasattr(self, "language_status"):
            count = len(overrides)
            self.language_status.setText(f"✓ Program language: {lang} • {count} custom UI names active")

    def _stats(self, s):
        super()._stats(s)
        if hasattr(self, "v11_mirror_card"):
            mirrored = int(s.get("mirrored", 0))
            mirror_bytes = int(s.get("mirror_bytes", 0))
            self.v11_mirror_card.setText(f"Mirror: {mirrored:,} resources • {self._fmt_bytes(mirror_bytes)}")
        if hasattr(self, "v11_network_card"):
            self.v11_network_card.setText(f"Network: {s.get('status', 'ready')} • FANTI adaptive transport available")

    @staticmethod
    def _fmt_bytes(n: int) -> str:
        value = float(max(0, n))
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{n} B"

    def _open_storage(self):
        path = Path.home() / "AWEC"
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self._log(f"Could not open storage: {exc}")
