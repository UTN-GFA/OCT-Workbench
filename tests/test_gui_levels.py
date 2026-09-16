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


def test_gui_level_selection_changes_data_and_exclusion_is_reversible(qapp, tmp_path):
    dataset = _multiz_dataset(tmp_path / "levels.npz")
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset)
    window._configure_cuts(dataset)

    assert window.spin_level_a.maximum() == 1
    assert np.allclose(window._level_arrays(dataset, "A")[2], 0.0)

    window.spin_level_a.setValue(1)
    assert np.allclose(window._level_arrays(dataset, "A")[2], 1.0)
    assert window.canvas_levels.figure.axes
    assert len(window.canvas_levels.figure.axes[0].collections) == 2

    window._exclude_level("A")
    with pytest.raises(ValueError, match="excluido"):
        window._level_arrays(dataset, "A")

    window._restore_levels("A")
    assert np.allclose(window._level_arrays(dataset, "A")[2], 1.0)
    window.close()


def test_levels_sidebar_contains_only_level_controls(qapp):
    window = MainWindow()

    window.show()
    window.group_b.setVisible(True)
    qapp.processEvents()
    assert 260 <= window.sidebar_scroll.width() <= 420
    assert window.main_splitter.count() == 2
    assert window.main_splitter.widget(0) is window.sidebar_scroll
    assert window.main_splitter.widget(1) is window.tabs
    assert window.sidebar.minimumWidth() == 0
    assert window.sidebar.maximumWidth() >= 100000
    assert window.group_a.geometry().right() <= window.sidebar.width()
    assert window.group_b.geometry().right() <= window.sidebar.width()
    assert not hasattr(window, "comparison_group")
    assert not window.level_controls_a.isHidden()
    assert not window.spin_level_a.isHidden()
    assert window.selector_group_a.isHidden()
    assert window.selector_group_b.isHidden()
    assert window.cut_group_a.isHidden()
    assert window.cut_group_b.isHidden()
    assert window.extraction_group.isHidden()
    assert not window.filter_group_a.isHidden()
    assert not window.filter_group_b.isHidden()

    for index in (1, 2, 3, 4, 5):
        window.tabs.setCurrentIndex(index)
        assert window.level_controls_a.isHidden()

    for index in (1, 2, 5):
        window.tabs.setCurrentIndex(index)
        assert not window.filter_group_a.isHidden()
        assert not window.filter_group_b.isHidden()
    for index in (3, 4):
        window.tabs.setCurrentIndex(index)
        assert not window.filter_group_a.isHidden()
        assert not window.filter_group_b.isHidden()

    window.tabs.setCurrentIndex(4)
    assert not window.selector_group_a.isHidden()
    assert not window.cut_group_a.isHidden()
    assert not window.extraction_group.isHidden()
    assert not window.filter_group_a.isHidden()
    assert not window.filter_group_b.isHidden()
    window.close()
