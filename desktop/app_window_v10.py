"""AWEC Desktop UI v10.

Keeps the existing v7 crawler/IA UI and adds a universal naming studio:
- 10+ built-in language packs remain available through the existing i18n module.
- Every visible text-bearing widget can be renamed manually.
- Per-language overrides are persisted locally.
- Custom .awec.language packs can be imported/exported.
- No secrets are included in language/name files.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QComboBox, QVBoxLayout, QWidget
)

from desktop.app_window_v7 import AWECMainWindow as V7MainWindow
from desktop.i18n import LANGUAGES
from desktop.language_editor import load_language, save_language


class AWECMainWindow(V7MainWindow):
    """AWEC v10: crawler control center + unlimited user naming layer."""

    NAME_FILE = Path.home() / "AWEC" / "ui_names_v10.json"
    PACK_DIR = Path.home() / "AWEC" / "languages"

    def __init__(self):
        self._name_overrides: dict[str, dict[str, str]] = {}
        self._name_widgets: dict[str, QWidget] = {}
        super().__init__()
        self._load_name_overrides()
        self._build_language_studio()
        self._index_visible_text()
        self._refresh_name_list()

    def _build_language_studio(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Language & Universal Naming Studio"))
        layout.addWidget(QLabel(
            "Choose a language, then rename every visible AWEC label/button manually. "
            "Changes are stored per language and survive restarts."
        ))

        top = QHBoxLayout()
        self.v10_language = QComboBox()
        for code, name in LANGUAGES.items():
            self.v10_language.addItem(f"{name} ({code})", code)
        self.v10_language.addItem("Custom / User Language", "custom")
        self.v10_language.currentIndexChanged.connect(self._refresh_name_list)
        top.addWidget(QLabel("Language:"))
        top.addWidget(self.v10_language, 1)
        new_btn = QPushButton("＋ New Custom Language")
        new_btn.clicked.connect(self._new_custom_language)
        top.addWidget(new_btn)
        layout.addLayout(top)

        row = QHBoxLayout()
        self.name_filter = QLineEdit()
        self.name_filter.setPlaceholderText("Search every UI label / button...")
        self.name_filter.textChanged.connect(self._refresh_name_list)
        row.addWidget(self.name_filter, 1)
        export_btn = QPushButton("Export .awec.language")
        export_btn.clicked.connect(self._export_language)
        import_btn = QPushButton("Import .awec.language")
        import_btn.clicked.connect(self._import_language)
        row.addWidget(import_btn)
        row.addWidget(export_btn)
        layout.addLayout(row)

        self.name_list = QListWidget()
        self.name_list.currentRowChanged.connect(self._select_name)
        layout.addWidget(self.name_list, 1)

        form = QFormLayout()
        self.name_key = QLineEdit(); self.name_key.setReadOnly(True)
        self.name_original = QLineEdit(); self.name_original.setReadOnly(True)
        self.name_value = QLineEdit()
        form.addRow("UI key", self.name_key)
        form.addRow("Original", self.name_original)
        form.addRow("Your name", self.name_value)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        save = QPushButton("✓ Apply Name")
        save.clicked.connect(self._save_selected_name)
        reset = QPushButton("↺ Reset This Name")
        reset.clicked.connect(self._reset_selected_name)
        apply_all = QPushButton("⚡ Apply Language To UI")
        apply_all.clicked.connect(self._apply_language)
        buttons.addWidget(save); buttons.addWidget(reset); buttons.addWidget(apply_all)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.language_status = QLabel("● Naming Studio Ready")
        self.language_status.setWordWrap(True)
        layout.addWidget(self.language_status)
        self.pages.addWidget(page)

        # Add a dedicated navigation control without changing the v7 pages.
        side = self.findChild(QWidget, "sidebar")
        if side and side.layout():
            nav = QPushButton("Languages & Names")
            nav.setObjectName("navButton")
            nav.setCheckable(True)
            nav.clicked.connect(lambda: self._page_v10_language())
            side.layout().insertWidget(max(0, side.layout().count() - 2), nav)
            self.nav_v10 = nav

    def _page_v10_language(self):
        self.pages.setCurrentWidget(self.pages.widget(self.pages.count() - 1))
        for b in self.nav.values():
            b.setChecked(False)
        if hasattr(self, "nav_v10"):
            self.nav_v10.setChecked(True)

    def _index_visible_text(self):
        self._name_widgets.clear()
        root = self.centralWidget()
        if not root:
            return
        widgets = [root, *root.findChildren(QWidget)]
        for w in widgets:
            text = ""
            if hasattr(w, "text") and callable(w.text):
                try: text = w.text()
                except Exception: text = ""
            elif hasattr(w, "placeholderText") and callable(w.placeholderText):
                try: text = w.placeholderText()
                except Exception: text = ""
            text = str(text).strip()
            if not text or text.startswith("●") or text in {"0", "—"}:
                continue
            # Stable enough for this UI while remaining independent of secrets/config.
            key = w.objectName() or f"text:{text}"
            if key.startswith("text:") and key in self._name_widgets:
                continue
            self._name_widgets[key] = w
        self._original_text = {
            k: self._widget_text(w) for k, w in self._name_widgets.items()
        }

    @staticmethod
    def _widget_text(w: QWidget) -> str:
        if hasattr(w, "text") and callable(w.text):
            try: return str(w.text())
            except Exception: pass
        if hasattr(w, "placeholderText") and callable(w.placeholderText):
            try: return str(w.placeholderText())
            except Exception: pass
        return ""

    @staticmethod
    def _set_widget_text(w: QWidget, value: str):
        if hasattr(w, "setText") and callable(w.setText):
            try: w.setText(value); return
            except Exception: pass
        if hasattr(w, "setPlaceholderText") and callable(w.setPlaceholderText):
            try: w.setPlaceholderText(value)
            except Exception: pass

    def _load_name_overrides(self):
        try:
            self._name_overrides = json.loads(self.NAME_FILE.read_text(encoding="utf-8"))
            if not isinstance(self._name_overrides, dict): self._name_overrides = {}
        except Exception:
            self._name_overrides = {}

    def _persist_name_overrides(self):
        self.NAME_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.NAME_FILE.write_text(json.dumps(self._name_overrides, ensure_ascii=False, indent=2), encoding="utf-8")

    def _current_lang(self) -> str:
        return str(self.v10_language.currentData() or "custom")

    def _refresh_name_list(self):
        if not hasattr(self, "name_list"):
            return
        self.name_list.blockSignals(True); self.name_list.clear()
        needle = self.name_filter.text().strip().lower() if hasattr(self, "name_filter") else ""
        lang = self._current_lang()
        overrides = self._name_overrides.get(lang, {})
        for key, w in self._name_widgets.items():
            original = self._original_text.get(key, self._widget_text(w))
            value = overrides.get(key, original)
            label = f"{original}  →  {value}" if value != original else original
            if needle and needle not in (key + " " + original + " " + value).lower():
                continue
            self.name_list.addItem(label)
            self.name_list.item(self.name_list.count() - 1).setData(Qt.ItemDataRole.UserRole, key)
        self.name_list.blockSignals(False)
        if self.name_list.count(): self.name_list.setCurrentRow(0)

    def _select_name(self, row: int):
        if row < 0: return
        item = self.name_list.item(row)
        key = item.data(Qt.ItemDataRole.UserRole)
        original = self._original_text.get(key, "")
        value = self._name_overrides.get(self._current_lang(), {}).get(key, original)
        self.name_key.setText(str(key)); self.name_original.setText(original); self.name_value.setText(value)

    def _save_selected_name(self):
        row = self.name_list.currentRow()
        if row < 0: return
        key = self.name_list.item(row).data(Qt.ItemDataRole.UserRole)
        value = self.name_value.text().strip()
        if not value: return
        lang = self._current_lang()
        self._name_overrides.setdefault(lang, {})[key] = value
        self._persist_name_overrides()
        self._apply_language()
        self._refresh_name_list()
        self.language_status.setText(f"✓ Saved custom name for {key}")

    def _reset_selected_name(self):
        row = self.name_list.currentRow()
        if row < 0: return
        key = self.name_list.item(row).data(Qt.ItemDataRole.UserRole)
        self._name_overrides.setdefault(self._current_lang(), {}).pop(key, None)
        self._persist_name_overrides(); self._apply_language(); self._refresh_name_list()

    def _apply_language(self):
        overrides = self._name_overrides.get(self._current_lang(), {})
        for key, value in overrides.items():
            if key in self._name_widgets: self._set_widget_text(self._name_widgets[key], value)
        self.language_status.setText(
            f"✓ Applied {len(overrides)} custom names • {len(self._name_widgets)} UI elements available"
        )

    def _new_custom_language(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Language", "Language code (e.g. ar, ka, xx):")
        if not ok or not name.strip(): return
        code = name.strip().lower().replace(" ", "-")
        if code not in [self.v10_language.itemData(i) for i in range(self.v10_language.count())]:
            self.v10_language.addItem(f"Custom: {code}", code)
        self._name_overrides.setdefault(code, {})
        self._persist_name_overrides()
        self.v10_language.setCurrentIndex(self.v10_language.findData(code))

    def _export_language(self):
        lang = self._current_lang(); values = {}
        overrides = self._name_overrides.get(lang, {})
        for key, w in self._name_widgets.items(): values[key] = overrides.get(key, self._original_text.get(key, ""))
        path, _ = QFileDialog.getSaveFileName(self, "Export AWEC Language", f"{lang}.awec.language", "AWEC Language (*.awec.language)")
        if not path: return
        save_language(path, values, lang, LANGUAGES.get(lang, f"Custom {lang}"))
        self.language_status.setText(f"✓ Exported {path}")

    def _import_language(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import AWEC Language", "", "AWEC Language (*.awec.language);;All Files (*)")
        if not path: return
        try:
            values = load_language(path); lang = values.pop("language", "custom"); values.pop("name", None)
            self._name_overrides[lang] = values
            self._persist_name_overrides()
            if self.v10_language.findData(lang) < 0: self.v10_language.addItem(f"Custom: {lang}", lang)
            self.v10_language.setCurrentIndex(self.v10_language.findData(lang))
            self._apply_language(); self._refresh_name_list()
            self.language_status.setText(f"✓ Imported {len(values)} UI names")
        except Exception as exc:
            QMessageBox.warning(self, "AWEC Language", str(exc))
