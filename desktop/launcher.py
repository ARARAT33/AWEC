#!/usr/bin/env python3
"""AWEC Desktop entry point."""
from PySide6.QtWidgets import QApplication
from .theme import apply_theme
from .app_window_v2 import AWECMainWindow


def main():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    window = AWECMainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
