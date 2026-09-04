"""AWEC desktop theme: clean light workspace with roomy, responsive controls."""
from PySide6.QtWidgets import QApplication

AWEC_LIGHT_QSS = '''
QMainWindow { background:#f5f7fb; color:#172033; font-family:'Segoe UI','SF Pro Display',Arial,sans-serif; font-size:13px; }
QWidget { color:#172033; }
QFrame#sidebar { background:#ffffff; border-right:1px solid #dfe4ec; }
QLabel#brandTitle { font-size:28px; font-weight:900; color:#172033; letter-spacing:2px; }
QLabel#brandSubtitle { font-size:11px; color:#687386; margin-bottom:10px; }
QLabel#pageHeader { font-size:27px; font-weight:900; color:#141b2a; }
QLabel#pageSubtitle { color:#687386; font-size:12px; margin-bottom:5px; }
QLabel#hint { color:#465268; padding:12px 14px; background:#f8fafc; border:1px solid #dfe5ee; border-radius:8px; }
QLabel#infoBadge { background:#eef4ff; border:1px solid #cddcf7; border-radius:8px; padding:7px 10px; color:#315a9a; font-weight:800; }
QPushButton#navButton { background:transparent; border:1px solid transparent; border-radius:7px; padding:10px 12px; text-align:left; font-weight:700; color:#5f6b7d; }
QPushButton#navButton:hover { background:#f1f4f8; color:#172033; border-color:#e1e6ee; }
QPushButton#navButton:checked { background:#eaf2ff; border-color:#c9daf8; color:#2457a6; }
QGroupBox { background:#ffffff; border:1px solid #dfe4ec; border-radius:9px; margin-top:12px; padding:18px 14px 13px; font-weight:800; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 7px; color:#2b4f86; background:#ffffff; }
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox,QPlainTextEdit,QListWidget,QTextEdit,QTreeWidget,QTextBrowser { background:#ffffff; border:1px solid #cfd6e2; border-radius:7px; padding:8px 10px; color:#172033; selection-background-color:#dce9ff; selection-color:#172033; }
QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus,QComboBox:focus,QPlainTextEdit:focus,QTextEdit:focus,QTreeWidget:focus,QTextBrowser:focus { border:1px solid #6b96d8; }
QPushButton { background:#ffffff; border:1px solid #cfd6e2; border-radius:7px; padding:8px 13px; font-weight:700; color:#273246; min-height:18px; }
QPushButton:hover { background:#f4f7fb; border-color:#aebbd0; }
QPushButton:pressed { background:#e9eef5; }
QPushButton:disabled { color:#9aa3b2; background:#f2f4f7; border-color:#e1e5eb; }
QPushButton#primaryButton { background:#2f6fce; border:1px solid #2f6fce; color:white; font-weight:900; padding:9px 17px; }
QPushButton#primaryButton:hover { background:#245eaf; }
QPushButton#dangerButton { background:#c53b4d; border:1px solid #c53b4d; color:white; font-weight:900; }
QPushButton#warningButton { background:#b87816; border:1px solid #b87816; color:white; font-weight:900; }
QFrame#metricCard { background:#ffffff; border:1px solid #dfe4ec; border-radius:9px; }
QLabel#metricTitle { font-size:10px; font-weight:800; color:#748095; }
QLabel#metricValue { font-size:23px; font-weight:900; color:#182236; margin-top:2px; }
QProgressBar { background:#edf0f5; border:1px solid #d5dbe5; border-radius:7px; height:16px; text-align:center; color:#263248; font-weight:800; }
QProgressBar::chunk { background:#4b82d1; border-radius:6px; }
QScrollBar:vertical { background:#f5f7fb; width:9px; border:0; }
QScrollBar::handle:vertical { background:#c5ccd8; border-radius:4px; min-height:26px; }
QScrollBar::handle:vertical:hover { background:#aeb8c8; }
QCheckBox { spacing:8px; font-weight:650; padding:3px 0; }
QCheckBox::indicator { width:17px; height:17px; border-radius:4px; border:1px solid #aeb8c8; background:#ffffff; }
QCheckBox::indicator:checked { background:#3975c9; border-color:#3975c9; }
QLabel#statusBadgeStopped,QLabel#statusBadgeRunning,QLabel#statusBadgePaused { border-radius:7px; padding:7px 10px; font-weight:900; }
QLabel#statusBadgeStopped { background:#eef1f5; color:#5c6778; border:1px solid #d8dee7; }
QLabel#statusBadgeRunning { background:#e7f6ee; color:#177346; border:1px solid #b8e1ca; }
QLabel#statusBadgePaused { background:#fff4dd; color:#8a5b0b; border:1px solid #edd39a; }
QFrame#v11Hero { background:#ffffff; border:1px solid #dfe4ec; border-radius:9px; }
QLabel#v11HeroTitle { font-size:19px; font-weight:900; color:#1c2b43; letter-spacing:.5px; }
QLabel#v11HeroSubtitle { color:#687386; margin-top:2px; }
QLabel#v11Card { background:#ffffff; border:1px solid #dfe4ec; border-radius:8px; padding:12px; font-weight:800; color:#43516a; }
QSplitter::handle { background:#d8dee8; width:3px; }
QTreeWidget::item { padding:4px 2px; }
QTreeWidget::item:selected { background:#e5efff; color:#1c4e91; border-radius:4px; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#f1f4f8; border:1px solid #dce2eb; padding:8px 13px; margin-right:3px; border-radius:6px; color:#667287; }
QTabBar::tab:selected { background:#eaf2ff; color:#2457a6; border-color:#c9daf8; }
QToolTip { background:#ffffff; color:#172033; border:1px solid #cfd6e2; padding:5px; }
'''

def apply_theme(app: QApplication):
    app.setStyleSheet(AWEC_LIGHT_QSS)
