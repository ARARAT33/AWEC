#!/usr/bin/env python3
"""AWEC Desktop 3.0 entry point script."""
import sys
from PySide6.QtWidgets import QApplication
from desktop.theme import apply_theme
from desktop.app_window_v2 import AWECMainWindow

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app)

    window = AWECMainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
