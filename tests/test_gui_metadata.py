import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication, QLabel

from oct_workbench_gui import MetadataDialog
from test_core import make_dataset


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_metadata_dialog_surfaces_curated_quality_summary(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    dialog = MetadataDialog(dataset, None)
    labels = [label.text() for label in dialog.findChildren(QLabel)]
    quality_texts = [text for text in labels if "OPD válidos" in text]
    assert len(quality_texts) == 1
    assert "Amplitud válida" in quality_texts[0]
    assert "Barrido abortado" in quality_texts[0]
    dialog.close()
