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
    _TEXT_HORIZONTAL_PADDING = 4.0
    _TEXT_VERTICAL_PADDING = 2.0
    _TEXT_LINE_HEIGHT_FACTOR = 1.25

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
                    page.draw_rect(rect, color=None, fill=(1, 1, 1), width=0)
                    page.insert_textbox(
                        self._bottom_aligned_text_rect(annotation, rect),
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

    def _bottom_aligned_text_rect(self, annotation: Annotation, rect: fitz.Rect) -> fitz.Rect:
        content_width = max(rect.width - (self._TEXT_HORIZONTAL_PADDING * 2), 1.0)
        line_count = self._wrapped_line_count(annotation.text or " ", annotation.font_size, content_width)
        text_height = min(
            max(line_count * annotation.font_size * self._TEXT_LINE_HEIGHT_FACTOR, annotation.font_size),
            max(rect.height - (self._TEXT_VERTICAL_PADDING * 2), 1.0),
        )
        y0 = max(
            rect.y0 + self._TEXT_VERTICAL_PADDING,
            rect.y1 - text_height - self._TEXT_VERTICAL_PADDING,
        )
        return fitz.Rect(
            rect.x0 + self._TEXT_HORIZONTAL_PADDING,
            y0,
            rect.x1 - self._TEXT_HORIZONTAL_PADDING,
            rect.y1 - self._TEXT_VERTICAL_PADDING,
        )

    def _wrapped_line_count(self, text: str, font_size: float, max_width: float) -> int:
        font = fitz.Font(fontname="helv")
        line_count = 0
        for paragraph in text.splitlines() or [" "]:
            words = paragraph.split()
            if not words:
                line_count += 1
                continue
            current = words[0]
            for word in words[1:]:
                candidate = f"{current} {word}"
                if font.text_length(candidate, fontsize=font_size) <= max_width:
                    current = candidate
                else:
                    line_count += 1
                    current = word
            line_count += 1
        return max(line_count, 1)

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
