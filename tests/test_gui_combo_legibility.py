import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication, QComboBox

from oct_workbench_gui import MainWindow


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_combo_boxes_have_readable_closed_and_popup_colors(qapp):
    """Los combos no deben heredar texto claro sobre fondos claros."""
    window = MainWindow()

    stylesheet = window.styleSheet()
    assert "QComboBox {" in stylesheet
    assert "color: #20242a" in stylesheet
    assert "QComboBox QAbstractItemView" in stylesheet
    assert "selection-color: #ffffff" in stylesheet

    combos = window.findChildren(QComboBox)
    assert combos
    assert all(combo.currentText() for combo in combos)
    window.close()
