#!/usr/bin/env python3
"""AWEC Desktop Lite entry point."""
from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from desktop.app_window_lite import AWECMainWindow
from desktop.lite_theme import apply_lite_theme


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_lite_theme(app)
    window = AWECMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
