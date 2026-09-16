import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from model.dataset import OCTDataset
from oct_workbench_gui import MainWindow
from transforms.base import TransformedView
from tests.plugin_transforms import InvertAxis, LevelFromRegions


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _plane_dataset(path):
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0, 0.0, 1.0]),
        y_mm=np.array([0.0, 0.0, 1.0, 1.0]),
        z_mm=np.zeros(4),
        depth_m=(np.array([[[5.0]], [[7.0]], [[8.0]], [[10.0]]])) / 1000.0,
        amplitude=np.ones((4, 1, 1)),
        wavelengths_nm=np.array([850.0]),
        win_depth_min_m=np.array([0.001]),
        win_depth_max_m=np.array([0.004]),
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def test_region_leveling_is_reversible_and_preserves_source(qapp, tmp_path):
    dataset = _plane_dataset(tmp_path / "plane.npz")
    original = dataset.depth_mm.copy()
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_region_level(dataset, "a")
    window.spin_region_x_min_a.setValue(1.0)
    window.spin_region_x_max_a.setValue(0.0)
    window.spin_region_y_min_a.setValue(1.0)
    window.spin_region_y_max_a.setValue(0.0)

    window._apply_region_leveling("A")

    assert window.view_a is not None
    assert np.allclose(window._shown_a().depth_mm[:, 0, 0], 0.0)
    assert np.array_equal(dataset.depth_mm, original)
    assert "aplicado" in window.lbl_region_level_status_a.text().lower()

    window._restore_region_leveling("A")
    assert window.view_a is None
    assert window.lbl_region_level_status_a.text() == "Sin nivelado aplicado"
    window.close()


def test_region_leveling_remains_available_in_all_views(qapp):
    window = MainWindow()

    window._update_sidebar_for_tab(1)  # Superficie
    assert not window.region_level_group_a.isHidden()
    window._update_sidebar_for_tab(2)  # Topografía
    assert not window.region_level_group_a.isHidden()
    window._update_sidebar_for_tab(5)  # Histograma
    assert not window.region_level_group_a.isHidden()
    assert not window.geometry_group_a.isHidden()
    assert window.pipeline_group_a.isHidden()

    window.close()


def test_region_restore_keeps_other_pipeline_steps(qapp, tmp_path):
    dataset = _plane_dataset(tmp_path / "plane_restore.npz")
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_region_level(dataset, "a")
    window.view_a = TransformedView(dataset)
    window.view_a.pipeline.add(InvertAxis("X"))
    window.view_a.pipeline.add(LevelFromRegions(
        [(0.0, 1.0, 0.0, 1.0)], win_id=0, measurement=0,
        level_z_mm=0.0, level_tolerance_mm=dataset.coordinate_tolerance_mm,
    ))
    window._redraw = lambda *_args: None

    assert [step.name for step in window.view_a.pipeline.steps] == ["Invertir X", "Nivelar regiones (1)"]
    window._restore_region_leveling("A")
    assert window.view_a is not None
    assert [step.name for step in window.view_a.pipeline.steps] == ["Invertir X"]
    window.close()
