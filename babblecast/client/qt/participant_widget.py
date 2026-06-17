"""Participant row with voice meter, Tap, and per-user controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QSlider,
    QWidget,
)

from babblecast.taps import get_tap_store


class ParticipantWidget(QWidget):
    volume_changed = pyqtSignal(str, float)
    mute_toggled = pyqtSignal(str, bool)
    tap_requested = pyqtSignal(str)
    name_clicked = pyqtSignal(str)
    reopen_tap_chat = pyqtSignal(str, str)

    def __init__(
        self,
        composite_key: str,
        name: str,
        is_self: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.composite_key = composite_key
        self._client_id = composite_key.split(":", 1)[-1]
        self._name = name
        self._is_self = is_self
        self._tapped = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self._name_label = QLabel(name)
        self._name_label.setMinimumWidth(100)
        self._name_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name_label.mousePressEvent = self._on_name_click  # type: ignore[method-assign]
        layout.addWidget(self._name_label)

        self._meter = QProgressBar()
        self._meter.setRange(0, 100)
        self._meter.setValue(0)
        self._meter.setTextVisible(False)
        self._meter.setFixedHeight(12)
        layout.addWidget(self._meter, stretch=1)

        if not is_self:
            self._tap_btn = QPushButton("Tap")
            self._tap_btn.setFixedWidth(44)
            self._tap_btn.clicked.connect(lambda: self.tap_requested.emit(self._client_id))
            layout.addWidget(self._tap_btn)

        self._mute_btn = QPushButton("Mute")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setFixedWidth(64)
        self._mute_btn.toggled.connect(self._on_mute)
        layout.addWidget(self._mute_btn)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 200)
        self._vol.setValue(100)
        self._vol.setFixedWidth(80)
        self._vol.valueChanged.connect(self._on_volume)
        layout.addWidget(self._vol)

        if is_self:
            self._mute_btn.setToolTip("Self mute — use PTT to talk while muted")

    def _on_name_click(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.name_clicked.emit(self._client_id)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_saved_taps_menu(event.globalPos())

    def _show_saved_taps_menu(self, pos) -> None:
        menu = QMenu(self)
        saved = get_tap_store().all_for_peer(self._client_id)
        if not saved:
            menu.addAction("(No saved taps)").setEnabled(False)
        for tap in saved:
            mark = "✓ " if tap.done else "○ "
            sub = menu.addMenu(f"{mark}{tap.reminder[:36]}")
            sub.addAction("Mark done" if not tap.done else "Mark undone").triggered.connect(
                lambda _c=False, t=tap: self._toggle_saved(t.save_id, not t.done)
            )
            sub.addAction("Reinsert to room chat").triggered.connect(
                lambda _c=False, sid=tap.save_id: self.reopen_tap_chat.emit(sid, self._client_id)
            )
        menu.exec(pos)

    def _toggle_saved(self, save_id: str, done: bool) -> None:
        get_tap_store().mark_done(save_id, done)

    def _on_mute(self, checked: bool) -> None:
        self.mute_toggled.emit(self.composite_key, checked)

    def _on_volume(self, value: int) -> None:
        self.volume_changed.emit(self.composite_key, value / 100.0)

    def set_tapped(self, tapped: bool) -> None:
        self._tapped = tapped
        self._refresh_name()

    def update_state(
        self,
        name: str,
        voice_level: float,
        muted: bool,
        speaking: bool,
        volume: float,
    ) -> None:
        self._name = name
        self._refresh_name(speaking, muted)
        self._meter.setValue(int(min(100, voice_level * 100)))
        self._mute_btn.blockSignals(True)
        self._mute_btn.setChecked(muted)
        self._mute_btn.blockSignals(False)
        self._vol.blockSignals(True)
        self._vol.setValue(int(volume * 100))
        self._vol.blockSignals(False)

    def _refresh_name(self, speaking: bool = False, muted: bool = False) -> None:
        suffix = " (you)" if self._is_self else ""
        tag = " 🔊" if speaking else ""
        mute_tag = " 🔇" if muted else ""
        tap_tag = " 👆" if self._tapped else ""
        highlight = "color: #e0af68; font-weight: bold;" if self._tapped else ""
        self._name_label.setStyleSheet(highlight)
        self._name_label.setText(f"{self._name}{suffix}{tap_tag}{tag}{mute_tag}")
