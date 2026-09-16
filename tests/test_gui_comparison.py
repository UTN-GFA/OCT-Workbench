import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from oct_workbench_gui import MainWindow
from test_core import make_dataset


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_comparison_button_and_difference_object_are_contextual(qapp, tmp_path):
    window = MainWindow()
    window.dataset_a = make_dataset(tmp_path, name="A")
    window.dataset_b = make_dataset(tmp_path, name="B", offset=0.01)
    window.group_b.setVisible(True)
    window._configure_levels(window.dataset_a, "a")
    window._configure_selectors(window.dataset_a, "a")
    window._configure_levels(window.dataset_b, "b")
    window._configure_selectors(window.dataset_b, "b")
    window._refresh_comparison_controls()

    assert window.btn_compare_ab.isEnabled()
    derived = window._create_comparison_difference()

    assert derived.name.startswith("Diff:")
    assert derived.depth_mm is not None
    assert window.derived_objects[-1] is derived
    assert "A − B" in window.lbl_status.text()
    window.close()
