import pytest

from gui.display_state import DisplayState


def test_display_state_defaults_to_independent_navigation():
    state = DisplayState()

    assert state.shared_level is False
    assert state.shared_window is False
    assert state.shared_measurement is False


def test_source_state_exposes_canonical_window_and_measurement_indices():
    state = DisplayState()
    source = state.source("A")
    source.window_index = 2
    source.measurement_index = 1

    assert source.window_id == 2
    assert source.measurement == 1
    assert source.window_index == 2
    assert source.measurement_index == 1


def test_display_state_keeps_independent_a_b_selections():
    state = DisplayState()
    state.set_level("A", 2)
    state.set_level("B", 4)
    state.set_cut("A", 0.1, 0.2)

    assert state.source("A").level_index == 2
    assert state.source("B").level_index == 4
    assert state.source("A").cut_x_mm == 0.1
    assert state.source("B").cut_x_mm is None


def test_display_state_excludes_levels_without_mutating_other_source():
    state = DisplayState()
    state.exclude_level("A", 3)
    state.restore_level("A", 3)

    assert state.source("A").excluded_levels == frozenset()
    assert state.source("B").excluded_levels == frozenset()


def test_display_state_rejects_invalid_depth_mm_range():
    state = DisplayState()

    with pytest.raises(ValueError, match="mínimo OPD"):
        state.set_filter("A", 2.0, 1.0)
