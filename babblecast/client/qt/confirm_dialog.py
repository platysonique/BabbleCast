"""Reusable confirmation dialogs with optional “do not ask again”."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class ConfirmCheckboxDialog(QDialog):
    """Modal confirm/cancel with optional skip-future checkbox."""

    def __init__(
        self,
        title: str,
        message: str,
        *,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        confirm_style: str = "",
        checkbox_label: str = "Do not ask again",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        self._dont_ask = QCheckBox(checkbox_label)
        layout.addWidget(self._dont_ask)
        buttons = QHBoxLayout()
        cancel = QPushButton(cancel_label)
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(confirm_label)
        if confirm_style:
            confirm.setStyleSheet(confirm_style)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    @property
    def skip_future(self) -> bool:
        return self._dont_ask.isChecked()
