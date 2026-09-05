#!/usr/bin/env python3
"""AWEC Desktop canonical packaged entry point.

The packaged application must use the same v12 command-center path as the
source launcher: v12 UI -> desktop.engine.Engine -> ResumableAWECrawler.
"""
from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from desktop.app_window_v12 import AWECMainWindow
from desktop.theme import apply_theme


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app)
    window = AWECMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
