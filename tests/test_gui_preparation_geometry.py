import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from oct_workbench_gui import MainWindow
from test_core import make_dataset
from transforms.base import TransformedView
from tests.plugin_transforms import InvertAxis


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_geometry_preparation_is_reversible_and_keeps_source(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    original_x = dataset.X.copy()
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_geometry(dataset, "a")

    window.btn_geometry_invertir_x_a.click()

    assert window.view_a is not None
    assert np.allclose(window._shown_a().X, -original_x)
    assert np.array_equal(dataset.X, original_x)
    assert "Invertir X" in window.lbl_pipeline_a.text()
    assert not hasattr(window, "combo_geometry_a")
    assert [button.text() for button in window.geometry_action_buttons_a] == [
        "Invertir X", "Invertir Y", "Invertir Z",
        "Espejar X", "Espejar Y", "Centrar origen",
    ]
    assert window.chk_invert_depth_a.text() == "Invertir OPD"

    window._configure_filter(dataset, "a")
    window._apply_depth_mm_mask("A")
    assert np.allclose(window._shown_a().X, -original_x)
    assert [step["name"] for step in window.view_a.parameters["steps"]][0] == "Invertir X"

    window._restore_original("A")
    assert window.view_a is None
    assert window.lbl_pipeline_a.text() == "Último paso: —"
    window.close()


def test_invert_x_coordinate_conversion_is_identical_for_a_and_b(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    window = MainWindow()
    window.dataset_a = dataset
    window.dataset_b = dataset
    window.view_a = TransformedView(dataset)
    window.view_b = TransformedView(dataset)
    window.view_a.pipeline.add(InvertAxis("X"))
    window.view_b.pipeline.add(InvertAxis("X"))
    source_value = float(dataset.X[0])

    assert window._display_coordinate(window.view_a, "X", source_value) == pytest.approx(
        window._display_coordinate(window.view_b, "X", source_value)
    )
    window.close()


def test_geometry_value_is_contextual_and_only_offsets_use_mm(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_geometry(dataset, "a")

    assert not hasattr(window, "combo_geometry_a")
    assert [button.text() for button in window.geometry_action_buttons_a] == [
        "Invertir X", "Invertir Y", "Invertir Z",
        "Espejar X", "Espejar Y", "Centrar origen",
    ]
    assert all(button.isEnabled() for button in window.geometry_action_buttons_a)
    assert set(window.geometry_offset_spins_a) == {"X", "Y", "Z"}
    assert set(window.geometry_offset_buttons_a) == {"X", "Y", "Z"}
    window.close()
