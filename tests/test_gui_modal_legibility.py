import os
import sys

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from oct_workbench_gui import MainWindow


def test_modal_dialogs_have_explicit_high_contrast_theme():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    stylesheet = window.styleSheet()

    assert "QDialog#modalDialog" in stylesheet
    assert "QLabel#dialogIntro" in stylesheet
    assert "QDialogButtonBox#modalButtons" in stylesheet
    assert "QMessageBox QPushButton" in stylesheet
    assert "background: #252b34" in stylesheet
    assert "color: #f2f4f7" in stylesheet

    window.close()
    app.processEvents()
