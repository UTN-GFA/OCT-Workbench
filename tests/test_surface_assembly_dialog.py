import os
import sys

from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.surface_assembly_dialog import SurfaceAssemblyDialog
from test_core import make_dataset


def test_surface_assembly_dialog_exposes_independent_a_b_patch_rows(tmp_path):
    app = QApplication.instance() or QApplication([])
    dataset_a = make_dataset(tmp_path, name="A")
    dataset_b = make_dataset(tmp_path, name="B")

    dialog = SurfaceAssemblyDialog({"A": dataset_a, "B": dataset_b})

    assert dialog.table.rowCount() == 2
    specs = dialog.specifications()
    assert [spec.source for spec in specs] == ["A", "B"]
    assert all(spec.data is None for spec in specs)
    assert specs[0].z_mm == 0.0
    assert specs[1].z_mm == 0.0

    dialog.close()
    app.processEvents()
