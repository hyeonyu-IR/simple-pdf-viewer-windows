from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage

from office_pdf_signer.annotations.models import Annotation


@dataclass(frozen=True)
class PageSummary:
    index: int
    label: str
    width: float
    height: float


class PdfDocument:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._document = fitz.open(self.path)

    @property
    def page_count(self) -> int:
        return self._document.page_count

    def page_summaries(self) -> list[PageSummary]:
        summaries: list[PageSummary] = []
        for index in range(self.page_count):
            page = self._document.load_page(index)
            rect = page.rect
            summaries.append(
                PageSummary(
                    index=index,
                    label=f"Page {index + 1}",
                    width=rect.width,
                    height=rect.height,
                )
            )
        return summaries

    def render_page(self, page_index: int, zoom: float = 1.0) -> QImage:
        page = self._document.load_page(page_index)
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(
            pixmap.samples,
            pixmap.width,
            pixmap.height,
            pixmap.stride,
            QImage.Format_RGB888,
        ).copy()
        return image

    def render_page_to_width(self, page_index: int, target_width: int) -> QImage:
        page = self._document.load_page(page_index)
        page_width = max(page.rect.width, 1.0)
        zoom = max(target_width / page_width, 0.05)
        return self.render_page(page_index, zoom=zoom)

    def save_with_annotations(
        self,
        output_path: str | Path,
        annotations: list[Annotation],
    ) -> None:
        output_path = Path(output_path)
        exported = fitz.open(self.path)
        try:
            for annotation in annotations:
                page = exported.load_page(annotation.page_index)
                rect = fitz.Rect(
                    annotation.rect.x(),
                    annotation.rect.y(),
                    annotation.rect.x() + annotation.rect.width(),
                    annotation.rect.y() + annotation.rect.height(),
                )
                if annotation.kind in {"text", "date"}:
                    page.insert_textbox(
                        rect,
                        annotation.text,
                        fontsize=annotation.font_size,
                        fontname="helv",
                        color=(0, 0, 0),
                    )
                elif annotation.kind == "signature" and annotation.image is not None:
                    page.insert_image(rect, stream=self._qimage_to_png_bytes(annotation.image))
            exported.save(output_path)
        finally:
            exported.close()

    def _qimage_to_png_bytes(self, image: QImage) -> bytes:
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        return bytes(byte_array)

    def close(self) -> None:
        self._document.close()

    def __enter__(self) -> "PdfDocument":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
