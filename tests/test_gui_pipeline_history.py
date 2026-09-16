import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication

from oct_workbench_gui import MainWindow, PipelineHistoryDialog
from test_core import make_dataset


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _configured_window(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    window = MainWindow()
    window.dataset_a = dataset
    window._configure_levels(dataset, "a")
    window._configure_selectors(dataset, "a")
    window._configure_median(dataset, "a")
    window._configure_geometry(dataset, "a")
    window.btn_geometry_invertir_x_a.click()
    window._apply_median_filter("A")
    return window


def test_sidebar_shows_only_last_step_and_history_dialog_keeps_all_steps(qapp, tmp_path):
    window = _configured_window(qapp, tmp_path)

    assert window.lbl_pipeline_a.text() == "Último paso: Mediana 3×3"
    assert "Pipeline (" not in window.lbl_pipeline_a.text()
    assert window.btn_history_pipeline_a.isEnabled()

    dialog = PipelineHistoryDialog("A", window.view_a, window)
    assert dialog.history_list.count() == 2
    assert "Invertir X" in dialog.history_list.item(0).text()
    assert "Mediana" in dialog.history_list.item(1).text()
    assert "color: #20242a" in dialog.history_list.styleSheet()
    dialog.close()
    window.close()


def test_history_can_rewind_to_selected_step_and_restore_original(qapp, tmp_path):
    window = _configured_window(qapp, tmp_path)
    dialog = PipelineHistoryDialog("A", window.view_a, window)
    dialog.rewind_requested.connect(lambda index: window._rewind_preparation("A", index))
    dialog.history_list.setCurrentRow(0)
    dialog.rewind_button.click()

    assert window.view_a is not None
    assert [step.name for step in window.view_a.pipeline.steps] == ["Invertir X"]
    assert window.lbl_pipeline_a.text() == "Último paso: Invertir X"

    window._restore_original("A")
    assert window.view_a is None
    assert window.lbl_pipeline_a.text() == "Último paso: —"
    assert not window.btn_restore_pipeline_a.isEnabled()
    window.close()


def test_pipeline_controls_are_global_and_persist_across_views(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    window = MainWindow()
    window.dataset_a = dataset
    window._update_sidebar_for_tab(5)  # Histograma

    assert window.pipeline_group_a.parentWidget() is window.preparation_group
    assert window.pipeline_header.parentWidget() is window.toolbar_container
    assert not window.pipeline_group_a.isHidden()
    window.show()
    qapp.processEvents()
    assert window.pipeline_group_a.width() > 0
    assert window.btn_undo_pipeline_a.width() == window.btn_metadata.sizeHint().width()
    assert window.btn_history_pipeline_a.width() == window.btn_metadata.sizeHint().width()
    assert window.btn_restore_pipeline_a.width() == window.btn_metadata.sizeHint().width()
    assert window.pipeline_header.geometry().y() == 0
    assert all(
        getattr(window, f"btn_{name}_pipeline_{suffix}").geometry().right()
        <= getattr(window, f"pipeline_group_{suffix}").width()
        for suffix in ("a", "b")
        for name in ("undo", "history", "restore")
    )
    window.dataset_b = dataset
    window._update_sidebar_for_tab(5)
    window.toolbar_container.layout().activate()
    window.pipeline_header.layout().activate()
    qapp.processEvents()
    for suffix in ("a", "b"):
        buttons = [
            getattr(window, f"btn_undo_pipeline_{suffix}"),
            getattr(window, f"btn_history_pipeline_{suffix}"),
            getattr(window, f"btn_restore_pipeline_{suffix}"),
        ]
        last_step = getattr(window, f"lbl_pipeline_{suffix}")
        group = getattr(window, f"pipeline_group_{suffix}")
        controls = buttons + [last_step]
        rects = [
            widget.rect().translated(widget.mapTo(group, widget.rect().topLeft()))
            for widget in controls
        ]
        assert all(rect.left() >= 0 and rect.right() <= group.width() for rect in rects)
        assert all(
            not rects[left].intersects(rects[right])
            for left in range(len(rects))
            for right in range(left + 1, len(rects))
        )
    initial_width = window.pipeline_group_a.width()
    window.lbl_pipeline_a.setText("Último paso: Nivelar regiones (123456789)")
    assert window.pipeline_group_a.width() == initial_width
    assert window.lbl_pipeline_a.geometry().right() <= window.pipeline_group_a.width()
    assert window.pipeline_group_a.parentWidget() is not window.group_a
    assert window.pipeline_group_b.width() > 0
    assert not window.pipeline_group_b.isHidden()
    window.resize(2560, 900)
    window.show()
    qapp.processEvents()
    assert not window._pipeline_header_separate_row
    assert window.pipeline_header.geometry().y() == 0
    pipeline_center = window.pipeline_header.geometry().center().x()
    assert abs(pipeline_center - window.toolbar_container.width() / 2) <= 20
    window.close()


def test_toolbar_reflows_without_clipping_at_narrow_width(qapp, tmp_path):
    dataset = make_dataset(tmp_path)
    window = MainWindow()
    window.dataset_a = dataset
    window.dataset_b = dataset
    window.group_b.setVisible(True)
    window._update_sidebar_for_tab(5)
    window.resize(800, 900)
    window.show()
    qapp.processEvents()
    window.toolbar_container.layout().activate()
    window.pipeline_header.layout().activate()
    qapp.processEvents()

    assert window.width() <= 820
    controls = [
        window.btn_open_a,
        window.btn_open_b,
        window.btn_close_b,
        window.btn_metadata,
        window.btn_compare_ab,
        window.btn_export,
        window.btn_assemble_levels,
        window.btn_assemble_surface,
    ]
    rects = [
        widget.rect().translated(widget.mapTo(window.selection_actions_group, widget.rect().topLeft()))
        for widget in controls
    ]
    assert window.selection_actions_group.isVisible()
    assert all(
        rect.left() >= 0 and rect.right() <= window.selection_actions_group.width()
        for rect in rects
    )
    assert all(
        not rects[left].intersects(rects[right])
        for left in range(len(rects))
        for right in range(left + 1, len(rects))
    )
    window.close()


def test_selection_cards_follow_active_page_height(qapp):
    window = MainWindow()
    window.show()
    qapp.processEvents()

    selection_height = window.group_a.height()
    assert selection_height < 250
    window.sample_mode_bar.setCurrentIndex(1)
    window._set_sample_mode(1)
    qapp.processEvents()
    assert window.sample_mode_bar.currentIndex() == 1
    assert window.sample_pages_a.currentIndex() == 1
    assert window.sample_pages_a.height() > 500
    assert window.group_a.height() > selection_height
    window.sample_mode_bar.setCurrentIndex(0)
    qapp.processEvents()
    assert window.group_a.height() == selection_height
    window.close()


def test_sidebar_pipeline_history_is_disabled_for_original_data(qapp):
    window = MainWindow()
    assert window.lbl_pipeline_a.text() == "Último paso: —"
    assert not window.btn_history_pipeline_a.isEnabled()
    assert not window.btn_restore_pipeline_a.isEnabled()
    window.close()
