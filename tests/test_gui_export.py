"""Regresiones de exportación contextual de la GUI."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication

from oct_workbench_gui import MainWindow
from test_core import make_dataset
from transforms.base import TransformedView
from tests.plugin_transforms import Offset


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_export_options_follow_the_active_view(qapp):
    window = MainWindow()

    assert window._export_options_for_tab(0) == ("PNG", "CSV", "NPZ", "HDF5")
    assert window._export_options_for_tab(1) == ("PNG", "CSV", "NPZ", "HDF5")
    assert window._export_options_for_tab(2) == ("PNG", "CSV", "NPZ", "HDF5")
    assert window._export_options_for_tab(3) == ("PNG", "CSV", "NPZ", "HDF5")
    assert window._export_options_for_tab(4) == ("PNG", "CSV")
    assert window._export_options_for_tab(5) == ("PNG", "CSV", "NPZ", "HDF5")
    window.close()


def test_export_sources_use_the_current_transformed_view(qapp, tmp_path):
    dataset = make_dataset(tmp_path, one_dimensional=True)
    view = TransformedView(dataset)
    view.pipeline.add(Offset("DEPTH", 0.25))
    window = MainWindow()
    window.dataset_a = dataset
    window.view_a = view

    sources = window._export_sources()

    assert sources[0][0] == "Muestra A (vista actual)"
    assert sources[0][1] is view
    window.close()


def test_export_data_path_roundtrips_the_current_view(qapp, tmp_path):
    dataset = make_dataset(tmp_path, one_dimensional=True)
    view = TransformedView(dataset)
    view.pipeline.add(Offset("DEPTH", 0.25))
    window = MainWindow()

    output = window._export_to_path("NPZ", view, str(tmp_path / "transformed"))

    loaded = dataset.__class__.from_file(output)
    assert loaded.depth_mm.mean() == pytest.approx(dataset.depth_mm.mean() + 0.25)
    window.close()


def test_gui_export_supports_data_formats(qapp, tmp_path):
    dataset = make_dataset(tmp_path, one_dimensional=True)
    window = MainWindow()

    csv_path = window._export_to_path("CSV", dataset, str(tmp_path / "profile"))
    h5_path = window._export_to_path("HDF5", dataset, str(tmp_path / "dataset"))

    assert os.path.exists(csv_path)
    assert os.path.exists(h5_path)
    loaded = dataset.__class__.from_file(h5_path)
    assert loaded.n_points == dataset.n_points
    window.close()
