from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from office_pdf_signer.annotations.models import Annotation
from office_pdf_signer.services.pdf_document import PageSummary, PdfDocument


class PageCanvas(QWidget):
    annotation_selected = Signal(object)
    annotation_added = Signal(object)
    annotation_changed = Signal(object)
    _TEXT_MIN_WIDTH = 80.0
    _TEXT_HORIZONTAL_PADDING = 16.0
    _TEXT_VERTICAL_PADDING = 10.0
    _TEXT_RIGHT_MARGIN = 12.0

    def __init__(
        self,
        page_summary: PageSummary,
        zoom: float,
        page_image: QImage,
        annotations: list[Annotation],
        placement_factory: Callable[[int, QPointF], Annotation | None] | None,
        selected_annotation_id: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._page_summary = page_summary
        self._zoom = zoom
        self._page_image = page_image
        self._annotations = annotations
        self._placement_factory = placement_factory
        self._selected_annotation_id = selected_annotation_id
        self._dragging_annotation_id: str | None = None
        self._resizing_annotation_id: str | None = None
        self._drag_offset = QPointF()
        self.setMinimumSize(page_image.width(), page_image.height())
        self.resize(page_image.width(), page_image.height())
        self.setStyleSheet("background: white; border: 1px solid #3c3c3c;")

    def paintEvent(self, event) -> None:  # pragma: no cover - Qt painting
        painter = QPainter(self)
        painter.drawImage(0, 0, self._page_image)
        painter.setRenderHint(QPainter.Antialiasing)
        for annotation in self._annotations:
            self._draw_annotation(painter, annotation)
        painter.end()
        super().paintEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # pragma: no cover - Qt event
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        page_point = self._widget_to_page(event.position())
        if self._placement_factory is not None:
            annotation = self._placement_factory(self._page_summary.index, page_point)
            if annotation is not None:
                self.annotation_added.emit(annotation)
            return

        annotation = self._annotation_at(event.position())
        if annotation is None:
            self.annotation_selected.emit(None)
            return

        if self._is_resize_handle_hit(annotation, event.position()):
            self._resizing_annotation_id = annotation.id
            self.annotation_selected.emit(annotation)
            return

        self._dragging_annotation_id = annotation.id
        self._drag_offset = page_point - annotation.rect.topLeft()
        self.annotation_selected.emit(annotation)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # pragma: no cover - Qt event
        if not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return

        if self._resizing_annotation_id is not None:
            annotation = self._find_annotation(self._resizing_annotation_id)
            if annotation is None:
                return
            self._resize_annotation(annotation, event.position())
            self.annotation_selected.emit(annotation)
            self.update()
            return

        if self._dragging_annotation_id is None:
            super().mouseMoveEvent(event)
            return

        annotation = self._find_annotation(self._dragging_annotation_id)
        if annotation is None:
            return

        next_top_left = self._widget_to_page(event.position()) - self._drag_offset
        annotation.rect = self._clamp_rect(QRectF(next_top_left, annotation.rect.size()))
        self.annotation_selected.emit(annotation)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # pragma: no cover - Qt event
        active_id = self._dragging_annotation_id or self._resizing_annotation_id
        if active_id is not None:
            annotation = self._find_annotation(active_id)
            if annotation is not None:
                self.annotation_changed.emit(annotation)
        self._dragging_annotation_id = None
        self._resizing_annotation_id = None
        super().mouseReleaseEvent(event)

    def update_page_state(
        self,
        zoom: float,
        page_image: QImage,
        annotations: list[Annotation],
        placement_factory: Callable[[int, QPointF], Annotation | None] | None,
        selected_annotation_id: str | None,
    ) -> None:
        self._zoom = zoom
        self._page_image = page_image
        self._annotations = annotations
        self._placement_factory = placement_factory
        self._selected_annotation_id = selected_annotation_id
        self.setMinimumSize(page_image.width(), page_image.height())
        self.resize(page_image.width(), page_image.height())
        self.update()

    def set_selected_annotation_id(self, annotation_id: str | None) -> None:
        self._selected_annotation_id = annotation_id
        self.update()

    def _draw_annotation(self, painter: QPainter, annotation: Annotation) -> None:
        rect = self._page_to_widget_rect(annotation.rect)
        if annotation.kind in {"text", "date"}:
            painter.fillRect(rect, QColor("#ffffff"))
            font = QFont("Segoe UI", max(8, int(annotation.font_size * self._zoom)))
            painter.setFont(font)
            painter.setPen(QColor("#0f1720"))
            text_rect = rect.adjusted(
                4.0 * self._zoom,
                2.0 * self._zoom,
                -4.0 * self._zoom,
                -2.0 * self._zoom,
            )
            painter.drawText(
                text_rect,
                Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap,
                annotation.text,
            )
        elif annotation.kind == "signature" and annotation.image is not None:
            painter.drawImage(rect, annotation.image)

        if annotation.id == self._selected_annotation_id:
            pen = QPen(QColor("#2470ff"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            if annotation.kind in {"signature", "text", "date"}:
                handle = self._resize_handle_rect(rect)
                painter.fillRect(handle, QColor("#2470ff"))

    def _annotation_at(self, widget_pos: QPointF) -> Annotation | None:
        for annotation in reversed(self._annotations):
            if self._page_to_widget_rect(annotation.rect).contains(widget_pos):
                return annotation
        return None

    def _find_annotation(self, annotation_id: str) -> Annotation | None:
        for annotation in self._annotations:
            if annotation.id == annotation_id:
                return annotation
        return None

    def _widget_to_page(self, point: QPointF) -> QPointF:
        return QPointF(point.x() / self._zoom, point.y() / self._zoom)

    def _page_to_widget_rect(self, rect: QRectF) -> QRectF:
        return QRectF(
            rect.x() * self._zoom,
            rect.y() * self._zoom,
            rect.width() * self._zoom,
            rect.height() * self._zoom,
        )

    def _clamp_rect(self, rect: QRectF) -> QRectF:
        max_x = max(self._page_summary.width - rect.width(), 0.0)
        max_y = max(self._page_summary.height - rect.height(), 0.0)
        return QRectF(
            min(max(rect.x(), 0.0), max_x),
            min(max(rect.y(), 0.0), max_y),
            rect.width(),
            rect.height(),
        )

    def _is_resize_handle_hit(self, annotation: Annotation, widget_pos: QPointF) -> bool:
        if annotation.kind not in {"signature", "text", "date"} or annotation.id != self._selected_annotation_id:
            return False
        return self._resize_handle_rect(self._page_to_widget_rect(annotation.rect)).contains(widget_pos)

    def _resize_handle_rect(self, rect: QRectF) -> QRectF:
        handle_size = 10.0
        return QRectF(
            rect.right() - handle_size,
            rect.bottom() - handle_size,
            handle_size,
            handle_size,
        )

    def _resize_annotation(self, annotation: Annotation, widget_pos: QPointF) -> None:
        if annotation.kind in {"text", "date"}:
            self._resize_text_annotation(annotation, widget_pos)
            return
        self._resize_signature_annotation(annotation, widget_pos)

    def _resize_signature_annotation(self, annotation: Annotation, widget_pos: QPointF) -> None:
        if annotation.image is None:
            return
        top_left = annotation.rect.topLeft()
        page_point = self._widget_to_page(widget_pos)
        raw_width = max(page_point.x() - top_left.x(), 24.0)
        aspect_ratio = annotation.image.height() / max(annotation.image.width(), 1)
        width = raw_width
        height = width * aspect_ratio

        max_width = max(self._page_summary.width - top_left.x(), 24.0)
        max_height = max(self._page_summary.height - top_left.y(), 12.0)
        if height > max_height:
            scale = max_height / max(height, 1.0)
            width *= scale
            height = max_height
        if width > max_width:
            scale = max_width / max(width, 1.0)
            width = max_width
            height *= scale

        annotation.rect = QRectF(top_left.x(), top_left.y(), max(width, 24.0), max(height, 12.0))

    def _resize_text_annotation(self, annotation: Annotation, widget_pos: QPointF) -> None:
        top_left = annotation.rect.topLeft()
        page_point = self._widget_to_page(widget_pos)
        page_width = self._page_summary.width
        available_width = max(
            page_width - top_left.x() - self._TEXT_RIGHT_MARGIN,
            self._TEXT_MIN_WIDTH,
        )
        target_width = min(
            max(page_point.x() - top_left.x(), self._TEXT_MIN_WIDTH),
            available_width,
        )
        size = self._measure_text_annotation_size(
            annotation.text,
            annotation.font_size,
            target_width,
        )
        annotation.rect = self._clamp_rect(
            QRectF(top_left.x(), top_left.y(), size.width(), size.height())
        )

    def _measure_text_annotation_size(
        self,
        text: str,
        font_size: float,
        width: float,
    ) -> QRectF:
        font = QFont("Segoe UI")
        font.setPointSizeF(font_size)
        metrics = QFontMetricsF(font)
        wrapped_text = text or " "
        text_box = metrics.boundingRect(
            QRectF(
                0.0,
                0.0,
                max(width - self._TEXT_HORIZONTAL_PADDING, 1.0),
                10000.0,
            ),
            Qt.TextWordWrap,
            wrapped_text,
        )
        height = max(
            font_size * 1.8,
            text_box.height() + self._TEXT_VERTICAL_PADDING,
        )
        return QRectF(0.0, 0.0, width, height)


class PdfViewer(QWidget):
    current_page_changed = Signal(int)
    zoom_changed = Signal(float)
    annotation_selected = Signal(object)
    annotation_added = Signal(object)
    annotation_deleted = Signal(str)
    annotation_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._zoom = 1.0
        self._document: PdfDocument | None = None
        self._page_summaries: list[PageSummary] = []
        self._page_canvases: list[PageCanvas] = []
        self._current_page_index = 0
        self._annotations_by_page: dict[int, list[Annotation]] = {}
        self._selected_annotation_id: str | None = None
        self._placement_factory: Callable[[int, QPointF], Annotation | None] | None = None
        self._build_ui()

    @property
    def zoom(self) -> float:
        return self._zoom

    def fit_to_page_zoom(self) -> float:
        if not self._page_summaries:
            return self._zoom
        viewport = self._scroll_area.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return self._zoom
        summary = self._page_summaries[0]
        available_width = max(viewport.width() - 76, 1)
        available_height = max(viewport.height() - 96, 1)
        return max(
            0.25,
            min(
                available_width / max(summary.width, 1.0),
                available_height / max(summary.height, 1.0),
                4.0,
            ),
        )

    def fit_to_width_zoom(self) -> float:
        if not self._page_summaries:
            return self._zoom
        viewport = self._scroll_area.viewport().size()
        if viewport.width() <= 0:
            return self._zoom
        summary = self._page_summaries[0]
        available_width = max(viewport.width() - 76, 1)
        return max(0.25, min(available_width / max(summary.width, 1.0), 4.0))

    def fit_to_height_zoom(self) -> float:
        if not self._page_summaries:
            return self._zoom
        viewport = self._scroll_area.viewport().size()
        if viewport.height() <= 0:
            return self._zoom
        summary = self._page_summaries[0]
        available_height = max(viewport.height() - 96, 1)
        return max(0.25, min(available_height / max(summary.height, 1.0), 4.0))

    def has_valid_viewport(self) -> bool:
        viewport = self._scroll_area.viewport().size()
        return viewport.width() > 0 and viewport.height() > 0

    def set_document(self, document: PdfDocument, page_summaries: list[PageSummary]) -> None:
        self._document = document
        self._page_summaries = page_summaries
        self._current_page_index = 0
        self._annotations_by_page = {summary.index: [] for summary in page_summaries}
        self._selected_annotation_id = None
        self._placement_factory = None
        self._render_all_pages()
        self._empty_label.hide()
        self._scroll_area.show()
        self.scroll_to_page(0)
        self.current_page_changed.emit(0)

    def clear_document(self, message: str = "Open a PDF to start.") -> None:
        self._document = None
        self._page_summaries = []
        self._page_canvases = []
        self._current_page_index = 0
        self._annotations_by_page = {}
        self._selected_annotation_id = None
        self._placement_factory = None
        self._clear_page_widgets()
        self._scroll_area.hide()
        self._empty_label.setText(message)
        self._empty_label.show()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.25, min(zoom, 4.0))
        self.zoom_changed.emit(self._zoom)
        if self._document is None:
            return
        current_page_index = self._current_page_index
        self._render_all_pages()
        QTimer.singleShot(0, lambda: self.scroll_to_page(current_page_index))

    def begin_annotation_placement(
        self,
        placement_factory: Callable[[int, QPointF], Annotation | None],
    ) -> None:
        self._placement_factory = placement_factory
        self._update_canvas_modes()

    def cancel_annotation_placement(self) -> None:
        self._placement_factory = None
        self._update_canvas_modes()

    def refresh_annotations(self) -> None:
        self._update_canvas_modes()

    def annotations(self) -> list[Annotation]:
        all_annotations: list[Annotation] = []
        for annotations in self._annotations_by_page.values():
            all_annotations.extend(annotations)
        return all_annotations

    def remove_selected_annotation(self) -> bool:
        if self._selected_annotation_id is None:
            return False
        for annotations in self._annotations_by_page.values():
            for annotation in list(annotations):
                if annotation.id == self._selected_annotation_id:
                    annotations.remove(annotation)
                    self._selected_annotation_id = None
                    self._render_all_pages()
                    self.annotation_deleted.emit(annotation.id)
                    self.annotation_selected.emit(None)
                    return True
        return False

    def scroll_to_page(self, page_index: int) -> None:
        if page_index < 0 or page_index >= len(self._page_canvases):
            return
        self._scroll_area.ensureWidgetVisible(self._page_canvases[page_index], 16, 16)
        self._set_current_page(page_index)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._empty_label = QLabel("Open a PDF to start.", self)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            "border: 1px solid #3c3c3c; background: #252526; color: #9da5b4;"
        )

        self._content_widget = QWidget(self)
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(24, 24, 24, 24)
        self._content_layout.setSpacing(18)
        self._content_layout.addStretch()
        self._content_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self._content_widget.setStyleSheet("background: #1e1e1e;")

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setWidget(self._content_widget)
        self._scroll_area.setStyleSheet(
            "QScrollArea { background: #1e1e1e; border: none; }"
            "QWidget { background: #1e1e1e; }"
        )
        self._scroll_area.viewport().setStyleSheet("background: #1e1e1e;")
        self._scroll_area.verticalScrollBar().valueChanged.connect(
            self._handle_scroll_changed
        )
        self._scroll_area.hide()

        layout.addWidget(self._empty_label)
        layout.addWidget(self._scroll_area)

    def _render_all_pages(self) -> None:
        if self._document is None:
            return
        self._clear_page_widgets()
        self._page_canvases = []
        for summary in self._page_summaries:
            canvas = self._create_page_canvas(summary)
            self._page_canvases.append(canvas)
            self._content_layout.insertWidget(self._content_layout.count() - 1, canvas)

    def _create_page_canvas(self, summary: PageSummary) -> PageCanvas:
        image = self._document.render_page(summary.index, zoom=self._zoom)
        canvas = PageCanvas(
            page_summary=summary,
            zoom=self._zoom,
            page_image=image,
            annotations=self._annotations_by_page.setdefault(summary.index, []),
            placement_factory=self._placement_factory,
            selected_annotation_id=self._selected_annotation_id,
            parent=self._content_widget,
        )
        canvas.annotation_selected.connect(self._handle_annotation_selected)
        canvas.annotation_added.connect(self._handle_annotation_added)
        canvas.annotation_changed.connect(self._handle_annotation_changed)
        return canvas

    def _update_canvas_modes(self) -> None:
        if self._document is None:
            return
        for canvas, summary in zip(self._page_canvases, self._page_summaries, strict=False):
            canvas.update_page_state(
                zoom=self._zoom,
                page_image=self._document.render_page(summary.index, zoom=self._zoom),
                annotations=self._annotations_by_page.setdefault(summary.index, []),
                placement_factory=self._placement_factory,
                selected_annotation_id=self._selected_annotation_id,
            )

    def _clear_page_widgets(self) -> None:
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _handle_scroll_changed(self) -> None:
        if not self._page_canvases:
            return
        viewport_center = (
            self._scroll_area.verticalScrollBar().value()
            + self._scroll_area.viewport().height() / 2
        )
        best_index = 0
        best_distance = float("inf")
        for index, canvas in enumerate(self._page_canvases):
            distance = abs((canvas.y() + canvas.height() / 2) - viewport_center)
            if distance < best_distance:
                best_distance = distance
                best_index = index
        self._set_current_page(best_index)

    def _handle_annotation_selected(self, annotation: Annotation | None) -> None:
        self._selected_annotation_id = None if annotation is None else annotation.id
        for canvas in self._page_canvases:
            canvas.set_selected_annotation_id(self._selected_annotation_id)
        self.annotation_selected.emit(annotation)

    def _handle_annotation_added(self, annotation: Annotation) -> None:
        self._annotations_by_page.setdefault(annotation.page_index, []).append(annotation)
        self._selected_annotation_id = annotation.id
        self._placement_factory = None
        self._render_all_pages()
        self.annotation_added.emit(annotation)
        self.annotation_selected.emit(annotation)

    def _handle_annotation_changed(self, annotation: Annotation) -> None:
        self.annotation_changed.emit(annotation)

    def _set_current_page(self, page_index: int) -> None:
        if page_index == self._current_page_index:
            return
        self._current_page_index = page_index
        self.current_page_changed.emit(page_index)
