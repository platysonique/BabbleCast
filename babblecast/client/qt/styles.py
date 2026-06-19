"""BabbleCast dark theme."""

STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1a1b26;
    color: #c0caf5;
    font-family: "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #3b4261;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #7aa2f7;
}
QListWidget, QTextEdit, QLineEdit, QComboBox {
    background-color: #24283b;
    border: 1px solid #414868;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #565f89;
}
QPushButton {
    background-color: #414868;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    color: #c0caf5;
    font-weight: 600;
}
QPushButton:hover { background-color: #565f89; }
QPushButton:pressed { background-color: #7aa2f7; color: #1a1b26; }
QPushButton:checked, QPushButton#pttActive {
    background-color: #9ece6a;
    color: #1a1b26;
}
QPushButton#danger:checked { background-color: #f7768e; }
QPushButton#drawerToggle {
    background: transparent;
    padding: 2px 0;
    font-size: 11px;
    color: #7aa2f7;
    border-radius: 4px;
}
QPushButton#drawerToggle:hover { background-color: #24283b; }
QSlider::groove:horizontal {
    height: 6px;
    background: #414868;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -4px 0;
    background: #7aa2f7;
    border-radius: 7px;
}
QSlider::handle:vertical {
    height: 14px;
    margin: 0 -4px;
    background: #7aa2f7;
    border-radius: 7px;
}
QSlider::groove:vertical {
    width: 6px;
    background: #414868;
    border-radius: 3px;
}
QDial#volumeKnob {
    background-color: #24283b;
    color: #7aa2f7;
}
QDial#volumeKnob::groove {
    background: #1a1b26;
    border: 1px solid #414868;
    border-radius: 32px;
}
QDial#volumeKnob::handle {
    background: #ffffff;
    border: 2px solid #e0e0e0;
    border-radius: 6px;
    width: 12px;
    height: 12px;
}
QProgressBar {
    border: none;
    border-radius: 4px;
    background: #24283b;
    text-align: center;
    max-height: 10px;
}
QProgressBar::chunk {
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #9ece6a, stop:0.7 #e0af68, stop:1 #f7768e);
}
QLabel#title { font-size: 18px; font-weight: bold; color: #7aa2f7; }
QLabel#status { color: #9ece6a; }
QScrollBar:vertical {
    background: #24283b;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #565f89;
    border-radius: 5px;
    min-height: 24px;
}
"""
