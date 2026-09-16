import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from model.dataset import OCTDataset
from oct_workbench_gui import MainWindow


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _multiz_dataset(path):
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0, 0.0, 1.0]),
        y_mm=np.array([0.0, 0.0, 1.0, 1.0]),
        z_mm=np.array([0.0, 0.0, 1.0, 1.0]),
        wavelengths_nm=np.array([800.0]),
        depth_m=np.array([[[0.001]], [[0.0011]], [[0.002]], [[0.0021]]]),
        amplitude=np.ones((4, 1, 1)),
        win_depth_min_m=np.array([0.001]),
        win_depth_max_m=np.array([0.003]),
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def _configure(window, dataset):
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset)
    window._configure_cuts(dataset)
    window.tabs.setCurrentIndex(4)


def test_orthogonal_volume_controls_belong_to_cortes_and_are_independent(qapp, tmp_path):
    dataset = _multiz_dataset(tmp_path / "volume.npz")
    window = MainWindow()
    _configure(window, dataset)

    assert [window.combo_volume_orientation_a.itemText(i) for i in range(3)] == ["XY", "XZ", "YZ"]
    assert window.combo_volume_orientation_a is not window.combo_volume_orientation_b
    assert window.volume_coordinate_a is not window.volume_coordinate_b
    assert not window.volume_group_a.isHidden()

    window.combo_volume_orientation_a.setCurrentText("XZ")
    window.volume_coordinate_a.setValue(0.5)
    window._draw_cuts()

    assert "corte xz" in window.canvas_cuts.figure.axes[0].get_title().lower()
    window.close()


def test_2d_payload_stays_a_valid_xy_slice(qapp, tmp_path):
    path = tmp_path / "2d.npz"
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0, 0.0, 1.0]),
        y_mm=np.array([0.0, 0.0, 1.0, 1.0]),
        z_mm=np.zeros(4),
        wavelengths_nm=np.array([800.0]),
        depth_m=np.array([[[0.001]], [[0.0011]], [[0.0012]], [[0.0013]]]),
        amplitude=np.ones((4, 1, 1)),
        win_depth_min_m=np.array([0.001]),
        win_depth_max_m=np.array([0.003]),
        schema_version="6.0.0",
    )
    dataset = OCTDataset.from_file(path)
    window = MainWindow()
    _configure(window, dataset)
    window.combo_volume_orientation_a.setCurrentText("XY")
    window._draw_cuts()
    assert window.canvas_cuts.figure.axes[0].lines
    window.close()


def test_volume_cut_without_depth_mm_shows_a_placeholder(qapp, tmp_path):
    path = tmp_path / "without_depth_mm.npz"
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0]),
        y_mm=np.array([0.0, 0.0]),
        z_mm=np.array([0.0, 1.0]),
        wavelengths_nm=np.array([800.0]),
        schema_version="6.0.0",
    )
    dataset = OCTDataset.from_file(path)
    window = MainWindow()
    _configure(window, dataset)
    window.combo_volume_orientation_a.setCurrentText("XZ")
    window._draw_cuts()
    assert any("no contiene picos" in text.get_text() for text in window.canvas_cuts.figure.axes[0].texts)
    window.close()
