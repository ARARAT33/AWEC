"""AWEC modern dark desktop UI theme stylesheet."""
from PySide6.QtWidgets import QApplication

AWEC_DARK_QSS = '''
QMainWindow {
    background-color: #0b1020;
    color: #e8edf7;
    font-family: 'Segoe UI', 'SF Pro Text', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
}

QWidget {
    background-color: transparent;
    color: #e8edf7;
}

QFrame#sidebar {
    background-color: #080d19;
    border-right: 1px solid #1c273e;
}

QLabel#brandTitle {
    font-size: 26px;
    font-weight: 900;
    color: #4f7cff;
    letter-spacing: 1px;
}

QLabel#brandSubtitle {
    font-size: 11px;
    color: #7a8aa8;
}

QLabel#pageHeader {
    font-size: 22px;
    font-weight: 800;
    color: #ffffff;
    margin-bottom: 8px;
}

QPushButton#navButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 11px 16px;
    text-align: left;
    font-weight: 600;
    font-size: 13px;
    color: #8f9fc2;
}

QPushButton#navButton:hover {
    background-color: #141d33;
    color: #ffffff;
}

QPushButton#navButton:checked {
    background-color: #1a2747;
    border: 1px solid #3655a0;
    color: #4f7cff;
}

QGroupBox {
    background-color: #11182b;
    border: 1px solid #23304c;
    border-radius: 12px;
    margin-top: 14px;
    padding: 16px 14px 14px 14px;
    font-weight: 700;
    font-size: 13px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #4f7cff;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QListWidget, QTextEdit {
    background-color: #0c1324;
    border: 1px solid #253350;
    border-radius: 8px;
    padding: 8px 10px;
    color: #f1f5fd;
    selection-background-color: #4f7cff;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #4f7cff;
    background-color: #0e172e;
}

QPushButton {
    background-color: #18233c;
    border: 1px solid #2c3c5f;
    border-radius: 8px;
    padding: 9px 16px;
    font-weight: 600;
    color: #e8edf7;
}

QPushButton:hover {
    background-color: #223254;
    border-color: #4f7cff;
}

QPushButton:pressed {
    background-color: #121b30;
}

QPushButton#primaryButton {
    background-color: #3b71fe;
    border: none;
    color: #ffffff;
    font-weight: 700;
}

QPushButton#primaryButton:hover {
    background-color: #5282ff;
}

QPushButton#dangerButton {
    background-color: #d3384c;
    border: none;
    color: #ffffff;
    font-weight: 700;
}

QPushButton#dangerButton:hover {
    background-color: #e64a5e;
}

QPushButton#warningButton {
    background-color: #d97706;
    border: none;
    color: #ffffff;
    font-weight: 700;
}

QPushButton#warningButton:hover {
    background-color: #f59e0b;
}

QFrame#metricCard {
    background-color: #11182b;
    border: 1px solid #202d48;
    border-radius: 12px;
    padding: 12px;
}

QLabel#metricTitle {
    font-size: 11px;
    font-weight: 600;
    color: #7f90b3;
    text-transform: uppercase;
}

QLabel#metricValue {
    font-size: 22px;
    font-weight: 800;
    color: #ffffff;
    margin-top: 4px;
}

QProgressBar {
    background-color: #0c1324;
    border: 1px solid #23304c;
    border-radius: 6px;
    height: 10px;
    text-align: center;
}

QProgressBar::chunk {
    background-color: #3b71fe;
    border-radius: 6px;
}

QScrollBar:vertical {
    background-color: #0b1020;
    width: 8px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #23304c;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3b71fe;
}

QCheckBox {
    spacing: 8px;
    font-weight: 500;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #2c3c5f;
    background-color: #0c1324;
}

QCheckBox::indicator:checked {
    background-color: #3b71fe;
    border-color: #3b71fe;
    image: url(none);
}

QLabel#statusBadgeRunning {
    background-color: #064e3b;
    color: #34d399;
    border: 1px solid #059669;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 800;
}

QLabel#statusBadgePaused {
    background-color: #78350f;
    color: #fbbf24;
    border: 1px solid #d97706;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 800;
}

QLabel#statusBadgeStopped {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 800;
}
'''

def apply_theme(app: QApplication):
    app.setStyleSheet(AWEC_DARK_QSS)
