from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage


@dataclass
class Annotation:
    id: str
    kind: str
    page_index: int
    rect: QRectF
    text: str = ""
    font_size: float = 14.0
    image: QImage | None = None

    @classmethod
    def make_text(
        cls,
        page_index: int,
        rect: QRectF,
        text: str,
        font_size: float = 14.0,
    ) -> "Annotation":
        return cls(
            id=uuid4().hex,
            kind="text",
            page_index=page_index,
            rect=rect,
            text=text,
            font_size=font_size,
        )

    @classmethod
    def make_date(
        cls,
        page_index: int,
        rect: QRectF,
        text: str,
        font_size: float = 14.0,
    ) -> "Annotation":
        return cls(
            id=uuid4().hex,
            kind="date",
            page_index=page_index,
            rect=rect,
            text=text,
            font_size=font_size,
        )

    @classmethod
    def make_signature(
        cls,
        page_index: int,
        rect: QRectF,
        image: QImage,
    ) -> "Annotation":
        return cls(
            id=uuid4().hex,
            kind="signature",
            page_index=page_index,
            rect=rect,
            image=image,
        )
