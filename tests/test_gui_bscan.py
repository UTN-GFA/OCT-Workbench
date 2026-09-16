import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from model.dataset import OCTDataset
from oct_workbench_gui import MainWindow


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _spectral_dataset(path):
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0, 2.0]),
        y_mm=np.array([0.0, 0.0, 0.0]),
        z_mm=np.array([0.0, 0.0, 0.0]),
        wavelengths_nm=np.array([800.0, 850.0, 900.0, 950.0]),
        spectra=np.array([
            [[1.0, 2.0, 3.0, 4.0]],
            [[2.0, 3.0, 4.0, 5.0]],
            [[3.0, 4.0, 5.0, 6.0]],
        ]),
        win_depth_min_m=np.array([0.001]),
        win_depth_max_m=np.array([0.004]),
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def test_cortes_bscan_uses_spectral_axis_and_selected_x_line(qapp, tmp_path):
    dataset = _spectral_dataset(tmp_path / "spectral.npz")
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_cuts(dataset, "a")

    positions, wavelengths, values = window._selected_bscan(dataset, "A")

    assert np.allclose(positions, [0.0, 1.0, 2.0])
    assert np.allclose(wavelengths, [800.0, 850.0, 900.0, 950.0])
    assert values.shape == (3, 4)
    assert np.allclose(values[:, 0], [1.0, 2.0, 3.0])
    window.close()


def test_cortes_bscan_draws_only_when_explicitly_selected(qapp, tmp_path):
    dataset = _spectral_dataset(tmp_path / "spectral.npz")
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_cuts(dataset, "a")

    assert window.combo_cut_mode_a.currentText() == "Cortes X/Y"
    window.combo_cut_mode_a.setCurrentText("B-scan espectral")
    window._draw_cuts()

    assert any("B-scan" in axis.get_title() for axis in window.canvas_cuts.figure.axes)
    window.close()
