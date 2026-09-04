"""AWEC Lite desktop UI.

Keeps the stable v5 crawler/IA engine while removing the heavyweight v10-v12
UI inheritance chain, archive explorer, resume polling and runtime-wide i18n.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from desktop.app_window_v5 import AWECMainWindow as V5MainWindow


class AWECMainWindow(V5MainWindow):
    """Compact AWEC shell with a single, deterministic navigation menu."""

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
        old_layout = side.layout()
        if old_layout is None:
            return

        # Remove the v5 navigation widgets; keep the sidebar itself and status state.
        old_buttons = list(getattr(self, "nav", {}).values())
        status = getattr(self, "status", None)
        for button in old_buttons:
            old_layout.removeWidget(button)
            button.deleteLater()

        while old_layout.count():
            item = old_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not status:
                widget.deleteLater()
            elif item.layout() is not None:
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget() is not None:
                        child.widget().deleteLater()

        side.setFixedWidth(188)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(5)

        brand = QLabel("AWEC")
        brand.setObjectName("brandTitle")
        brand.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(brand)
        subtitle = QLabel("Web Archive Engine")
        subtitle.setObjectName("brandSubtitle")
        layout.addWidget(subtitle)

        section = QLabel("WORKSPACE")
        section.setObjectName("menuSection")
        layout.addWidget(section)
        layout.addSpacing(3)

        self.nav = {}
        items = (
            ("dashboard", "⌂  Dashboard"),
            ("sites", "◎  Seed Sites"),
            ("crawler", "↯  Crawler"),
            ("ia", "☁  Internet Archive"),
            ("logs", "≡  Live Logs"),
        )
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, text in items:
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setMinimumHeight(38)
            button.clicked.connect(lambda checked=False, k=key: self._page(k))
            group.addButton(button)
            self.nav[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        if status is not None:
            layout.addWidget(status)
        self._page("dashboard")
