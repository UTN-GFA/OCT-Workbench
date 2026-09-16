import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from model.dataset import OCTDataset
from oct_workbench_gui import MainWindow
from transforms.base import TransformedView
from tests.plugin_transforms import Mirror


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _profile_dataset(path):
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0]),
        y_mm=np.array([0.0, 0.0]),
        z_mm=np.array([0.0, 0.0]),
        wavelengths_nm=np.array([800.0]),
        profile_mod_w0=np.array([[[1.0, 2.0, 3.0, 4.0]], [[4.0, 3.0, 2.0, 1.0]]]),
        profile_depth_m_w0=np.array([0.001, 0.002, 0.003, 0.004]),
        win_depth_min_m=np.array([0.001]),
        win_depth_max_m=np.array([0.004]),
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def test_cortes_can_select_axial_profile_from_saver_payload(qapp, tmp_path):
    dataset = _profile_dataset(tmp_path / "profiles.npz")
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_cuts(dataset, "a")

    depth_mm, values = window._selected_axial_profile(dataset, "A")

    assert np.allclose(depth_mm, [1.0, 2.0, 3.0, 4.0])
    assert np.allclose(values, [1.0, 2.0, 3.0, 4.0])
    window._draw_cuts()
    assert any("Perfil axial" in axis.get_title() for axis in window.canvas_cuts.figure.axes)
    window.close()


def test_axial_profile_selection_uses_transformed_coordinates(qapp, tmp_path):
    dataset = _profile_dataset(tmp_path / "profiles_mirror.npz")
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_cuts(dataset, "a")
    window.spin_x_a.setValue(0.0)
    view = TransformedView(dataset)
    view.pipeline.add(Mirror("X"))

    _depth_mm, values = window._selected_axial_profile(view, "A")

    assert np.allclose(values, [1.0, 2.0, 3.0, 4.0])
    window.close()
