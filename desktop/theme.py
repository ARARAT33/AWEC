"""AWEC modern desktop theme."""
from PySide6.QtWidgets import QApplication

AWEC_QSS = '''
QMainWindow, QWidget { background:#0b1020; color:#e8edf7; font-family:"Segoe UI"; font-size:13px; }
QFrame, QGroupBox { background:#11182b; border:1px solid #25304a; border-radius:14px; }
QGroupBox { margin-top:12px; padding:16px 10px 10px; font-weight:700; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 6px; color:#9fb2d8; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QListWidget { background:#0e1526; border:1px solid #2b3855; border-radius:10px; padding:9px; color:#f5f7fb; selection-background-color:#4f7cff; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border:1px solid #5c8dff; }
QPushButton { background:#1b2740; border:1px solid #334466; border-radius:10px; padding:10px 16px; font-weight:600; }
QPushButton:hover { background:#243657; }
QPushButton:pressed { background:#15213a; }
QPushButton#primary { background:#4f7cff; border:0; color:white; }
QPushButton#danger { background:#c84b5b; border:0; color:white; }
QLabel#title { font-size:25px; font-weight:800; }
QLabel#subtitle { color:#8190ad; }
QLabel#running { color:#54e39a; font-size:15px; font-weight:800; }
QLabel#metricValue { font-size:20px; font-weight:800; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#11182b; padding:11px 18px; margin-right:4px; border-radius:9px; color:#9eabc4; }
QTabBar::tab:selected { background:#243657; color:white; }
QCheckBox { spacing:8px; padding:5px; }
QProgressBar { background:#0e1526; border:0; border-radius:8px; height:12px; text-align:center; }
QProgressBar::chunk { background:#4f7cff; border-radius:8px; }
QScrollBar:vertical { background:#0b1020; width:10px; }
QScrollBar::handle:vertical { background:#34415e; border-radius:5px; }
'''

def apply_theme(app: QApplication):
    app.setStyleSheet(AWEC_QSS)
