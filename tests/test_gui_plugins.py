import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication

import oct_workbench_gui
from oct_workbench_gui import MainWindow
from test_core import make_dataset
from transforms.discovery import discover_plugins


@pytest.fixture(scope="session")
def qapp_plugins():
    return QApplication.instance() or QApplication([])


def test_gui_generates_local_plugin_controls_from_metadata(qapp_plugins, tmp_path, monkeypatch):
    plugin_dir = tmp_path / "filters"
    plugin_dir.mkdir()
    (plugin_dir / "gain.py").write_text(
        '''
PLUGIN = {
    "id": "gain",
    "tipo": "filter",
    "nombre": "Ganancia local",
    "descripcion": "Multiplicar OPD",
    "parametros": [{"id": "factor", "tipo": "float", "nombre": "Factor", "default": 2.0, "min": 0.0, "max": 10.0}],
}
def aplicar(data, parametros):
    return data.depth_mm * parametros["factor"]
''',
        encoding="utf-8",
    )
    registry = discover_plugins(plugin_dir)
    monkeypatch.setattr(oct_workbench_gui, "discover_plugin_tree", lambda _root: registry)

    window = MainWindow()

    assert window.plugin_buttons_filter_a
    assert window.plugin_buttons_filter_a[0].text() == "Aplicar Ganancia local"
    assert window.findChild(type(window.filter_group_a), "localFilterPlugins") is not None
    window.close()


def test_gui_applies_local_plugin_through_existing_pipeline(qapp_plugins, tmp_path, monkeypatch):
    plugin_dir = tmp_path / "filters"
    plugin_dir.mkdir()
    (plugin_dir / "gain.py").write_text(
        '''
PLUGIN = {"id": "gain", "tipo": "filter", "nombre": "Ganancia local"}
def aplicar(data, parametros):
    return data.depth_mm * 2.0
''',
        encoding="utf-8",
    )
    registry = discover_plugins(plugin_dir)
    monkeypatch.setattr(oct_workbench_gui, "discover_plugin_tree", lambda _root: registry)

    window = MainWindow()
    dataset = make_dataset(tmp_path)
    window.dataset_a = dataset
    window._configure_filter(dataset, "a")
    button = window.plugin_buttons_filter_a[0]
    assert button.isEnabled()
    button.click()

    assert window.view_a is not None
    assert window.view_a.pipeline.steps[-1].name == "Ganancia local"
    window.close()


def test_gui_exposes_integrated_level_plane_plugin(qapp_plugins, tmp_path):
    window = MainWindow()
    dataset = make_dataset(tmp_path)
    window.dataset_a = dataset
    window._configure_filter(dataset, "a")
    window.sample_mode_bar.setCurrentIndex(1)
    window._set_sample_mode(1)
    window.show()
    qapp_plugins.processEvents()

    assert window.level_plane_group_a.isVisible()
    assert window.btn_apply_level_plane_a.isEnabled()
    window.btn_apply_level_plane_a.click()

    assert window.view_a is not None
    assert window.view_a.pipeline.steps[-1].name == "Nivelar plano"
    assert "plano" in window.lbl_level_plane_status_a.text().lower()
    window.close()
