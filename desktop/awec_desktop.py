#!/usr/bin/env python3
"""AWEC Desktop entry point."""
import sys
from PySide6.QtWidgets import QApplication
from desktop.theme import apply_theme
from desktop.app_window_runtime import AWECMainWindow

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app)
    window = AWECMainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
