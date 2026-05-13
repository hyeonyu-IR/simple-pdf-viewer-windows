from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QListWidget


class ThumbnailListWidget(QListWidget):
    _THUMB_ITEM_SIZE = QSize(156, 112)

    sidebar_width_changed = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSpacing(8)
        self.setResizeMode(QListWidget.Fixed)
        self.setUniformItemSizes(False)
        self.setViewMode(QListWidget.ListMode)
        self.setMovement(QListWidget.Static)
        self.setFrameShape(QListWidget.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setContentsMargins(0, 0, 0, 0)
        self.setWrapping(False)
        self.verticalScrollBar().setSingleStep(24)
        self.setIconSize(QSize(64, 88))

    def resizeEvent(self, event) -> None:  # pragma: no cover - Qt event
        super().resizeEvent(event)
        self.sidebar_width_changed.emit(self.viewport().width())
