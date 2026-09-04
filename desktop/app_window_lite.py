"""AWEC Lite desktop UI with the full lightweight navigation and language studio."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from desktop.app_window_v5 import AWECMainWindow as V5MainWindow
from desktop.i18n import LANGUAGES, get_translation, load_language_pack
from desktop.language_editor import load_language, save_language


class AWECMainWindow(V5MainWindow):
    """Fast desktop shell; advanced functionality stays available without the old UI chain."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AWEC • Web Archive Engine")
        self.setMinimumSize(900, 620)
        self.resize(1120, 720)
        self._language_code = "en"
        self._language_values = get_translation("en")
        self._language_keys = []
        self._rewrite_sidebar()
        self._build_language_page()
        self._build_storage_page()
        self._page("dashboard")

    def _rewrite_sidebar(self):
        side = self.findChild(QWidget, "sidebar")
        if side is None:
            return
        layout = side.layout()
        if layout is None:
            return
        status = getattr(self, "status", None)
        for button in list(getattr(self, "nav", {}).values()):
            layout.removeWidget(button)
            button.deleteLater()
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not status:
                widget.deleteLater()
            elif item.layout() is not None:
                child_layout = item.layout()
                while child_layout.count():
                    child = child_layout.takeAt(0)
                    if child.widget() is not None:
                        child.widget().deleteLater()
        side.setFixedWidth(190)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(5)
        brand = QLabel("AWEC"); brand.setObjectName("brandTitle"); layout.addWidget(brand)
        subtitle = QLabel("Web Archive Engine"); subtitle.setObjectName("brandSubtitle"); layout.addWidget(subtitle)
        section = QLabel("WORKSPACE"); section.setObjectName("menuSection"); layout.addWidget(section)
        self.nav = {}
        group = QButtonGroup(self); group.setExclusive(True)
        # Keep the existing menu order and labels unchanged.
        items = (
            ("dashboard", "⌂  Dashboard"),
            ("sites", "◎  Seed Sites"),
            ("crawler", "↯  Crawler"),
            ("storage", "▣  Storage & S3"),
            ("ia", "☁  Internet Archive"),
            ("languages", "文  Languages"),
            ("logs", "≡  Live Logs"),
        )
        for key, text in items:
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True); button.setAutoDefault(False)
            button.setMinimumHeight(34); button.setMaximumHeight(38)
            button.clicked.connect(lambda checked=False, k=key: self._page(k))
            group.addButton(button); self.nav[key] = button; layout.addWidget(button)
        layout.addStretch(1)
        if status is not None:
            layout.addWidget(status)

    def _build_storage_page(self):
        p = QWidget(); self.storage_page = p
        l = QVBoxLayout(p); l.setContentsMargins(24, 22, 24, 22); l.setSpacing(12)
        l.addWidget(QLabel("Storage & S3", objectName="pageHeader"))
        l.addWidget(QLabel("Lightweight local storage policy and destination overview.", objectName="pageSubtitle"))
        box = QGroupBox("Local Storage")
        f = QFormLayout(box)
        self.storage_path = QLineEdit(str(Path.home() / "AWEC")); self.storage_path.setReadOnly(True)
        f.addRow("AWEC data directory", self.storage_path)
        self.storage_limit = QSpinBox(); self.storage_limit.setRange(0, 2147483647); self.storage_limit.setValue(50)
        self.storage_limit.setSuffix(" MB")
        f.addRow("Local cache limit", self.storage_limit)
        l.addWidget(box)
        hint = QLabel("Uploads are sent to Internet Archive when enabled; local files can be purged after successful verification.")
        hint.setWordWrap(True); l.addWidget(hint)
        l.addStretch(1); self.pages.addWidget(p)

    def _build_language_page(self):
        p = QWidget(); self.language_page = p
        l = QVBoxLayout(p); l.setContentsMargins(24, 22, 24, 22); l.setSpacing(10)
        l.addWidget(QLabel("Languages & Custom Language Studio", objectName="pageHeader"))
        l.addWidget(QLabel("Built-in languages plus editable .awec.language packs. Changes apply without restarting the crawler.", objectName="pageSubtitle"))

        top = QHBoxLayout()
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items(): self.language_combo.addItem(f"{name} ({code})", code)
        self.language_combo.currentIndexChanged.connect(self._language_selected)
        top.addWidget(QLabel("Language")); top.addWidget(self.language_combo, 1)
        imp = QPushButton("Import .awec.language"); imp.clicked.connect(self._import_language); top.addWidget(imp)
        exp = QPushButton("Export .awec.language"); exp.clicked.connect(self._export_language); top.addWidget(exp)
        l.addLayout(top)

        row = QHBoxLayout()
        self.language_filter = QLineEdit(); self.language_filter.setPlaceholderText("Search UI keys or translated text…")
        self.language_filter.textChanged.connect(self._filter_language_table); row.addWidget(self.language_filter, 1)
        apply_btn = QPushButton("✓ Apply Language"); apply_btn.setObjectName("primaryButton"); apply_btn.clicked.connect(self._apply_language); row.addWidget(apply_btn)
        save_btn = QPushButton("💾 Save Custom Pack"); save_btn.clicked.connect(self._save_custom_language); row.addWidget(save_btn)
        l.addLayout(row)

        self.language_table = QTableWidget(0, 2)
        self.language_table.setHorizontalHeaderLabels(["UI Key", "Value"])
        self.language_table.setAlternatingRowColors(True)
        self.language_table.horizontalHeader().setStretchLastSection(True)
        self.language_table.cellChanged.connect(self._language_cell_changed)
        l.addWidget(self.language_table, 1)
        self.language_status = QLabel("10 built-in languages • custom .awec.language supported")
        l.addWidget(self.language_status)
        self.pages.addWidget(p)
        self._populate_language_table()

    def _language_selected(self, _index):
        code = self.language_combo.currentData()
        if not code: return
        self._language_code = code
        self._language_values = get_translation(code)
        self._populate_language_table()

    def _populate_language_table(self):
        if not hasattr(self, "language_table"): return
        self.language_table.blockSignals(True)
        self.language_table.setRowCount(0)
        self._language_keys = sorted(self._language_values)
        for key in self._language_keys:
            r = self.language_table.rowCount(); self.language_table.insertRow(r)
            self.language_table.setItem(r, 0, QTableWidgetItem(key))
            self.language_table.setItem(r, 1, QTableWidgetItem(str(self._language_values.get(key, ""))))
        self.language_table.blockSignals(False)
        self._filter_language_table(self.language_filter.text() if hasattr(self, "language_filter") else "")

    def _filter_language_table(self, text):
        q = text.strip().lower()
        for r in range(self.language_table.rowCount()):
            key = self.language_table.item(r, 0).text().lower()
            val = self.language_table.item(r, 1).text().lower()
            self.language_table.setRowHidden(r, bool(q and q not in key and q not in val))

    def _language_cell_changed(self, row, column):
        if column != 1: return
        key = self.language_table.item(row, 0).text()
        value = self.language_table.item(row, 1).text()
        self._language_values[key] = value

    def _apply_language(self):
        t = self._language_values
        # Translate labels by their own semantic key; storage and languages are never cross-wired.
        labels = {
            "dashboard": t.get("dashboard", "Dashboard"), "sites": t.get("sites", "Seed Sites"),
            "crawler": t.get("crawler", "Crawler"), "storage": t.get("storage", "Storage & S3"),
            "ia": t.get("ia_settings", "Internet Archive"), "languages": t.get("languages", "Languages & Editor"),
            "logs": t.get("logs", "Live Logs"),
        }
        for key, text in labels.items():
            if key in self.nav: self.nav[key].setText(text)
        if hasattr(self, "start_btn"): self.start_btn.setText("▶  " + t.get("start", "Start Crawl"))
        if hasattr(self, "pause_btn"): self.pause_btn.setText("⏸  " + t.get("pause", "Pause"))
        if hasattr(self, "stop_btn"): self.stop_btn.setText("■  " + t.get("stop", "Stop Crawl"))
        self.setWindowTitle(t.get("title", "AWEC Desktop — Web Archive Engine"))
        self.language_status.setText(f"✓ Applied: {self._language_code}")
        self._log(f"🌐 Language applied: {self._language_code}")

    def _import_language(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import AWEC Language Pack", "", "AWEC Language (*.awec.language);;All Files (*)")
        if not path: return
        try:
            values = load_language(path)
            values.pop("language", None); values.pop("name", None)
            base = get_translation("en"); base.update(values)
            self._language_values = base
            self._language_code = "custom"
            self._populate_language_table()
            self._apply_language()
            self.language_status.setText(f"✓ Imported: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "AWEC", f"Language import failed: {e}")

    def _export_language(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export AWEC Language Pack", "custom.awec.language", "AWEC Language (*.awec.language)")
        if not path: return
        try:
            save_language(path, self._language_values, self._language_code if self._language_code != "custom" else "xx", "AWEC Custom Language")
            self.language_status.setText(f"✓ Exported: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "AWEC", f"Language export failed: {e}")

    def _save_custom_language(self):
        self._export_language()

    def _page(self, key):
        # Use actual page widgets for the appended pages, so Storage and Languages
        # cannot be swapped by numeric index changes elsewhere in the UI.
        if key == "storage" and hasattr(self, "storage_page"):
            self.pages.setCurrentWidget(self.storage_page)
        elif key == "languages" and hasattr(self, "language_page"):
            self.pages.setCurrentWidget(self.language_page)
        else:
            indexes = {"dashboard": 0, "sites": 1, "crawler": 2, "ia": 3, "logs": 4}
            if hasattr(self, "pages") and key in indexes:
                self.pages.setCurrentIndex(indexes[key])
        if key in getattr(self, "nav", {}):
            for k, b in self.nav.items(): b.setChecked(k == key)
