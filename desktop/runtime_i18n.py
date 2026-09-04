"""Runtime localization for the entire AWEC Qt interface.

The engine translates widget text, placeholders, group-box titles and tab labels
from the existing canonical 10-language catalog, then applies user overrides.
Unknown/custom strings remain untouched instead of being guessed.
"""
from __future__ import annotations

from typing import Any
from desktop.i18n import LANGUAGES, TRANSLATIONS


def _reverse_catalog(lang: str) -> dict[str, str]:
    catalog = TRANSLATIONS.get(lang, {})
    return {str(v): str(v2) for key, v in TRANSLATIONS.get("en", {}).items() if (v2 := catalog.get(key))}


def translate_value(value: str, lang: str) -> str:
    if not value:
        return value
    if lang == "en":
        return value
    catalog = TRANSLATIONS.get(lang, {})
    # Exact canonical English value first.
    for key, english in TRANSLATIONS.get("en", {}).items():
        if value == english:
            return str(catalog.get(key, value))
    # A few common dynamic labels.
    dynamic = {
        "AWEC • Health Check": "AWEC • " + str(catalog.get("health_check", "Health Check")),
        "Languages & Names": str(catalog.get("languages", "Languages & Names")),
    }
    return dynamic.get(value, value)


def apply_to_widget_tree(root: Any, lang: str, overrides: dict[str, str] | None = None) -> int:
    """Translate visible Qt text without touching secrets or user data."""
    overrides = overrides or {}
    changed = 0
    widgets = [root, *root.findChildren(type(root))] if root is not None else []
    # QObject children can include all QWidget subclasses; use findChildren(QWidget)
    try:
        from PySide6.QtWidgets import QWidget
        widgets = [root, *root.findChildren(QWidget)] if root is not None else []
    except Exception:
        pass

    def stable_key(w: Any, old: str) -> str:
        return str(w.objectName() or f"text:{old}")

    for w in widgets:
        try:
            if hasattr(w, "text") and callable(w.text):
                old = str(w.text())
                if old:
                    key = stable_key(w, old)
                    value = overrides.get(key, translate_value(old, lang))
                    if value != old and hasattr(w, "setText"):
                        w.setText(value); changed += 1
            if hasattr(w, "placeholderText") and callable(w.placeholderText):
                old = str(w.placeholderText())
                if old:
                    key = stable_key(w, old)
                    value = overrides.get(key, translate_value(old, lang))
                    if value != old and hasattr(w, "setPlaceholderText"):
                        w.setPlaceholderText(value); changed += 1
            if hasattr(w, "title") and callable(w.title) and hasattr(w, "setTitle"):
                old = str(w.title())
                if old:
                    key = stable_key(w, old)
                    value = overrides.get(key, translate_value(old, lang))
                    if value != old:
                        w.setTitle(value); changed += 1
        except Exception:
            continue

    # QTabWidget labels are not widget.text().
    for w in widgets:
        try:
            if hasattr(w, "count") and hasattr(w, "tabText") and hasattr(w, "setTabText"):
                for i in range(w.count()):
                    old = str(w.tabText(i))
                    value = translate_value(old, lang)
                    if value != old:
                        w.setTabText(i, value); changed += 1
        except Exception:
            pass
    return changed


def language_name(code: str) -> str:
    return LANGUAGES.get(code, f"Custom ({code})")
