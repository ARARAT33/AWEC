"""AWEC Lite desktop UI.

Compact shell around the stable crawler UI. The menu is rebuilt in-place so
Qt does not create competing layouts, while keeping the crawler controls and
advanced features available.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from desktop.app_window_v5 import AWECMainWindow as V5MainWindow


class AWECMainWindow(V5MainWindow):
    """Fast desktop shell with a lightweight, full navigation menu."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AWEC • Web Archive Engine")
        self.setMinimumSize(900, 620)
        self.resize(1120, 720)
        self._rewrite_sidebar()

    def _rewrite_sidebar(self):
        side = self.findChild(QWidget, "sidebar")
        if side is None:
            return
        layout = side.layout()
        if layout is None:
            return

        status = getattr(self, "status", None)
        old_buttons = list(getattr(self, "nav", {}).values())

        # Reuse the existing Qt layout. Creating a second layout on the same
        # QWidget was the reason the menu could disappear entirely.
        for button in old_buttons:
            layout.removeWidget(button)
            button.deleteLater()

        # Remove every old layout item except the status widget.
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

        brand = QLabel("AWEC")
        brand.setObjectName("brandTitle")
        layout.addWidget(brand)

        subtitle = QLabel("Web Archive Engine")
        subtitle.setObjectName("brandSubtitle")
        layout.addWidget(subtitle)

        section = QLabel("WORKSPACE")
        section.setObjectName("menuSection")
        layout.addWidget(section)

        self.nav = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        items = (
            ("dashboard", "⌂  Dashboard"),
            ("sites", "◎  Seed Sites"),
            ("crawler", "↯  Crawler"),
            ("ia", "☁  Internet Archive"),
            ("logs", "≡  Live Logs"),
        )
        for key, text in items:
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setMinimumHeight(36)
            button.setMaximumHeight(40)
            button.clicked.connect(lambda checked=False, k=key: self._page(k))
            group.addButton(button)
            self.nav[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        if status is not None:
            layout.addWidget(status)

        self._page("dashboard")
