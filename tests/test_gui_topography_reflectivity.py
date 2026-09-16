import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from model.dataset import OCTDataset
from oct_workbench_gui import MainWindow


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _map_dataset(path):
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0, 0.0, 1.0]),
        y_mm=np.array([0.0, 0.0, 1.0, 1.0]),
        z_mm=np.zeros(4),
        depth_m=(np.array([[[1.0]], [[2.0]], [[3.0]], [[4.0]]])) / 1000.0,
        amplitude=np.array([[[10.0]], [[20.0]], [[30.0]], [[40.0]]]),
        wavelengths_nm=np.array([850.0]),
        win_depth_min_m=np.array([0.001]),
        win_depth_max_m=np.array([0.004]),
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def test_topography_and_reflectivity_are_separate_views(qapp, tmp_path):
    dataset = _map_dataset(tmp_path / "views.npz")
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")

    assert not hasattr(window, "combo_map_view")
    assert window.filters_group_a.parent() is window.sample_pages_a.widget(1)
    assert window.filters_group_b.parent() is window.sample_pages_b.widget(1)

    window.tabs.setCurrentIndex(2)
    window._redraw()
    topography_axes = window.canvas_depth_mm.figure.axes
    assert any("OPD" in axis.get_ylabel() for axis in topography_axes)
    assert not any("Amplitud" in axis.get_ylabel() for axis in topography_axes)

    window.tabs.setCurrentIndex(3)
    window._redraw()
    reflectivity_axes = window.canvas_amp.figure.axes
    assert any("Amplitud" in axis.get_ylabel() for axis in reflectivity_axes)
    assert not any("OPD" in axis.get_ylabel() for axis in reflectivity_axes)
    window.close()
