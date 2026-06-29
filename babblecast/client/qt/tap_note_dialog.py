"""Compose and view/edit tap note dialogs (Qt desktop)."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from babblecast.taps import SavedTap, get_tap_store


class TapNoteComposeDialog(QDialog):
    """Add a new tap note — subject required, detail optional."""

    def __init__(
        self,
        *,
        default_subject: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("+ Tap Note")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Subject (required)"))
        self._subject = QLineEdit(default_subject)
        self._subject.setPlaceholderText("Short topic for this note")
        layout.addWidget(self._subject)
        layout.addWidget(QLabel("Details (optional)"))
        self._detail = QTextEdit()
        self._detail.setPlaceholderText("Extra context, if any")
        self._detail.setMinimumHeight(120)
        layout.addWidget(self._detail)

        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _save(self) -> None:
        if not self._subject.text().strip():
            QMessageBox.warning(self, "+ Tap Note", "Subject is required.")
            return
        self.accept()

    @property
    def subject(self) -> str:
        return self._subject.text().strip()

    @property
    def detail(self) -> str:
        return self._detail.toPlainText().strip()


class TapNoteViewDialog(QDialog):
    """Read-only tap note viewer with safe edit mode."""

    def __init__(
        self,
        tap: SavedTap,
        *,
        on_saved: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tap = tap
        self._on_saved = on_saved

        self.setWindowTitle("Tap Note")
        self.setMinimumSize(480, 320)

        root = QVBoxLayout(self)
        meta = QLabel(
            f"<span style='color:#565f89'>{tap.peer_name} · {tap.server_label}</span>"
        )
        root.addWidget(meta)
        root.addWidget(QLabel("Subject"))
        self._subject = QLineEdit(tap.display_subject)
        self._subject.setReadOnly(True)
        root.addWidget(self._subject)
        root.addWidget(QLabel("Details"))
        self._detail = QTextEdit(tap.detail)
        self._detail.setReadOnly(True)
        self._detail.setMinimumHeight(160)
        root.addWidget(self._detail)

        self._button_row = QHBoxLayout()
        root.addLayout(self._button_row)
        self._build_view_buttons()

    def _build_view_buttons(self) -> None:
        self._clear_buttons()
        edit = QPushButton("Edit")
        edit.clicked.connect(self._enter_edit)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        self._button_row.addWidget(edit)
        self._button_row.addStretch()
        self._button_row.addWidget(close)

    def _build_edit_buttons(self) -> None:
        self._clear_buttons()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._cancel_edit)
        save = QPushButton("Save")
        save.clicked.connect(lambda: self._commit(close_after=False))
        save_exit = QPushButton("Save & Exit")
        save_exit.clicked.connect(lambda: self._commit(close_after=True))
        self._button_row.addWidget(cancel)
        self._button_row.addStretch()
        self._button_row.addWidget(save)
        self._button_row.addWidget(save_exit)

    def _clear_buttons(self) -> None:
        while self._button_row.count():
            item = self._button_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _enter_edit(self) -> None:
        self._subject.setReadOnly(False)
        self._detail.setReadOnly(False)
        self._build_edit_buttons()

    def _cancel_edit(self) -> None:
        self._subject.setText(self._tap.display_subject)
        self._detail.setPlainText(self._tap.detail)
        self._subject.setReadOnly(True)
        self._detail.setReadOnly(True)
        self._build_view_buttons()

    def _commit(self, *, close_after: bool) -> None:
        subject = self._subject.text().strip()
        if not subject:
            QMessageBox.warning(self, "Tap Note", "Subject is required.")
            return
        detail = self._detail.toPlainText().strip()
        if not get_tap_store().update(self._tap.save_id, subject=subject, detail=detail):
            QMessageBox.warning(self, "Tap Note", "Could not save this note.")
            return
        self._tap.subject = subject
        self._tap.detail = detail
        if self._on_saved:
            self._on_saved()
        if close_after:
            self.accept()
            return
        self._cancel_edit()


class TapNoteRowLabel(QLabel):
    """List row label that opens the note on double-click."""

    double_clicked = pyqtSignal(str)

    def __init__(self, save_id: str, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self._save_id = save_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit(self._save_id)
        super().mouseDoubleClickEvent(event)
