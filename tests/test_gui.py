"""Smoke tests de la GUI principal."""

import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication

from oct_workbench_gui import MainWindow
from test_core import make_dataset


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_main_window_starts_in_single_sample_mode(qapp):
    window = MainWindow()

    assert window.windowTitle() == "OCT Workbench"
    assert window.btn_open_a.text().startswith("Abrir A")
    assert not window.btn_open_b.isEnabled()
    assert window.tabs.count() == 6
    assert [window.tabs.tabText(i) for i in range(6)] == [
        "Niveles", "Superficie", "Topografía", "Reflectividad", "Cortes", "Histograma"
    ]
    assert window.lbl_status.text() == "Sin medición cargada"
    assert window.header_title.text() == "OCT Workbench"
    assert window.selection_actions_group.title() == "Acciones"
    assert window.pipeline_group_a.parentWidget() is window.preparation_group
    assert window.pipeline_group_b.parentWidget() is window.preparation_group
    assert window.main_splitter.count() == 2
    window.show()
    qapp.processEvents()
    assert window.pipeline_header.isVisible()
    assert window.btn_open_a.isVisible()
    assert window.btn_export.isVisible()
    window.close()

def test_shared_sample_stage_navigation_keeps_a_and_b_aligned(qapp):
    window = MainWindow()

    assert [window.sample_mode_bar.tabText(i) for i in range(window.sample_mode_bar.count())] == [
        "Selección", "Filtros", "Geometría"
    ]
    assert window.sample_mode_bar.currentIndex() == 0
    assert not hasattr(window.filters_group_a, "title")
    assert not hasattr(window.geometry_group_a, "title")
    assert not window.geometry_group_a.isHidden()
    for index in range(3):
        window.sample_mode_bar.setCurrentIndex(index)
        assert window.sample_pages_a.currentIndex() == index
        assert window.sample_pages_b.currentIndex() == index
    window.close()


def test_each_sample_has_independent_window_and_measurement_selectors(qapp):
    window = MainWindow()

    assert window.spin_window_a is not window.spin_window_b
    assert window.spin_measurement_a is not window.spin_measurement_b
    assert window.cut_group_b.parent() is window.sample_pages_b.widget(0)
    assert window.cut_group_a.title() == "Corte"
    assert window.cut_group_b.title() == "Corte"
    assert window.lbl_depth_mm_offset_a.text() == "Offset (mm):"
    assert window.lbl_depth_mm_offset_b.text() == "Offset (mm):"
    assert not window.spin_depth_mm_offset_a.isHidden()
    assert not window.spin_depth_mm_offset_b.isHidden()
    assert window.chk_offset_zero_a.text() == "Auto offset"
    assert "QCheckBox::indicator:unchecked" in window.styleSheet()
    assert "background: #000000" in window.styleSheet()
    assert "checkbox_checked.svg" in window.styleSheet()
    median_labels = [label.text() for label in window.median_group_a.findChildren(type(window.lbl_depth_mm_min_a))]
    assert "Matriz cuadrada:" in median_labels
    assert window.group_b.isHidden()
    window.close()


def test_map_click_updates_the_cut_of_the_clicked_sample(qapp, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    dataset_a = make_dataset(tmp_path / "a")
    dataset_b = make_dataset(tmp_path / "b")
    window = MainWindow()
    window.dataset_a = dataset_a
    window.dataset_b = dataset_b
    window.group_b.setVisible(True)
    window._configure_cuts(dataset_a, "a")
    window._configure_cuts(dataset_b, "b")
    window._draw_maps("depth_mm")

    class Event:
        xdata = 0.25
        ydata = 0.75

    Event.inaxes = window.canvas_depth_mm.figure.axes[1]
    old_a = (window.spin_x_a.value(), window.spin_y_a.value())
    window._map_clicked(Event())

    assert (window.spin_x_b.value(), window.spin_y_b.value()) != old_a
    assert window.spin_x_a.value() != 0.25 or window.spin_y_a.value() != 0.75
    window.close()


def test_filter_controls_follow_depth_mm_display_units(qapp, tmp_path):
    dataset = make_dataset(tmp_path, one_dimensional=True)
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_filter(dataset)

    assert window.lbl_depth_mm_min.text() == "Mínimo (µm):"
    assert window.lbl_depth_mm_max.text() == "Máximo (µm):"
    assert window.spin_depth_mm_min.value() == pytest.approx(500.0)
    assert window.spin_depth_mm_max.value() == pytest.approx(600.0)

    window.spin_depth_mm_min.setValue(550.0)
    window._apply_depth_mm_mask()
    assert window.view_a is not None
    mask_step = window.view_a.pipeline.steps[0]
    assert mask_step.minimum_mm == pytest.approx(0.55)
    assert mask_step.maximum_mm == pytest.approx(0.60)
    assert window.view_a.offset_mm == pytest.approx(0.0)
    window.close()


def test_depth_mm_filters_are_independent_between_samples(qapp, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    dataset_a = make_dataset(tmp_path / "a", one_dimensional=True)
    dataset_b = make_dataset(tmp_path / "b", one_dimensional=True)
    window = MainWindow()
    window.dataset_a = dataset_a
    window.dataset_b = dataset_b
    window.group_b.setVisible(True)
    window._configure_filter(dataset_a, "a")
    window._configure_filter(dataset_b, "b")

    window.spin_depth_mm_min_a.setValue(550.0)
    window.spin_depth_mm_max_a.setValue(600.0)
    window.spin_depth_mm_min_b.setValue(500.0)
    window.spin_depth_mm_max_b.setValue(550.0)
    window._apply_depth_mm_mask("A")

    assert window.view_a is not None
    assert window.view_b is None
    assert window.view_a.pipeline.steps[0].minimum_mm == pytest.approx(0.55)
    assert window.view_a.pipeline.steps[0].maximum_mm == pytest.approx(0.60)

    window._apply_depth_mm_mask("B")
    assert window.view_b is not None
    assert window.view_b.pipeline.steps[0].minimum_mm == pytest.approx(0.50)
    assert window.view_b.pipeline.steps[0].maximum_mm == pytest.approx(0.55)
    window.close()


def test_cuts_are_separated_by_sample(qapp, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    dataset_a = make_dataset(tmp_path / "a", one_dimensional=True)
    dataset_b = make_dataset(tmp_path / "b", one_dimensional=True)
    window = MainWindow()
    window.dataset_a = dataset_a
    window.dataset_b = dataset_b
    window.group_b.setVisible(True)
    window._configure_selectors(dataset_a, "a")
    window._configure_selectors(dataset_b, "b")
    window._configure_cuts(dataset_a, "a")
    window._configure_cuts(dataset_b, "b")
    window._draw_cuts()

    assert len(window.canvas_cuts.figure.axes) == 4
    assert [axis.get_title() for axis in window.canvas_cuts.figure.axes] == [
        "A: Corte sobre X", "A: Corte sobre Y", "B: Corte sobre X", "B: Corte sobre Y"
    ]
    window.close()


def test_3d_uses_the_same_dataset_view_as_the_2d_maps(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_selectors(dataset)
    window._draw_3d()

    assert len(window.canvas_3d.figure.axes) == 1
    assert window.canvas_3d.figure.axes[0].name == "3d"
    assert window.canvas_3d.figure.axes[0].get_zlabel() == "OPD (µm)"
    window.close()


def test_3d_is_separated_by_sample(qapp, tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    dataset_a = make_dataset(tmp_path / "a")
    dataset_b = make_dataset(tmp_path / "b")
    window = MainWindow()
    window.dataset_a = dataset_a
    window.dataset_b = dataset_b
    window.group_b.setVisible(True)
    window._configure_selectors(dataset_a, "a")
    window._configure_selectors(dataset_b, "b")
    window._draw_3d()

    assert len(window.canvas_3d.figure.axes) == 2
    assert [axis.get_title() for axis in window.canvas_3d.figure.axes] == [
        "A: Superficie OPD", "B: Superficie OPD"
    ]
    assert all("Mallas nativas" not in axis.get_title() for axis in window.canvas_3d.figure.axes)
    assert all(not axis.texts for axis in window.canvas_3d.figure.axes)
    window.close()


def test_incomplete_grid_falls_back_to_point_map(qapp, tmp_path, monkeypatch):
    dataset = make_dataset(tmp_path)
    x_grid, y_grid, z_grid = dataset.topography_grid(0, 0)
    x_grid = x_grid.copy()
    y_grid = y_grid.copy()
    x_grid[0, 0] = np.nan
    y_grid[0, 0] = np.nan
    monkeypatch.setattr(
        dataset, "topography_grid",
        lambda win_id=0, measurement=0: (x_grid, y_grid, z_grid),
    )

    window = MainWindow()
    window.dataset_a = dataset
    window._configure_selectors(dataset)
    window._draw_maps("depth_mm")

    axis = window.canvas_depth_mm.figure.axes[0]
    assert axis.collections
    assert any("Grilla incompleta" in text.get_text() for text in axis.texts)
    window.close()


def test_multiz_map_uses_selected_level_without_raising(qapp, tmp_path):
    path = tmp_path / "multiz_gui.npz"
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0, 0.0, 1.0]),
        y_mm=np.array([0.0, 0.0, 1.0, 1.0]),
        z_mm=np.array([0.0, 0.0, 1.0, 1.0]),
        wavelengths_nm=np.array([800.0]),
        depth_m=np.ones((4, 1, 1)) * 1e-3,
        amplitude=np.ones((4, 1, 1)),
        win_depth_min_m=np.array([1e-3]),
        win_depth_max_m=np.array([2e-3]),
        schema_version="6.0.0",
    )
    from model.dataset import OCTDataset

    window = MainWindow()
    window.dataset_a = OCTDataset.from_file(path)
    window._configure_levels(window.dataset_a, "a")
    window._configure_selectors(window.dataset_a)
    window._draw_maps("depth_mm")
    assert window.spin_level_a.maximum() == 1
    assert window.canvas_depth_mm.figure.axes[0].collections
    window.spin_level_a.setValue(1)
    window._draw_maps("depth_mm")
    assert window.canvas_depth_mm.figure.axes[0].collections
    window.close()


def test_cuts_tab_handles_valid_file_without_peaks(qapp, tmp_path):
    path = tmp_path / "without_peaks.npz"
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0]),
        y_mm=np.array([0.0, 0.0]),
        z_mm=np.array([0.0, 0.0]),
        wavelengths_nm=np.array([800.0, 850.0]),
        schema_version="6.0.0",
        planned_points=np.int32(2),
        acquired_points=np.int32(2),
        dark=np.bool_(False),
        nonlinearity=np.bool_(False),
    )
    from model.dataset import OCTDataset

    window = MainWindow()
    window.dataset_a = OCTDataset.from_file(path)
    window._configure_selectors(window.dataset_a)
    window._draw_cuts()

    assert any("no contiene picos" in text.get_text() for text in window.canvas_cuts.figure.axes[0].texts)
    window.close()
