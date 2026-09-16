import os
import sys

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from oct_workbench_gui import MainWindow
from test_core import make_dataset


def test_gui_extract_profile_creates_derived_object(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    dataset = make_dataset(tmp_path, name="GUI")
    window.dataset_a = dataset
    window._configure_selectors(dataset)
    window.btn_extract_x.setEnabled(True)
    window.btn_extract_y.setEnabled(True)

    window._extract_profile("x")

    assert len(window.derived_objects) == 1
    derived = window.derived_objects[0]
    assert derived.n_points == 5
    assert derived.provenance.extraction_type.name == "PROFILE_X"
    assert "Puntos: 5" in window.lbl_derived_status.text()
    window.close()
    app.processEvents()
