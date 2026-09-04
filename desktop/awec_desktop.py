#!/usr/bin/env python3
"""AWEC Desktop v12 entry point."""
import sys
from PySide6.QtWidgets import QApplication
from desktop.theme import apply_theme
from desktop.language_navigation_fix import install_language_navigation_fix

# Install before importing the v12 window so the inherited v10 language button
# resolves its own page instead of assuming the last stacked page is Languages.
install_language_navigation_fix()
from desktop.app_window_v12 import AWECMainWindow  # noqa: E402


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app)
    window = AWECMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
