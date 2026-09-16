import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from oct_workbench_gui import MainWindow
from test_core import make_dataset


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_median_filter_is_contextual_and_reversible(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    original = dataset.depth_mm.copy()
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_median(dataset, "a")

    window._update_sidebar_for_tab(1)  # Superficie
    assert not window.median_group_a.isHidden()
    window._update_sidebar_for_tab(2)  # Topografía
    assert not window.median_group_a.isHidden()
    window._update_sidebar_for_tab(5)  # Histograma
    assert not window.median_group_a.isHidden()

    window.spin_median_kernel_a.setValue(3)
    window._apply_median_filter("A")

    assert window.view_a is not None
    assert any(step["name"].startswith("Mediana") for step in window.view_a.parameters["steps"])
    assert np.array_equal(dataset.depth_mm, original)

    window._restore_median_filter("A")
    assert window.view_a is None
    window.close()
