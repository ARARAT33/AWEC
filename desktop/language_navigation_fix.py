"""Navigation compatibility fix for the v10 language studio.

The v12 UI adds Resume Center and Archive Explorer after the v10 language page,
so v10's old ``pages.count() - 1`` lookup can accidentally open Archive Explorer.
Keep the existing 10+ language/custom naming system and resolve its page directly.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget


def install_language_navigation_fix() -> None:
    from desktop.app_window_v10 import AWECMainWindow as V10MainWindow

    def _page_v10_language(self):
        status = getattr(self, "language_status", None)
        page = None
        if status is not None:
            candidate = status
            while candidate is not None:
                try:
                    if self.pages.indexOf(candidate) >= 0:
                        page = candidate
                        break
                except Exception:
                    pass
                candidate = candidate.parentWidget() if isinstance(candidate, QWidget) else None

        if page is None:
            # Safe fallback for older layouts: locate the page containing the
            # language editor list instead of assuming it is the last page.
            for i in range(self.pages.count()):
                candidate = self.pages.widget(i)
                if candidate is not None and candidate.findChildren(type(getattr(self, "name_list", QWidget()))):
                    if hasattr(self, "name_list") and self.name_list is not None:
                        parent = self.name_list
                        while parent is not None:
                            if self.pages.indexOf(parent) == i:
                                page = candidate
                                break
                            parent = parent.parentWidget()
                if page is not None:
                    break

        if page is not None:
            self.pages.setCurrentWidget(page)
        for b in getattr(self, "nav", {}).values():
            b.setChecked(False)
        if hasattr(self, "nav_v10"):
            self.nav_v10.setChecked(True)

    V10MainWindow._page_v10_language = _page_v10_language
