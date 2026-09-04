"""AWEC v11 premium dark glass command-center theme."""
from PySide6.QtWidgets import QApplication

AWEC_DARK_QSS = '''
QMainWindow { background:#070b14; color:#edf2ff; font-family:'Segoe UI','SF Pro Display',Arial,sans-serif; font-size:13px; }
QWidget { color:#edf2ff; }
QFrame#sidebar { background:#050811; border-right:1px solid #17233a; }
QLabel#brandTitle { font-size:31px; font-weight:950; color:#76a4ff; letter-spacing:3px; }
QLabel#brandSubtitle { font-size:11px; color:#667695; margin-bottom:10px; }
QLabel#pageHeader { font-size:29px; font-weight:900; color:#fff; }
QLabel#pageSubtitle { color:#8090ae; font-size:13px; margin-bottom:5px; }
QLabel#hint { color:#9aabd0; padding:13px; background:#0b1322; border:1px solid #1b2b49; border-radius:12px; }
QLabel#infoBadge { background:#0e1a30; border:1px solid #28436f; border-radius:10px; padding:10px 12px; color:#b4cbff; font-weight:750; }
QPushButton#navButton { background:transparent; border:1px solid transparent; border-radius:10px; padding:12px 14px; text-align:left; font-weight:700; color:#7888a7; }
QPushButton#navButton:hover { background:#10192b; color:#fff; }
QPushButton#navButton:checked { background:#152642; border-color:#315896; color:#7ba5ff; }
QGroupBox { background:#0d1524; border:1px solid #1c2c47; border-radius:14px; margin-top:12px; padding:19px 14px 14px; font-weight:800; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 8px; color:#79a5ff; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit,QListWidget,QTextEdit { background:#080f1c; border:1px solid #223451; border-radius:10px; padding:9px 11px; color:#f4f7ff; selection-background-color:#3d73ef; }
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus,QPlainTextEdit:focus,QTextEdit:focus { border:1px solid #5a8cff; background:#0b1425; }
QPushButton { background:#111d31; border:1px solid #263a5b; border-radius:10px; padding:10px 15px; font-weight:700; color:#eaf0ff; }
QPushButton:hover { background:#1b2e4c; border-color:#5a86e8; }
QPushButton:pressed { background:#0b1424; }
QPushButton:disabled { color:#56647c; background:#0c1320; border-color:#17243a; }
QPushButton#primaryButton { background:#3e73f5; border:0; color:#fff; font-weight:850; }
QPushButton#primaryButton:hover { background:#5a88ff; }
QPushButton#dangerButton { background:#bd334b; border:0; color:#fff; font-weight:850; }
QPushButton#dangerButton:hover { background:#df4b61; }
QPushButton#warningButton { background:#aa650c; border:0; color:#fff; font-weight:850; }
QPushButton#warningButton:hover { background:#ca7e13; }
QFrame#metricCard { background:#0d1524; border:1px solid #1a2a45; border-radius:13px; }
QLabel#metricTitle { font-size:10px; font-weight:800; color:#7385a4; }
QLabel#metricValue { font-size:24px; font-weight:900; color:#fff; margin-top:3px; }
QProgressBar { background:#080f1c; border:1px solid #20324f; border-radius:9px; height:18px; text-align:center; color:#fff; font-weight:800; }
QProgressBar::chunk { background:#3e73f5; border-radius:8px; }
QScrollBar:vertical { background:#070b14; width:9px; border:0; }
QScrollBar::handle:vertical { background:#263858; border-radius:4px; min-height:25px; }
QScrollBar::handle:vertical:hover { background:#3f73ed; }
QCheckBox { spacing:8px; font-weight:600; }
QCheckBox::indicator { width:18px; height:18px; border-radius:5px; border:1px solid #344a6c; background:#080f1c; }
QCheckBox::indicator:checked { background:#3e73f5; border-color:#3e73f5; }
QLabel#statusBadgeStopped,QLabel#statusBadgeRunning,QLabel#statusBadgePaused { border-radius:9px; padding:8px 10px; font-weight:900; }
QLabel#statusBadgeStopped { background:#172235; color:#a8b4ca; border:1px solid #30415c; }
QLabel#statusBadgeRunning { background:#06382d; color:#42e1ae; border:1px solid #07936e; }
QLabel#statusBadgePaused { background:#4e2d09; color:#ffc35d; border:1px solid #b66b0a; }
QFrame#v11Hero { background:#0d1830; border:1px solid #294b84; border-radius:16px; }
QLabel#v11HeroTitle { font-size:20px; font-weight:950; color:#8db2ff; letter-spacing:1px; }
QLabel#v11HeroSubtitle { color:#9baccc; margin-top:3px; }
QLabel#v11Card { background:#0b1424; border:1px solid #1c3151; border-radius:12px; padding:14px; font-weight:800; color:#b6c9eb; }
'''

def apply_theme(app: QApplication):
    app.setStyleSheet(AWEC_DARK_QSS)
