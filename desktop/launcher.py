#!/usr/bin/env python3
"""AWEC Desktop 3.0/v12 canonical entry point.

The launcher deliberately targets the v12 command center so the desktop
application uses the same UI -> Engine -> ResumableAWECrawler(v12) path.
"""
import sys
from PySide6.QtWidgets import QApplication
from desktop.theme import apply_theme
from desktop.app_window_v12 import AWECMainWindow


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app)

    window = AWECMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
