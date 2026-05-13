import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from office_pdf_signer.ui.main_window import MainWindow


def _build_app_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#252526"))
    palette.setColor(QPalette.WindowText, QColor("#cccccc"))
    palette.setColor(QPalette.Base, QColor("#1e1e1e"))
    palette.setColor(QPalette.AlternateBase, QColor("#252526"))
    palette.setColor(QPalette.Text, QColor("#d4d4d4"))
    palette.setColor(QPalette.Button, QColor("#2d2d30"))
    palette.setColor(QPalette.ButtonText, QColor("#d4d4d4"))
    palette.setColor(QPalette.Highlight, QColor("#094771"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.PlaceholderText, QColor("#7f848e"))
    return palette


def main() -> int:
    QCoreApplication.setOrganizationName("Hyeonyu")
    QCoreApplication.setApplicationName("Office PDF Signer")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_build_app_palette())
    window = MainWindow()
    window.show()
    return app.exec()
