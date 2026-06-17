"""More details dialog for a participant — volume, mute, tap, saved taps."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from babblecast.taps import SavedTap, get_tap_store


class ParticipantDetailsDialog(QDialog):
    def __init__(
        self,
        composite_key: str,
        name: str,
        server_label: str,
        *,
        is_self: bool,
        voice_level: float,
        muted: bool,
        speaking: bool,
        volume: float,
        tapped: bool,
        on_volume,
        on_mute,
        on_tap,
        on_reopen_tap,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._composite_key = composite_key
        self._client_id = composite_key.split(":", 1)[-1]
        self._on_volume = on_volume
        self._on_mute = on_mute
        self._on_tap = on_tap
        self._on_reopen_tap = on_reopen_tap
        self.setWindowTitle(f"{name}{' (you)' if is_self else ''}")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Server: {server_label}"))
        layout.addWidget(QLabel(f"Speaking: {'Yes' if speaking else 'No'}"))
        layout.addWidget(QLabel(f"Tap pending: {'Yes' if tapped else 'No'}"))

        meter_row = QHBoxLayout()
        meter_row.addWidget(QLabel("Voice level:"))
        meter = QProgressBar()
        meter.setRange(0, 100)
        meter.setValue(int(min(100, voice_level * 100)))
        meter.setTextVisible(False)
        meter.setFixedHeight(14)
        meter_row.addWidget(meter, stretch=1)
        layout.addLayout(meter_row)

        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Your volume:"))
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 200)
        self._vol.setValue(int(volume * 100))
        self._vol.valueChanged.connect(self._emit_volume)
        vol_row.addWidget(self._vol, stretch=1)
        layout.addLayout(vol_row)

        self._mute_btn = QPushButton("Unmute" if muted else "Mute")
        self._muted = muted
        self._mute_btn.clicked.connect(self._toggle_mute)
        layout.addWidget(self._mute_btn)

        if not is_self:
            tap_row = QHBoxLayout()
            tap_btn = QPushButton("Tap")
            tap_btn.clicked.connect(self._do_tap)
            tap_row.addWidget(tap_btn)
            if tapped:
                chat_btn = QPushButton("Tap chat")
                chat_btn.clicked.connect(self._do_tap_chat)
                tap_row.addWidget(chat_btn)
            layout.addLayout(tap_row)

        saved = get_tap_store().all_for_peer(self._client_id)
        if saved:
            saved_btn = QPushButton("Saved taps…")
            saved_btn.clicked.connect(lambda: self._saved_menu(saved_btn, saved))
            layout.addWidget(saved_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn:
            close_btn.clicked.connect(self.accept)
        layout.addWidget(buttons)

    def _emit_volume(self, value: int) -> None:
        self._on_volume(self._composite_key, value / 100.0)

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        self._mute_btn.setText("Unmute" if self._muted else "Mute")
        self._on_mute(self._composite_key, self._muted)

    def _do_tap(self) -> None:
        self._on_tap(self._client_id)
        self.accept()

    def _do_tap_chat(self) -> None:
        saved = get_tap_store().all_for_peer(self._client_id)
        for tap in saved:
            if not tap.done:
                self._on_reopen_tap(tap.save_id, self._client_id)
                self.accept()
                return

    def _saved_menu(self, widget, saved: list[SavedTap]) -> None:
        menu = QMenu(self)
        for tap in saved:
            mark = "✓ " if tap.done else "○ "
            sub = menu.addMenu(f"{mark}{tap.reminder[:36]}")
            sub.addAction("Mark done" if not tap.done else "Mark undone").triggered.connect(
                lambda _c=False, t=tap: get_tap_store().mark_done(t.save_id, not t.done)
            )
            sub.addAction("Reinsert to room chat").triggered.connect(
                lambda _c=False, sid=tap.save_id: self._on_reopen_tap(sid, self._client_id)
            )
        menu.exec(widget.mapToGlobal(widget.rect().bottomLeft()))
