"""AWEC desktop command-center theme: compact, modern, readable and consistent."""
from PySide6.QtWidgets import QApplication

AWEC_DARK_QSS = '''
QMainWindow { background:#070a12; color:#eef2fb; font-family:'Segoe UI','SF Pro Display',Arial,sans-serif; font-size:13px; }
QWidget { color:#eef2fb; }
QFrame#sidebar { background:#0a0e18; border-right:1px solid #1c2536; }
QLabel#brandTitle { font-size:29px; font-weight:950; color:#a9c7ff; letter-spacing:3px; }
QLabel#brandSubtitle { font-size:11px; color:#7f8ba2; margin-bottom:8px; }
QLabel#pageHeader { font-size:28px; font-weight:900; color:#f7f9ff; }
QLabel#pageSubtitle { color:#8e9bb2; font-size:12px; margin-bottom:3px; }
QLabel#hint { color:#b7c5dc; padding:12px 14px; background:#0d1421; border:1px solid #202c40; border-radius:12px; }
QLabel#infoBadge { background:#101a2b; border:1px solid #2b4264; border-radius:10px; padding:8px 10px; color:#bfd3f5; font-weight:800; }
QPushButton#navButton { background:transparent; border:1px solid transparent; border-radius:10px; padding:10px 13px; text-align:left; font-weight:700; color:#8794aa; }
QPushButton#navButton:hover { background:#111a2a; color:#f3f6ff; border-color:#24334b; }
QPushButton#navButton:checked { background:#172844; border-color:#365b8e; color:#b5d0ff; }
QGroupBox { background:#0d131f; border:1px solid #1e2a3d; border-radius:13px; margin-top:12px; padding:18px 13px 12px; font-weight:800; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 7px; color:#a8c7ff; background:#0d131f; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit,QListWidget,QTextEdit,QTreeWidget,QTextBrowser { background:#080d16; border:1px solid #202d42; border-radius:9px; padding:8px 10px; color:#f2f5fb; selection-background-color:#315fae; }
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus,QPlainTextEdit:focus,QTextEdit:focus,QTreeWidget:focus,QTextBrowser:focus { border:1px solid #527fc5; background:#0a111d; }
QPushButton { background:#111a29; border:1px solid #283850; border-radius:9px; padding:8px 13px; font-weight:700; color:#eaf0fb; }
QPushButton:hover { background:#18263a; border-color:#4a6c9e; }
QPushButton:pressed { background:#0b111c; }
QPushButton:disabled { color:#5c687b; background:#0b1019; border-color:#182333; }
QPushButton#primaryButton { background:#3975e8; border:0; color:white; font-weight:900; padding:9px 16px; }
QPushButton#primaryButton:hover { background:#4f86f5; }
QPushButton#dangerButton { background:#b9364d; border:0; color:white; font-weight:900; }
QPushButton#warningButton { background:#9b6514; border:0; color:white; font-weight:900; }
QFrame#metricCard { background:#0d1421; border:1px solid #1e2c42; border-radius:12px; }
QLabel#metricTitle { font-size:10px; font-weight:800; color:#7f8da5; }
QLabel#metricValue { font-size:23px; font-weight:950; color:#f8faff; margin-top:2px; }
QProgressBar { background:#080d16; border:1px solid #202d42; border-radius:8px; height:16px; text-align:center; color:#fff; font-weight:800; }
QProgressBar::chunk { background:#4a82ef; border-radius:7px; }
QScrollBar:vertical { background:#070a11; width:8px; border:0; }
QScrollBar::handle:vertical { background:#293a55; border-radius:4px; min-height:24px; }
QScrollBar::handle:vertical:hover { background:#3b5274; }
QCheckBox { spacing:8px; font-weight:650; padding:2px 0; }
QCheckBox::indicator { width:17px; height:17px; border-radius:5px; border:1px solid #3a4d68; background:#080d16; }
QCheckBox::indicator:checked { background:#4a82ef; border-color:#4a82ef; }
QLabel#statusBadgeStopped,QLabel#statusBadgeRunning,QLabel#statusBadgePaused { border-radius:9px; padding:7px 10px; font-weight:900; }
QLabel#statusBadgeStopped { background:#141d2b; color:#abb7c9; border:1px solid #2c3b51; }
QLabel#statusBadgeRunning { background:#07382d; color:#55e4b7; border:1px solid #0b8e70; }
QLabel#statusBadgePaused { background:#49300b; color:#ffd47c; border:1px solid #a66e16; }
QFrame#v11Hero { background:#101a2a; border:1px solid #273c5c; border-radius:14px; }
QLabel#v11HeroTitle { font-size:19px; font-weight:950; color:#b3ceff; letter-spacing:.7px; }
QLabel#v11HeroSubtitle { color:#9aa9c2; margin-top:2px; }
QLabel#v11Card { background:#0c1421; border:1px solid #21324a; border-radius:11px; padding:12px; font-weight:800; color:#bfd0e8; }
QSplitter::handle { background:#1a2535; width:2px; }
QTreeWidget::item { padding:3px 2px; }
QTreeWidget::item:selected { background:#1a3154; border-radius:5px; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#0d1420; border:1px solid #1e2b3f; padding:8px 13px; margin-right:3px; border-radius:8px; color:#8e9bb0; }
QTabBar::tab:selected { background:#172844; color:#c4d8ff; border-color:#365b8e; }
'''

def apply_theme(app: QApplication):
    app.setStyleSheet(AWEC_DARK_QSS)
