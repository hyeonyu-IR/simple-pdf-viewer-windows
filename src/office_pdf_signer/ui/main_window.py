from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QFontMetricsF, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from office_pdf_signer.annotations.models import Annotation
from office_pdf_signer.services.pdf_document import PageSummary, PdfDocument
from office_pdf_signer.ui.thumbnail_list import ThumbnailListWidget
from office_pdf_signer.viewer.pdf_viewer import PdfViewer


class IntStepper(QWidget):
    valueChanged = QTimer.timeout  # placeholder to satisfy type checker

    def __init__(
        self,
        minimum: int,
        maximum: int,
        step: int = 1,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        from PySide6.QtCore import Signal

        cls = self.__class__
        if not hasattr(cls, "valueChanged") or not isinstance(getattr(cls, "valueChanged"), Signal):
            pass
        self._minimum = minimum
        self._maximum = maximum
        self._step = step
        self._suffix = suffix
        self._value = minimum
        self._build_ui()
        self._sync_text()

    from PySide6.QtCore import Signal as _Signal
    valueChanged = _Signal(int)

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        clamped = max(self._minimum, min(self._maximum, int(value)))
        if clamped == self._value:
            self._sync_text()
            return
        self._value = clamped
        self._sync_text()
        self.valueChanged.emit(self._value)

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = minimum
        self._maximum = maximum
        self.setValue(self._value)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._minus_button = QPushButton("-", self)
        self._minus_button.setObjectName("stepperButton")
        self._minus_button.clicked.connect(lambda: self.setValue(self._value - self._step))

        self._line_edit = QLineEdit(self)
        self._line_edit.setObjectName("stepperEdit")
        self._line_edit.setAlignment(Qt.AlignCenter)
        self._line_edit.editingFinished.connect(self._commit_text)

        self._plus_button = QPushButton("+", self)
        self._plus_button.setObjectName("stepperButton")
        self._plus_button.clicked.connect(lambda: self.setValue(self._value + self._step))

        layout.addWidget(self._minus_button)
        layout.addWidget(self._line_edit, 1)
        layout.addWidget(self._plus_button)

    def _sync_text(self) -> None:
        self._line_edit.setText(f"{self._value}{self._suffix}")

    def _commit_text(self) -> None:
        raw = self._line_edit.text().replace(self._suffix, "").strip()
        try:
            value = int(raw)
        except ValueError:
            self._sync_text()
            return
        self.setValue(value)


class ZoomPercentDialog(QDialog):
    def __init__(self, current_percent: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set Zoom")
        layout = QVBoxLayout(self)
        prompt = QLabel("Zoom percent:", self)
        self._stepper = IntStepper(25, 400, step=5, suffix="%", parent=self)
        self._stepper.setValue(current_percent)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(prompt)
        layout.addWidget(self._stepper)
        layout.addWidget(buttons)

    def value(self) -> int:
        return self._stepper.value()


class MainWindow(QMainWindow):
    _PAGE_PANEL_WIDTH = 190
    _FIT_MODE_PAGE = "page"
    _FIT_MODE_WIDTH = "width"
    _FIT_MODE_HEIGHT = "height"

    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings()
        self._document: PdfDocument | None = None
        self._page_summaries: list[PageSummary] = []
        self._current_page_index = 0
        self._thumbnail_width = 112
        self._fit_mode: str | None = self._FIT_MODE_PAGE
        self._selected_annotation: Annotation | None = None
        self._updating_properties = False
        self._has_unsaved_changes = False
        self._save_path: Path | None = None
        self._signature_image: QImage | None = None
        self._signature_path: Path | None = None
        self._fit_refresh_timer = QTimer(self)
        self._fit_refresh_timer.setSingleShot(True)
        self._fit_refresh_timer.timeout.connect(self._apply_fit_mode)
        self.setWindowTitle("Office PDF Signer")
        self.resize(1400, 900)
        self._build_actions()
        self._build_menu_bar()
        self._build_layout()
        self._build_status_bar()
        self._apply_window_style()
        self._restore_window_state()
        self._restore_signature_image()
        self._update_action_state()
        self._update_zoom_label()
        self._update_selection_summary()
        QTimer.singleShot(0, self._restore_last_file)

    def _build_actions(self) -> None:
        self._open_action = QAction("Open", self)
        self._open_action.triggered.connect(self.open_pdf)
        self._close_action = QAction("Close PDF", self)
        self._close_action.triggered.connect(self._close_document)

        self._zoom_out_action = QAction("Zoom Out", self)
        self._zoom_out_action.triggered.connect(lambda: self._change_zoom(-0.1))
        self._zoom_in_action = QAction("Zoom In", self)
        self._zoom_in_action.triggered.connect(lambda: self._change_zoom(0.1))
        self._set_zoom_action = QAction("Set Zoom...", self)
        self._set_zoom_action.triggered.connect(self._prompt_zoom_percent)
        self._fit_page_action = QAction("Fit Page", self)
        self._fit_page_action.triggered.connect(self._fit_current_document_to_page)
        self._fit_width_action = QAction("Fit Width", self)
        self._fit_width_action.triggered.connect(self._fit_current_document_to_width)
        self._fit_height_action = QAction("Fit Height", self)
        self._fit_height_action.triggered.connect(self._fit_current_document_to_height)
        self._actual_size_action = QAction("Actual Size", self)
        self._actual_size_action.triggered.connect(self._show_actual_size)

        self._text_action = QAction("Text", self)
        self._text_action.triggered.connect(self._begin_text_annotation)
        self._date_action = QAction("Date", self)
        self._date_action.triggered.connect(self._begin_date_annotation)
        self._saved_signature_action = QAction("Use Saved", self)
        self._saved_signature_action.triggered.connect(self._begin_signature_annotation)
        self._temporary_signature_action = QAction("Choose New", self)
        self._temporary_signature_action.triggered.connect(
            self._begin_temporary_signature_annotation
        )
        self._replace_signature_action = QAction("Replace Saved", self)
        self._replace_signature_action.triggered.connect(
            self._replace_saved_signature
        )
        self._delete_action = QAction("Delete", self)
        self._delete_action.triggered.connect(self._delete_selected_annotation)

        self._save_current_action = QAction("Save", self)
        self._save_current_action.triggered.connect(self._save_document)
        self._save_action = QAction("Save As", self)
        self._save_action.triggered.connect(self._save_document_as)

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)
        menu_bar.hide()

        self._file_menu = QMenu("File", self)
        self._populate_menu(self._file_menu, self._open_action, self._close_action)

        self._zoom_menu = QMenu("Zoom", self)
        self._populate_menu(
            self._zoom_menu,
            self._zoom_in_action,
            self._zoom_out_action,
            None,
            self._set_zoom_action,
            None,
            self._fit_page_action,
            self._fit_width_action,
            self._fit_height_action,
            self._actual_size_action,
        )

        self._annotate_menu = QMenu("Annotate", self)
        self._signature_menu = QMenu("Signature", self)
        self._signature_menu.addAction(self._saved_signature_action)
        self._signature_menu.addAction(self._temporary_signature_action)
        self._signature_menu.addAction(self._replace_signature_action)
        self._populate_menu(
            self._annotate_menu,
            self._text_action,
            self._date_action,
            None,
            self._delete_action,
        )
        self._annotate_menu.insertMenu(self._delete_action, self._signature_menu)
        self._annotate_menu.insertSeparator(self._delete_action)

        self._save_menu = QMenu("Save", self)
        self._populate_menu(self._save_menu, self._save_current_action, self._save_action)

    def _populate_menu(self, menu: QMenu, *entries: QAction | None) -> None:
        for entry in entries:
            if entry is None:
                menu.addSeparator()
            else:
                menu.addAction(entry)

    def _build_layout(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_top_menu_strip())

        self._splitter = QSplitter(Qt.Horizontal, self)
        self._splitter.setHandleWidth(10)
        self._splitter.setChildrenCollapsible(False)
        page_panel = self._build_page_list()
        page_panel.setMinimumWidth(self._PAGE_PANEL_WIDTH)
        page_panel.setMaximumWidth(self._PAGE_PANEL_WIDTH)
        self._splitter.addWidget(page_panel)
        self._splitter.addWidget(self._build_viewer_panel())
        self._splitter.addWidget(self._build_properties_panel())
        self._splitter.setSizes([self._PAGE_PANEL_WIDTH, 900, 280])
        self._splitter.handle(1).setEnabled(False)
        self._splitter.handle(1).setCursor(Qt.ArrowCursor)
        root_layout.addWidget(self._splitter, 1)
        self.setCentralWidget(root)

    def _build_top_menu_strip(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("topMenuStrip")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)

        for label, menu in (
            ("File", self._file_menu),
            ("Zoom", self._zoom_menu),
            ("Annotate", self._annotate_menu),
            ("Save", self._save_menu),
        ):
            button = QToolButton(container)
            button.setObjectName("topMenuButton")
            button.setText(label)
            button.setPopupMode(QToolButton.InstantPopup)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setMenu(menu)
            button.setFixedWidth(96)
            button.setFixedHeight(24)
            layout.addWidget(button)

        layout.addStretch()
        return container

    def _build_status_bar(self) -> None:
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._set_status_message("Ready")

    def _build_page_list(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("pagePanel")
        container.setStyleSheet("background: #252526;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 16, 4, 16)
        layout.setSpacing(10)
        title = QLabel("Pages", container)
        title.setObjectName("panelTitle")
        self._page_list = ThumbnailListWidget(container)
        self._page_list.setStyleSheet(
            """
            background: #2a2d2e;
            border: none;
            outline: none;
            padding: 0px;
            """
        )
        self._page_list.viewport().setStyleSheet("background: #2a2d2e;")
        self._page_list.currentRowChanged.connect(self._handle_page_selected)
        self._page_list.itemClicked.connect(
            lambda item: self._handle_page_selected(self._page_list.row(item))
        )
        self._page_list.addItem("Open a PDF to load pages")
        list_card = self._make_panel_card(container)
        list_card.setObjectName("pageListCard")
        list_card.setStyleSheet(
            "background: #252526; border: 1px solid #3c3c3c; border-radius: 8px;"
        )
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(0, 4, 0, 4)
        list_layout.addWidget(self._page_list)
        layout.addWidget(title)
        layout.addWidget(list_card, 1)
        return container

    def _build_viewer_panel(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(12)
        header = QWidget(container)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title = QLabel("Document", header)
        title.setObjectName("panelTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._zoom_out_button = QPushButton("-", header)
        self._zoom_out_button.setObjectName("viewerZoomButton")
        self._zoom_out_button.setToolTip("Zoom Out")
        self._zoom_out_button.clicked.connect(lambda: self._change_zoom(-0.1))

        self._zoom_in_button = QPushButton("+", header)
        self._zoom_in_button.setObjectName("viewerZoomButton")
        self._zoom_in_button.setToolTip("Zoom In")
        self._zoom_in_button.clicked.connect(lambda: self._change_zoom(0.1))

        self._fit_width_button = QPushButton("Fit Width", header)
        self._fit_width_button.setObjectName("viewerModeButton")
        self._fit_width_button.clicked.connect(self._fit_current_document_to_width)

        self._fit_height_button = QPushButton("Fit Height", header)
        self._fit_height_button.setObjectName("viewerModeButton")
        self._fit_height_button.clicked.connect(self._fit_current_document_to_height)

        self._zoom_percent_button = QPushButton("100%", header)
        self._zoom_percent_button.setObjectName("viewerPercentButton")
        self._zoom_percent_button.clicked.connect(self._prompt_zoom_percent)

        for button in (
            self._zoom_out_button,
            self._zoom_in_button,
            self._fit_width_button,
            self._fit_height_button,
            self._zoom_percent_button,
        ):
            header_layout.addWidget(button)

        layout.addWidget(header)
        self._viewer = PdfViewer(container)
        self._viewer.current_page_changed.connect(self._sync_page_list_selection)
        self._viewer.annotation_selected.connect(self._handle_annotation_selected)
        self._viewer.annotation_added.connect(self._handle_annotation_added)
        self._viewer.annotation_deleted.connect(self._handle_annotation_deleted)
        self._viewer.annotation_changed.connect(self._handle_annotation_changed)
        layout.addWidget(self._viewer, 1)
        return container

    def _build_properties_panel(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 16, 16, 16)
        layout.setSpacing(12)
        title = QLabel("Selection", container)
        title.setObjectName("panelTitle")
        subtitle = QLabel("Inspect and adjust the selected annotation.", container)
        subtitle.setObjectName("panelSubtitle")
        info_card = self._make_panel_card(container)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(14, 14, 14, 14)
        info_layout.setSpacing(10)
        self._selection_hint = QLabel(
            "Use Text, Date, or Signature to place a new item.\n"
            "Drag an existing annotation to reposition it.",
            info_card,
        )
        self._selection_hint.setObjectName("hintText")
        self._selection_hint.setWordWrap(True)
        self._selection_summary = QLabel(info_card)
        self._selection_summary.setWordWrap(True)
        self._selection_summary.setObjectName("summaryCard")
        self._text_value_label = QLabel("Text", info_card)
        self._text_value_label.setObjectName("fieldLabel")
        self._text_value_input = QLineEdit(info_card)
        self._text_value_input.setPlaceholderText("Selected text")
        self._text_value_input.textEdited.connect(self._apply_text_value_change)
        self._font_size_label = QLabel("Font Size", info_card)
        self._font_size_label.setObjectName("fieldLabel")
        self._font_size_input = IntStepper(8, 72, step=1, suffix=" pt", parent=info_card)
        self._font_size_input.valueChanged.connect(self._apply_font_size_change)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        info_layout.addWidget(self._selection_hint)
        info_layout.addWidget(self._selection_summary)
        info_layout.addWidget(self._text_value_label)
        info_layout.addWidget(self._text_value_input)
        info_layout.addWidget(self._font_size_label)
        info_layout.addWidget(self._font_size_input)
        layout.addWidget(info_card)
        layout.addStretch()
        self._text_value_label.hide()
        self._text_value_input.hide()
        self._font_size_label.hide()
        self._font_size_input.hide()
        return container

    def _make_panel_card(self, parent: QWidget) -> QFrame:
        card = QFrame(parent)
        card.setObjectName("panelCard")
        card.setFrameShape(QFrame.StyledPanel)
        return card

    def _apply_window_style(self) -> None:
        assets_dir = Path(__file__).resolve().parent / "assets"
        spin_up_icon = assets_dir.joinpath("spin_up.svg").as_posix()
        spin_down_icon = assets_dir.joinpath("spin_down.svg").as_posix()
        self.setStyleSheet(
            """
            QMainWindow {{
                background: #1e1e1e;
                color: #d4d4d4;
            }}
            QWidget#topMenuStrip {{
                background: #2d2d30;
                border-bottom: 1px solid #3c3c3c;
            }}
            QToolButton#topMenuButton {{
                background: #2d2d30;
                border: 1px solid #3c3c3c;
                padding: 2px 12px;
                border-radius: 6px;
                color: #d4d4d4;
                font-size: 13px;
                font-weight: 600;
                min-width: 96px;
                max-width: 96px;
                min-height: 24px;
                max-height: 24px;
            }}
            QToolButton#topMenuButton:hover {{
                background: #083b5e;
                border: 1px solid #0e639c;
            }}
            QToolButton#topMenuButton:pressed {{
                background: #0e639c;
            }}
            QMenu {{
                background: #252526;
                border: 1px solid #3c3c3c;
                padding: 6px;
                color: #d4d4d4;
            }}
            QMenu::item {{
                padding: 7px 24px 7px 12px;
                border-radius: 6px;
                color: #d4d4d4;
            }}
            QMenu::item:selected {{
                background: #0e639c;
                color: #ffffff;
            }}
            QSplitter::handle {{
                background: #2d2d30;
            }}
            QSplitter::handle:hover {{
                background: #0e639c;
            }}
            QLabel#panelTitle {{
                font-size: 18px;
                font-weight: 600;
                color: #d4d4d4;
            }}
            QLabel#panelSubtitle {{
                color: #9da5b4;
                font-size: 12px;
            }}
            QFrame#panelCard {{
                background: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
            }}
            QWidget#pagePanel {{
                background: #252526;
            }}
            QFrame#pageListCard {{
                background: #2d2d30;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
            }}
            QLabel#hintText {{
                color: #9da5b4;
                font-size: 12px;
                line-height: 1.4;
            }}
            QLabel#summaryCard {{
                background: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 10px;
                padding: 10px 12px;
                color: #d4d4d4;
            }}
            QLabel#fieldLabel {{
                font-size: 12px;
                font-weight: 600;
                color: #9da5b4;
                margin-top: 4px;
            }}
            QLineEdit, QSpinBox, QAbstractSpinBox, QDialog {{
                background: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
                padding: 7px 10px;
                min-height: 18px;
                color: #d4d4d4;
                selection-background-color: #094771;
            }}
            QLineEdit:focus, QSpinBox:focus, QAbstractSpinBox:focus {{
                border: 1px solid #0e639c;
            }}
            QLineEdit#stepperEdit {
                background: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
                padding: 7px 10px;
                color: #d4d4d4;
                min-width: 52px;
            }
            QPushButton#stepperButton {
                background: #2d2d30;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
                color: #d4d4d4;
                font-size: 15px;
                font-weight: 600;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
            }
            QPushButton#stepperButton:hover {
                background: #083b5e;
                border: 1px solid #0e639c;
            }
            QPushButton#stepperButton:pressed {
                background: #0e639c;
            }
            QPushButton#viewerZoomButton, QPushButton#viewerModeButton, QPushButton#viewerPercentButton {
                background: #2d2d30;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
                color: #d4d4d4;
                padding: 6px 12px;
                min-height: 28px;
            }
            QPushButton#viewerZoomButton:hover, QPushButton#viewerModeButton:hover, QPushButton#viewerPercentButton:hover {
                background: #083b5e;
                border: 1px solid #0e639c;
            }
            QPushButton#viewerZoomButton:pressed, QPushButton#viewerModeButton:pressed, QPushButton#viewerPercentButton:pressed {
                background: #0e639c;
            }
            QPushButton#viewerZoomButton {
                font-size: 18px;
                font-weight: 600;
                min-width: 36px;
                max-width: 36px;
                min-height: 32px;
                padding: 2px 0px;
            }
            QPushButton#viewerModeButton {
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#viewerPercentButton {
                font-size: 12px;
                font-weight: 600;
                min-width: 64px;
            }
            QSpinBox QLineEdit, QAbstractSpinBox QLineEdit {{
                color: #d4d4d4;
                background: transparent;
                border: none;
                padding: 0px;
                selection-background-color: #094771;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: #2d2d30;
                border-left: 1px solid #3c3c3c;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                width: 18px;
                color: #d4d4d4;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: #083b5e;
                border-left: 1px solid #0e639c;
            }}
            QSpinBox::up-arrow, QSpinBox::down-arrow,
            QAbstractSpinBox::up-arrow, QAbstractSpinBox::down-arrow {{
                width: 8px;
                height: 8px;
            }}
            QSpinBox::up-arrow, QAbstractSpinBox::up-arrow {{
                image: url("__SPIN_UP__");
            }}
            QSpinBox::down-arrow, QAbstractSpinBox::down-arrow {{
                image: url("__SPIN_DOWN__");
            }}
            QInputDialog {{
                background: #252526;
            }}
            QInputDialog QLabel {{
                color: #d4d4d4;
                font-size: 13px;
            }}
            QInputDialog QPushButton {{
                background: #2d2d30;
                border: 1px solid #3c3c3c;
                border-radius: 8px;
                padding: 6px 12px;
                color: #d4d4d4;
                min-width: 72px;
            }}
            QInputDialog QPushButton:hover {{
                background: #083b5e;
                border: 1px solid #0e639c;
            }}
            QInputDialog QPushButton:pressed {{
                background: #0e639c;
            }}
            QListWidget {{
                background: #252526;
                border: none;
                outline: none;
                padding: 0px;
            }}
            QListWidget::viewport {{
                background: #252526;
            }}
            QListWidget::item {{
                padding: 8px 8px;
                margin: 0px;
                color: #d4d4d4;
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background: #0e639c;
                color: #ffffff;
                font-weight: 600;
            }}
            QStatusBar {{
                background: #2d2d30;
                border-top: 1px solid #3c3c3c;
                color: #9da5b4;
            }}
            """
            .replace("__SPIN_UP__", spin_up_icon)
            .replace("__SPIN_DOWN__", spin_down_icon)
        )

    def open_pdf(self) -> None:
        if not self._confirm_discard_unsaved_changes("open another PDF"):
            return
        start_dir = self._pdf_start_dir()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            str(start_dir),
            "PDF Files (*.pdf)",
        )
        if file_path:
            self._load_pdf(file_path)

    def _load_pdf(self, file_path: str) -> None:
        pdf_path = Path(file_path)
        if not pdf_path.exists():
            QMessageBox.warning(self, "Open PDF", f"Could not find:\n\n{pdf_path}")
            return

        try:
            document = PdfDocument(pdf_path)
            summaries = document.page_summaries()
        except Exception as exc:  # pragma: no cover - UI path
            QMessageBox.critical(self, "Open PDF", f"Could not open the PDF.\n\n{exc}")
            return

        self._reset_document_state()
        self._document = document
        self._page_summaries = summaries
        self._current_page_index = 0
        self._thumbnail_width = 112
        self._selected_annotation = None
        self._save_path = None
        self._populate_page_list()
        self._viewer.set_document(self._document, self._page_summaries)
        self._update_action_state()
        self._settings.setValue("document/last_opened_file", str(pdf_path))
        self._settings.setValue("document/last_directory", str(pdf_path.parent))
        self._fit_mode = self._FIT_MODE_PAGE
        self._schedule_initial_fit()

    def _pdf_start_dir(self) -> Path:
        if self._document is not None:
            return self._document.path.parent
        last_file = self._settings.value("document/last_opened_file", "", str)
        if last_file:
            last_file_path = Path(last_file)
            if last_file_path.exists():
                return last_file_path.parent
        last_dir = self._settings.value("document/last_directory", "", str)
        if last_dir:
            last_dir_path = Path(last_dir)
            if last_dir_path.exists():
                return last_dir_path
        return Path.home()

    def closeEvent(self, event) -> None:  # pragma: no cover - Qt lifecycle
        if not self._confirm_discard_unsaved_changes("close the application"):
            event.ignore()
            return
        self._save_window_state()
        self._reset_document_state()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # pragma: no cover - Qt lifecycle
        super().resizeEvent(event)
        if self._document is not None and self._fit_mode is not None:
            self._fit_refresh_timer.start(80)

    def _populate_page_list(self) -> None:
        self._page_list.blockSignals(True)
        self._page_list.clear()
        for summary in self._page_summaries:
            item = QListWidgetItem(summary.label)
            item.setToolTip(
                f"{summary.label}\n{int(summary.width)} x {int(summary.height)} pt"
            )
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._page_list.addItem(item)
        if self._page_summaries:
            self._page_list.setCurrentRow(0)
        self._page_list.blockSignals(False)
        self._refresh_thumbnails_now()

    def _handle_page_selected(self, row: int) -> None:
        if 0 <= row < len(self._page_summaries):
            self._current_page_index = row
            self._viewer.scroll_to_page(row)
            self._update_status()

    def _sync_page_list_selection(self, page_index: int) -> None:
        if 0 <= page_index < len(self._page_summaries):
            self._current_page_index = page_index
            self._page_list.blockSignals(True)
            self._page_list.setCurrentRow(page_index)
            self._page_list.blockSignals(False)
            self._update_status()

    def _refresh_thumbnails_now(self) -> None:
        if self._document is None or not self._page_summaries:
            return
        thumbnail_width = self._thumbnail_width
        for row, summary in enumerate(self._page_summaries):
            image = self._document.render_page_to_width(summary.index, thumbnail_width)
            pixmap = QPixmap.fromImage(image)
            item = self._page_list.item(row)
            if item is None:
                continue
            item.setSizeHint(self._page_list._THUMB_ITEM_SIZE)
            item.setIcon(QIcon(pixmap))

    def _change_zoom(self, delta: float) -> None:
        if self._document is None:
            return
        self._fit_mode = None
        self._set_zoom(self._viewer.zoom + delta)

    def _set_zoom(self, zoom: float) -> None:
        if self._document is None:
            return
        self._viewer.set_zoom(zoom)
        self._update_zoom_label()
        self._update_status()

    def _schedule_initial_fit(self, retries: int = 6) -> None:
        if self._document is None:
            return
        if self._viewer.has_valid_viewport() or retries <= 0:
            self._apply_fit_mode()
            return
        QTimer.singleShot(30, lambda: self._schedule_initial_fit(retries - 1))

    def _apply_fit_mode(self) -> None:
        if self._document is None:
            return
        if self._fit_mode == self._FIT_MODE_PAGE:
            self._set_zoom(self._viewer.fit_to_page_zoom())
        elif self._fit_mode == self._FIT_MODE_WIDTH:
            self._set_zoom(self._viewer.fit_to_width_zoom())
        elif self._fit_mode == self._FIT_MODE_HEIGHT:
            self._set_zoom(self._viewer.fit_to_height_zoom())

    def _fit_current_document_to_page(self) -> None:
        if self._document is not None:
            self._fit_mode = self._FIT_MODE_PAGE
            self._apply_fit_mode()

    def _fit_current_document_to_width(self) -> None:
        if self._document is not None:
            self._fit_mode = self._FIT_MODE_WIDTH
            self._apply_fit_mode()

    def _fit_current_document_to_height(self) -> None:
        if self._document is not None:
            self._fit_mode = self._FIT_MODE_HEIGHT
            self._apply_fit_mode()

    def _show_actual_size(self) -> None:
        if self._document is not None:
            self._fit_mode = None
            self._set_zoom(1.0)

    def _prompt_zoom_percent(self) -> None:
        if self._document is None:
            return
        dialog = ZoomPercentDialog(int(self._viewer.zoom * 100), self)
        if dialog.exec() == QDialog.Accepted:
            self._fit_mode = None
            self._set_zoom(dialog.value() / 100.0)

    def _begin_text_annotation(self) -> None:
        if self._document is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Text")
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.addWidget(QLabel("Text:", dialog))
        text_input = QLineEdit(dialog)
        dialog_layout.addWidget(text_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted or not text_input.text().strip():
            return
        value = text_input.text().strip()
        self._viewer.begin_annotation_placement(
            lambda page_index, point: self._make_text_annotation(page_index, point, value, "text")
        )
        self._set_status_message("Click a page to place the text.")

    def _begin_date_annotation(self) -> None:
        if self._document is None:
            return
        value = date.today().isoformat()
        self._viewer.begin_annotation_placement(
            lambda page_index, point: self._make_text_annotation(page_index, point, value, "date")
        )
        self._set_status_message("Click a page to place the date.")

    def _begin_signature_annotation(self) -> None:
        if self._document is None:
            return
        if self._signature_image is None and self._choose_signature_image(save_as_default=True) is None:
            return
        if self._signature_image is None:
            return
        self._begin_signature_annotation_with_image(self._signature_image)

    def _begin_temporary_signature_annotation(self) -> None:
        if self._document is None:
            return
        image = self._choose_signature_image(save_as_default=False)
        if image is None:
            return
        self._begin_signature_annotation_with_image(image)

    def _replace_saved_signature(self) -> None:
        if self._document is None:
            return
        image = self._choose_signature_image(save_as_default=True)
        if image is None:
            return
        self._begin_signature_annotation_with_image(image)

    def _begin_signature_annotation_with_image(self, image: QImage) -> None:
        self._viewer.begin_annotation_placement(
            lambda page_index, point: self._make_signature_annotation(page_index, point, image)
        )
        self._set_status_message("Click a page to place the signature.")

    def _choose_signature_image(self, save_as_default: bool) -> QImage | None:
        start_dir = self._signature_start_dir()
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Signature Image",
            str(start_dir),
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )
        if not image_path:
            return None
        image = QImage(image_path)
        if image.isNull():
            QMessageBox.warning(self, "Signature", "Could not open the signature image.")
            return None
        chosen_path = Path(image_path)
        self._settings.setValue("signature/last_directory", str(chosen_path.parent))
        if save_as_default:
            self._signature_image = image
            self._signature_path = chosen_path
            self._settings.setValue("signature/last_image_path", str(chosen_path))
            self._update_signature_action_state()
        return image

    def _restore_signature_image(self) -> None:
        image_path = self._settings.value("signature/last_image_path", "", str)
        if not image_path:
            return
        signature_path = Path(image_path)
        if not signature_path.exists():
            return
        image = QImage(str(signature_path))
        if image.isNull():
            return
        self._signature_image = image
        self._signature_path = signature_path

    def _update_signature_action_state(self) -> None:
        has_saved_signature = self._signature_image is not None
        self._saved_signature_action.setEnabled(
            self._document is not None and has_saved_signature
        )
        self._temporary_signature_action.setEnabled(self._document is not None)
        self._replace_signature_action.setEnabled(self._document is not None)

    def _signature_start_dir(self) -> Path:
        if self._signature_path is not None and self._signature_path.exists():
            return self._signature_path.parent
        last_dir = self._settings.value("signature/last_directory", "", str)
        if last_dir and Path(last_dir).exists():
            return Path(last_dir)
        return Path.home()

    def _delete_selected_annotation(self) -> None:
        if self._viewer.remove_selected_annotation():
            self._set_status_message("Annotation deleted.")
        else:
            self._set_status_message("Select an annotation first.")

    def _make_text_annotation(
        self,
        page_index: int,
        point: QPointF,
        text: str,
        kind: str,
    ) -> Annotation:
        font_size = 14.0
        width = self._measure_text_annotation_width(text, font_size)
        height = font_size * 1.8
        rect = QRectF(point.x(), point.y(), width, height)
        if kind == "date":
            return Annotation.make_date(page_index, rect, text, font_size)
        return Annotation.make_text(page_index, rect, text, font_size)

    def _measure_text_annotation_width(self, text: str, font_size: float) -> float:
        font = QFont("Segoe UI")
        font.setPointSizeF(font_size)
        metrics = QFontMetricsF(font)
        text_width = metrics.horizontalAdvance(text or " ")
        return max(80.0, text_width + max(16.0, font_size * 0.75))

    def _make_signature_annotation(
        self,
        page_index: int,
        point: QPointF,
        image: QImage,
    ) -> Annotation:
        width = 150.0
        height = width * (image.height() / max(image.width(), 1))
        if height > 72.0:
            scale = 72.0 / height
            width *= scale
            height = 72.0
        rect = QRectF(point.x(), point.y(), width, height)
        return Annotation.make_signature(page_index, rect, image)

    def _handle_annotation_selected(self, annotation: Annotation | None) -> None:
        self._selected_annotation = annotation
        self._update_selection_summary()
        if annotation is None:
            self._set_status_message("Selection cleared.")
        else:
            self._set_status_message(
                f"Selected {annotation.kind} on page {annotation.page_index + 1}."
            )

    def _handle_annotation_added(self, annotation: Annotation) -> None:
        self._selected_annotation = annotation
        self._mark_unsaved_changes()
        self._update_selection_summary()
        self._set_status_message(
            f"Placed {annotation.kind} on page {annotation.page_index + 1}."
        )

    def _handle_annotation_deleted(self, _annotation_id: str) -> None:
        self._selected_annotation = None
        self._mark_unsaved_changes()
        self._update_selection_summary()

    def _handle_annotation_changed(self, annotation: Annotation) -> None:
        self._selected_annotation = annotation
        self._mark_unsaved_changes()
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        self._updating_properties = True
        if self._selected_annotation is None:
            self._selection_summary.setText("No annotation selected.")
            self._text_value_label.hide()
            self._text_value_input.hide()
            self._font_size_label.hide()
            self._font_size_input.hide()
            self._updating_properties = False
            return
        annotation = self._selected_annotation
        if annotation.kind == "signature":
            summary = (
                f"Type: Signature\n"
                f"Page: {annotation.page_index + 1}\n"
                f"Size: {int(annotation.rect.width())} x {int(annotation.rect.height())}"
            )
            self._text_value_label.hide()
            self._text_value_input.hide()
            self._font_size_label.hide()
            self._font_size_input.hide()
        else:
            summary = (
                f"Type: {annotation.kind.title()}\n"
                f"Page: {annotation.page_index + 1}\n"
                f"Text: {annotation.text}\n"
                f"Size: {int(annotation.rect.width())} x {int(annotation.rect.height())}"
            )
            self._text_value_label.show()
            self._text_value_input.show()
            self._font_size_label.show()
            self._font_size_input.show()
            self._text_value_input.setText(annotation.text)
            self._font_size_input.setValue(int(round(annotation.font_size)))
        self._selection_summary.setText(summary)
        self._updating_properties = False

    def _apply_text_value_change(self, value: str) -> None:
        if self._updating_properties or self._selected_annotation is None:
            return
        if self._selected_annotation.kind not in {"text", "date"}:
            return
        self._selected_annotation.text = value
        self._selected_annotation.rect.setWidth(
            self._measure_text_annotation_width(value, self._selected_annotation.font_size)
        )
        self._mark_unsaved_changes()
        self._viewer.refresh_annotations()
        self._update_selection_summary()

    def _apply_font_size_change(self, value: int) -> None:
        if self._updating_properties or self._selected_annotation is None:
            return
        if self._selected_annotation.kind not in {"text", "date"}:
            return
        self._selected_annotation.font_size = float(value)
        self._selected_annotation.rect.setWidth(
            self._measure_text_annotation_width(
                self._selected_annotation.text,
                self._selected_annotation.font_size,
            )
        )
        self._selected_annotation.rect.setHeight(self._selected_annotation.font_size * 1.8)
        self._mark_unsaved_changes()
        self._viewer.refresh_annotations()
        self._update_selection_summary()

    def _update_action_state(self) -> None:
        has_document = self._document is not None
        for action in (
            self._close_action,
            self._zoom_out_action,
            self._zoom_in_action,
            self._set_zoom_action,
            self._fit_page_action,
            self._fit_width_action,
            self._fit_height_action,
            self._actual_size_action,
            self._text_action,
            self._date_action,
            self._delete_action,
            self._save_current_action,
            self._save_action,
        ):
            action.setEnabled(has_document)
        self._update_signature_action_state()
        for button in (
            self._zoom_out_button,
            self._zoom_in_button,
            self._fit_width_button,
            self._fit_height_button,
            self._zoom_percent_button,
        ):
            button.setEnabled(has_document)

    def _update_zoom_label(self) -> None:
        zoom_percent = int(self._viewer.zoom * 100)
        self._set_zoom_action.setText(f"Set Zoom... ({zoom_percent}%)")
        self._zoom_percent_button.setText(f"{zoom_percent}%")

    def _update_status(self) -> None:
        if self._document is None or not self._page_summaries:
            self._set_status_message("Ready")
            return
        self._set_status_message(
            f"Viewing page {self._current_page_index + 1} of {len(self._page_summaries)} at {int(self._viewer.zoom * 100)}%"
        )

    def _save_document(self) -> bool:
        if self._document is None:
            return False
        if self._save_path is None:
            return self._save_document_as()
        return self._write_annotations_to_path(self._save_path)

    def _save_document_as(self) -> bool:
        if self._document is None:
            return False
        default_path = self._suggest_save_path()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Annotated PDF",
            str(default_path),
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return False
        save_path = Path(file_path)
        if save_path.suffix.lower() != ".pdf":
            save_path = save_path.with_suffix(".pdf")
        return self._write_annotations_to_path(save_path)

    def _write_annotations_to_path(self, save_path: Path) -> bool:
        if self._document is None:
            return False
        try:
            self._document.save_with_annotations(save_path, self._viewer.annotations())
        except Exception as exc:  # pragma: no cover - UI path
            QMessageBox.critical(self, "Save PDF", f"Could not save the PDF.\n\n{exc}")
            return False
        self._save_path = save_path
        self._has_unsaved_changes = False
        self._set_status_message(f"Saved annotated PDF to {save_path.name}.")
        return True

    def _suggest_save_path(self) -> Path:
        if self._save_path is not None:
            return self._save_path
        if self._document is None:
            return Path.home() / "annotated.pdf"
        source = self._document.path
        return source.with_name(f"{source.stem}-annotated.pdf")

    def _set_status_message(self, message: str) -> None:
        self._status_bar.showMessage(message)

    def _close_document(self) -> None:
        if not self._confirm_discard_unsaved_changes("close the PDF"):
            return
        self._reset_document_state()

    def _reset_document_state(self) -> None:
        if self._document is not None:
            self._document.close()
        self._document = None
        self._page_summaries = []
        self._current_page_index = 0
        self._thumbnail_width = 112
        self._fit_mode = self._FIT_MODE_PAGE
        self._selected_annotation = None
        self._has_unsaved_changes = False
        self._save_path = None
        self._page_list.clear()
        self._page_list.addItem("Open a PDF to load pages")
        self._viewer.clear_document()
        self._update_action_state()
        self._update_zoom_label()
        self._update_selection_summary()
        self._set_status_message("Ready")

    def _restore_window_state(self) -> None:
        geometry = self._settings.value("window/geometry")
        splitter_state = self._settings.value("window/splitter_state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if splitter_state is not None:
            self._splitter.restoreState(splitter_state)

    def _save_window_state(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/splitter_state", self._splitter.saveState())

    def _restore_last_file(self) -> None:
        last_file = self._settings.value("document/last_opened_file", "", str)
        if not last_file:
            return
        if not Path(last_file).exists():
            self._settings.remove("document/last_opened_file")
            return
        self._load_pdf(last_file)

    def _mark_unsaved_changes(self) -> None:
        self._has_unsaved_changes = True

    def _confirm_discard_unsaved_changes(self, action_name: str) -> bool:
        if self._document is None or not self._has_unsaved_changes:
            return True
        result = QMessageBox.warning(
            self,
            "Unsaved Changes",
            f"You have unsaved annotation changes.\n\nDo you want to save before you {action_name}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Save:
            return self._save_document()
        return result == QMessageBox.Discard
