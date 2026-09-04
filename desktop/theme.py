"""AWEC polished dark desktop theme."""
from PySide6.QtWidgets import QApplication

AWEC_DARK_QSS = '''
QMainWindow { background:#0a0f1c; color:#e8edf7; font-family:'Segoe UI','SF Pro Text',Arial,sans-serif; font-size:13px; }
QWidget { color:#e8edf7; }
QFrame#sidebar { background:#070b14; border-right:1px solid #1d2940; }
QLabel#brandTitle { font-size:30px; font-weight:900; color:#5b8cff; letter-spacing:2px; }
QLabel#brandSubtitle { font-size:11px; color:#71809b; margin-bottom:8px; }
QLabel#pageHeader { font-size:28px; font-weight:850; color:#fff; }
QLabel#pageSubtitle { color:#8392ad; font-size:13px; margin-bottom:4px; }
QLabel#hint { color:#8fa1bf; padding:12px; background:#0d1628; border:1px solid #1d2b45; border-radius:10px; }
QLabel#infoBadge { background:#101c31; border:1px solid #2b4168; border-radius:9px; padding:10px 12px; color:#a9c2f8; font-weight:700; }
QPushButton#navButton { background:transparent; border:1px solid transparent; border-radius:9px; padding:12px 14px; text-align:left; font-weight:650; color:#8291ad; }
QPushButton#navButton:hover { background:#111a2d; color:#fff; }
QPushButton#navButton:checked { background:#172646; border-color:#31549a; color:#6e99ff; }
QGroupBox { background:#101827; border:1px solid #22314c; border-radius:13px; margin-top:12px; padding:18px 14px 14px; font-weight:750; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 7px; color:#72a0ff; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit,QListWidget,QTextEdit { background:#0b1322; border:1px solid #263754; border-radius:9px; padding:9px 11px; color:#f3f6fc; selection-background-color:#3d70ef; }
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus,QPlainTextEdit:focus,QTextEdit:focus { border:1px solid #4d7fff; background:#0d1729; }
QPushButton { background:#162239; border:1px solid #2b3c5d; border-radius:9px; padding:10px 15px; font-weight:650; color:#e8edf7; }
QPushButton:hover { background:#203354; border-color:#527ff0; }
QPushButton:pressed { background:#10192a; }
QPushButton:disabled { color:#59677f; background:#111827; border-color:#1d2940; }
QPushButton#primaryButton { background:#3d72f5; border:0; color:#fff; font-weight:800; }
QPushButton#primaryButton:hover { background:#5585ff; }
QPushButton#dangerButton { background:#c9364c; border:0; color:#fff; font-weight:800; }
QPushButton#dangerButton:hover { background:#e04b60; }
QPushButton#warningButton { background:#b86b08; border:0; color:#fff; font-weight:800; }
QPushButton#warningButton:hover { background:#d8870b; }
QFrame#metricCard { background:#101827; border:1px solid #1f2e49; border-radius:12px; }
QLabel#metricTitle { font-size:10px; font-weight:750; color:#7789a8; }
QLabel#metricValue { font-size:23px; font-weight:850; color:#fff; margin-top:3px; }
QScrollBar:vertical { background:#0a0f1c; width:9px; border:0; }
QScrollBar::handle:vertical { background:#263754; border-radius:4px; min-height:25px; }
QScrollBar::handle:vertical:hover { background:#3d72f5; }
QCheckBox { spacing:8px; font-weight:550; }
QCheckBox::indicator { width:18px; height:18px; border-radius:5px; border:1px solid #344867; background:#0b1322; }
QCheckBox::indicator:checked { background:#3d72f5; border-color:#3d72f5; }
QLabel#statusBadgeStopped,QLabel#statusBadgeRunning,QLabel#statusBadgePaused { border-radius:8px; padding:8px 10px; font-weight:850; }
QLabel#statusBadgeStopped { background:#182235; color:#a0aec4; border:1px solid #34435d; }
QLabel#statusBadgeRunning { background:#073d30; color:#42dfad; border:1px solid #07936e; }
QLabel#statusBadgePaused { background:#57300a; color:#ffc25a; border:1px solid #b76a0a; }
'''

def apply_theme(app: QApplication):
    app.setStyleSheet(AWEC_DARK_QSS)
