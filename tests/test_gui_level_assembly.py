import numpy as np
import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from gui.level_assembly_dialog import LevelAssemblyDialog
from model.dataset import OCTDataset


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _dataset(path):
    x0 = np.tile([0.0, 1.0], 6)
    y0 = np.tile([0.0, 0.0, 1.0, 1.0], 3)
    z = np.repeat([0.0, 1.0, 2.0], 4)
    x = np.tile([0.0, 1.0, 0.0, 1.0], 3)
    y = np.tile([0.0, 0.0, 1.0, 1.0], 3)
    np.savez(
        path,
        x_mm=x, y_mm=y, z_mm=z,
        depth_m=(np.ones((12, 1, 1))) / 1000.0, amplitude=np.ones((12, 1, 1)),
        win_depth_min_m=np.array([0.001]), win_depth_max_m=np.array([0.002]),
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def test_dialog_configures_selection_and_delta_per_level(qapp, tmp_path):
    dataset = _dataset(tmp_path / "levels.npz")
    dialog = LevelAssemblyDialog(dataset)

    dialog._widgets[0][1].setValue(0.25)  # X mínimo Nivel 0
    dialog._widgets[0][5].setValue(0.5)   # ΔZ Nivel 0
    dialog._widgets[1][0].setChecked(False)
    dialog._widgets[2][4].setValue(0.75)  # Y máximo Nivel 2

    selections = dialog.selections()

    assert selections[0].enabled is True
    assert selections[0].x_min == pytest.approx(0.25)
    assert selections[0].delta_z_mm == pytest.approx(0.5)
    assert selections[1].enabled is False
    assert selections[2].y_max == pytest.approx(0.75)
    dialog.close()
