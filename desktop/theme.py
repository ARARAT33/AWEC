"""AWEC v12 liquid-glass command-center theme."""
from PySide6.QtWidgets import QApplication

AWEC_DARK_QSS='''
QMainWindow { background:#050812; color:#eef4ff; font-family:'Segoe UI','SF Pro Display',Arial,sans-serif; font-size:13px; }
QWidget { color:#eef4ff; }
QFrame#sidebar { background:rgba(7,12,25,245); border-right:1px solid #263657; }
QLabel#brandTitle { font-size:33px; font-weight:950; color:#8db7ff; letter-spacing:4px; }
QLabel#brandSubtitle { font-size:11px; color:#7f91b2; margin-bottom:10px; }
QLabel#pageHeader { font-size:31px; font-weight:900; color:#fff; }
QLabel#pageSubtitle { color:#93a5c7; font-size:13px; margin-bottom:5px; }
QLabel#hint { color:#b7c7e5; padding:14px; background:#0b1323; border:1px solid #2a3d60; border-radius:16px; }
QLabel#infoBadge { background:#0e1930; border:1px solid #35578f; border-radius:12px; padding:10px 12px; color:#c1d6ff; font-weight:800; }
QPushButton#navButton { background:rgba(15,25,45,70); border:1px solid transparent; border-radius:13px; padding:13px 15px; text-align:left; font-weight:750; color:#8293b3; }
QPushButton#navButton:hover { background:#14223b; color:#fff; border-color:#30496f; }
QPushButton#navButton:checked { background:#19345b; border-color:#4c78bd; color:#9ec1ff; }
QGroupBox { background:rgba(14,23,40,235); border:1px solid #263b5f; border-radius:18px; margin-top:14px; padding:21px 15px 15px; font-weight:850; }
QGroupBox::title { subcontrol-origin:margin; left:15px; padding:0 9px; color:#8fb7ff; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit,QListWidget,QTextEdit,QTreeWidget,QTextBrowser { background:#070f1e; border:1px solid #2a4166; border-radius:12px; padding:9px 11px; color:#f5f8ff; selection-background-color:#3d73ef; }
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus,QPlainTextEdit:focus,QTextEdit:focus,QTreeWidget:focus,QTextBrowser:focus { border:1px solid #6a99ff; background:#0a1427; }
QPushButton { background:#111f35; border:1px solid #30476b; border-radius:12px; padding:10px 16px; font-weight:750; color:#edf3ff; }
QPushButton:hover { background:#1a3151; border-color:#6995e8; }
QPushButton:pressed { background:#0b1526; }
QPushButton:disabled { color:#5d6b83; background:#0b1320; border-color:#1a2940; }
QPushButton#primaryButton { background:#3e73f5; border:0; color:#fff; font-weight:900; }
QPushButton#primaryButton:hover { background:#6692ff; }
QPushButton#dangerButton { background:#c33850; border:0; color:#fff; font-weight:900; }
QPushButton#warningButton { background:#ae6c10; border:0; color:#fff; font-weight:900; }
QFrame#metricCard { background:rgba(14,24,43,235); border:1px solid #263b5f; border-radius:16px; }
QLabel#metricTitle { font-size:10px; font-weight:850; color:#7f92b4; }
QLabel#metricValue { font-size:25px; font-weight:950; color:#fff; margin-top:3px; }
QProgressBar { background:#070f1e; border:1px solid #2a4166; border-radius:10px; height:19px; text-align:center; color:#fff; font-weight:850; }
QProgressBar::chunk { background:#4d80f5; border-radius:9px; }
QScrollBar:vertical { background:#060a13; width:10px; border:0; }
QScrollBar::handle:vertical { background:#2d4366; border-radius:5px; min-height:25px; }
QCheckBox { spacing:9px; font-weight:650; }
QCheckBox::indicator { width:18px; height:18px; border-radius:6px; border:1px solid #405579; background:#080f1d; }
QCheckBox::indicator:checked { background:#4b7ff2; border-color:#4b7ff2; }
QLabel#statusBadgeStopped,QLabel#statusBadgeRunning,QLabel#statusBadgePaused { border-radius:10px; padding:8px 11px; font-weight:900; }
QLabel#statusBadgeStopped { background:#172235; color:#afbdd3; border:1px solid #344866; }
QLabel#statusBadgeRunning { background:#063b30; color:#4be6b5; border:1px solid #0b9d78; }
QLabel#statusBadgePaused { background:#50300a; color:#ffd070; border:1px solid #b97412; }
QFrame#v11Hero { background:rgba(16,31,59,240); border:1px solid #3a5f99; border-radius:20px; }
QLabel#v11HeroTitle { font-size:21px; font-weight:950; color:#a5c5ff; letter-spacing:1px; }
QLabel#v11HeroSubtitle { color:#aab9d5; margin-top:3px; }
QLabel#v11Card { background:rgba(11,21,39,235); border:1px solid #294467; border-radius:15px; padding:15px; font-weight:850; color:#c0d2ef; }
'''

def apply_theme(app: QApplication): app.setStyleSheet(AWEC_DARK_QSS)
