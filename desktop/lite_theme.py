"""Compact theme for AWEC Desktop Lite."""
from PySide6.QtWidgets import QApplication

LITE_QSS = """
QMainWindow, QWidget { background:#f5f7fa; color:#1b2430; font-family:'Segoe UI',Arial,sans-serif; font-size:13px; }
QFrame#sidebar { background:#ffffff; border-right:1px solid #dde3ea; }
QLabel#brandTitle { font-size:25px; font-weight:900; color:#172033; letter-spacing:1.5px; }
QLabel#brandSubtitle { color:#7a8494; font-size:11px; margin-bottom:12px; }
QLabel#menuSection { color:#9aa4b2; font-size:10px; font-weight:800; letter-spacing:1px; padding:7px 4px 2px; }
QPushButton#navButton { background:transparent; border:1px solid transparent; border-radius:7px; padding:8px 10px; text-align:left; color:#5d6878; font-weight:700; }
QPushButton#navButton:hover { background:#f1f4f8; color:#172033; }
QPushButton#navButton:checked { background:#e8f0ff; border-color:#c9daf7; color:#245ca8; }
QLabel#statusBadgeStopped,QLabel#statusBadgeRunning,QLabel#statusBadgePaused { border-radius:7px; padding:7px 9px; font-weight:800; }
QLabel#statusBadgeStopped { background:#eef1f5; color:#596575; border:1px solid #d9dfe7; }
QLabel#statusBadgeRunning { background:#e6f5ec; color:#177044; border:1px solid #b8dfc8; }
QLabel#statusBadgePaused { background:#fff3db; color:#895b0a; border:1px solid #edd49a; }
QLabel#pageHeader { font-size:24px; font-weight:900; color:#172033; }
QLabel#pageSubtitle { color:#748094; font-size:12px; }
QGroupBox { background:#ffffff; border:1px solid #dde3ea; border-radius:8px; margin-top:10px; padding:14px 12px 10px; font-weight:800; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 6px; background:#ffffff; color:#355a8c; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit,QListWidget,QTextEdit { background:#ffffff; border:1px solid #ccd4df; border-radius:6px; padding:7px 9px; }
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus,QPlainTextEdit:focus { border:1px solid #6f99d5; }
QPushButton { background:#ffffff; border:1px solid #ccd4df; border-radius:6px; padding:7px 11px; font-weight:700; }
QPushButton:hover { background:#f3f6fa; }
QPushButton#primaryButton { background:#326fc5; color:#ffffff; border-color:#326fc5; font-weight:900; }
QPushButton#warningButton { background:#b47717; color:#ffffff; border-color:#b47717; }
QPushButton#dangerButton { background:#bd3e50; color:#ffffff; border-color:#bd3e50; }
QFrame#metricCard { background:#ffffff; border:1px solid #dde3ea; border-radius:8px; }
QLabel#metricTitle { color:#7a8596; font-size:10px; font-weight:800; }
QLabel#metricValue { color:#182337; font-size:21px; font-weight:900; }
QLabel#infoBadge { background:#edf4ff; border:1px solid #cfddf4; border-radius:6px; padding:7px 9px; }
QLabel#hint { background:#f8fafc; border:1px solid #e0e5ec; border-radius:6px; padding:8px 10px; color:#536073; }
QProgressBar { height:14px; border:1px solid #d5dce6; border-radius:6px; background:#edf0f4; text-align:center; }
QScrollBar:vertical { width:8px; background:#f5f7fa; border:0; }
QScrollBar::handle:vertical { background:#c4ccd7; border-radius:4px; min-height:24px; }
"""


def apply_lite_theme(app: QApplication) -> None:
    app.setStyleSheet(LITE_QSS)
