import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from model.dataset import OCTDataset
from oct_workbench_gui import MainWindow
from transforms.base import TransformedView
from tests.plugin_transforms import InvertAxis


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _dataset(path, offset=0.0):
    x = []
    y = []
    z = []
    for zz in (0.0, 1.0, 2.0):
        for yy in (0.0, 1.0):
            for xx in (0.0, 1.0):
                x.append(xx)
                y.append(yy)
                z.append(zz)
    n = len(x)
    depth_mm = np.broadcast_to(np.linspace(0.001, 0.002, n)[:, None, None], (n, 2, 2)).copy()
    depth_mm += offset
    np.savez(
        path,
        x_mm=np.array(x),
        y_mm=np.array(y),
        z_mm=np.array(z),
        depth_m=depth_mm,
        amplitude=np.ones_like(depth_mm),
        wavelengths_nm=np.array([800.0, 810.0]),
        win_depth_min_m=np.array([0.001, 0.001]),
        win_depth_max_m=np.array([0.004, 0.004]),
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def _configure(window, slot, dataset):
    if slot == "a":
        window.dataset_a = dataset
    else:
        window.dataset_b = dataset
        window.group_b.setVisible(True)
    window._configure_levels(dataset, slot)
    window._configure_selectors(dataset, slot)
    window._configure_cuts(dataset, slot)


def test_ab_navigation_is_independent_until_explicitly_enabled(qapp, tmp_path):
    window = MainWindow()
    _configure(window, "a", _dataset(tmp_path / "a.npz"))
    _configure(window, "b", _dataset(tmp_path / "b.npz", 0.0001))
    window._redraw()

    assert not window.coordination_group.isHidden()
    window.sample_mode_bar.setCurrentIndex(1)
    assert window.coordination_group.isHidden()
    window.sample_mode_bar.setCurrentIndex(2)
    assert window.coordination_group.isHidden()
    window.sample_mode_bar.setCurrentIndex(0)
    assert not window.coordination_group.isHidden()
    assert not window.chk_shared_level.isChecked()
    window.spin_level_a.setValue(2)
    assert window.spin_level_b.value() == 0

    window.chk_shared_level.setChecked(True)
    window.spin_level_a.setValue(1)
    assert window.spin_level_b.value() == 1

    window.chk_shared_window.setChecked(True)
    window.spin_window_a.setValue(1)
    assert window.spin_window_b.value() == 1

    window.chk_shared_measurement.setChecked(True)
    window.spin_measurement_a.setValue(1)
    assert window.spin_measurement_b.value() == 1
    window.close()


def test_ab_cuts_remain_independent_without_coordination(qapp, tmp_path):
    window = MainWindow()
    _configure(window, "a", _dataset(tmp_path / "a.npz"))
    _configure(window, "b", _dataset(tmp_path / "b.npz"))
    window._redraw()

    assert not hasattr(window, "chk_shared_cuts")
    window.combo_volume_orientation_a.setCurrentText("XZ")
    window.volume_coordinate_a.setValue(0.0)
    assert window.combo_volume_orientation_b.currentText() == "XY"
    window.tabs.setCurrentIndex(4)
    assert not window.coordination_group.isHidden()
    window.sample_mode_bar.setCurrentIndex(1)
    assert window.coordination_group.isHidden()
    window.tabs.setCurrentIndex(2)
    assert window.coordination_group.isHidden()
    window.sample_mode_bar.setCurrentIndex(0)
    assert not window.coordination_group.isHidden()

    window.close()


def test_gui_preparation_keeps_source_and_restores_the_view(qapp, tmp_path):
    dataset = _dataset(tmp_path / "a.npz")
    window = MainWindow()
    _configure(window, "a", dataset)
    original = dataset.depth_mm.copy()
    window._configure_filter(dataset, "a")
    window.view_a = TransformedView(dataset)
    window.view_a.pipeline.add(InvertAxis("X"))
    window.spin_depth_mm_offset_a.setValue(0.25)
    window._apply_depth_mm_mask("A")

    assert window.view_a is not None
    assert dataset.depth_mm is not None and np.array_equal(dataset.depth_mm, original)
    assert any(step["name"].startswith("Offset OPD") for step in window.view_a.parameters["steps"])
    assert window.btn_restore_mask_a.isEnabled()

    window._restore_depth_mm_mask("A")
    assert window.view_a is not None
    assert [step.name for step in window.view_a.pipeline.steps] == ["Invertir X"]
    assert np.array_equal(dataset.depth_mm, original)
    window.close()


def test_gui_region_controls_disable_cleanly_for_nonfinite_coordinates(qapp, tmp_path):
    dataset = _dataset(tmp_path / "nan_coordinates.npz")
    dataset._X[:] = np.nan
    window = MainWindow()
    _configure(window, "a", dataset)
    window._configure_region_level(dataset, "a")

    assert not window.btn_apply_region_level_a.isEnabled()
    assert window.lbl_region_level_status_a.text() == "Sin coordenadas finitas"
    window.close()


def test_gui_offset_minimum_to_zero_is_simple_and_reversible(qapp, tmp_path):
    dataset = _dataset(tmp_path / "auto_offset.npz", offset=0.0005)
    original = dataset.depth_mm.copy()
    window = MainWindow()
    _configure(window, "a", dataset)
    window._configure_filter(dataset, "a")
    window.chk_offset_zero_a.setChecked(True)
    window._apply_depth_mm_mask("A")

    values = window._shown_a().depth_mm
    assert values is not None
    assert np.nanmin(values) == pytest.approx(0.0)
    assert window.spin_depth_mm_offset_a.value() == pytest.approx(-1.5)
    assert dataset.depth_mm is not None and np.array_equal(dataset.depth_mm, original)
    assert any(step["name"] == "Offset OPD automático" for step in window.view_a.parameters["steps"])
    window._restore_original("A")
    assert window.view_a is None
    window.close()
