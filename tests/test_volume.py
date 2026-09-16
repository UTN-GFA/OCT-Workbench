import numpy as np
import pytest

from model.volume import LevelSelection, VolumeLayout, select_volume_slice


def test_2d_layout_has_one_physical_level():
    x = np.array([0.0, 1.0, 0.0, 1.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    z = np.zeros(4)

    layout = VolumeLayout.from_coordinates(x, y, z, tolerance_mm=1e-6)

    assert layout.dimensions == (2, 2, 1)
    assert layout.n_levels == 1
    assert layout.levels[0].z_mm == 0.0
    assert layout.levels[0].point_indices.tolist() == [0, 1, 2, 3]


def test_multiz_layout_groups_physical_z_with_tolerance():
    x = np.tile([0.0, 1.0], 4)
    y = np.repeat([0.0, 1.0], 4)
    z = np.array([0.0, 0.0, 0.0 + 2e-7, 0.0, 1.0, 1.0, 1.0 + 2e-7, 1.0])

    layout = VolumeLayout.from_coordinates(x, y, z, tolerance_mm=1e-6)

    assert layout.dimensions == (2, 2, 2)
    assert [level.z_mm for level in layout.levels] == pytest.approx([0.0, 1.0], abs=1e-6)
    assert [level.n_points for level in layout.levels] == [4, 4]


def test_level_selection_excludes_reversibly():
    x = np.array([0.0, 1.0, 0.0, 1.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    z = np.array([0.0, 0.0, 1.0, 1.0])
    layout = VolumeLayout.from_coordinates(x, y, z, tolerance_mm=1e-6)
    selection = LevelSelection(layout)

    excluded = selection.exclude(1)
    restored = excluded.restore(1)

    assert selection.active_indices == (0, 1)
    assert excluded.active_indices == (0,)
    assert excluded.excluded_indices == (1,)
    assert restored.active_indices == (0, 1)
    assert selection is not excluded


def test_volume_slices_select_physical_planes_in_each_orientation():
    x = np.tile([0.0, 1.0], 6)
    y = np.repeat([0.0, 1.0], 6)
    z = np.tile([0.0, 0.0, 1.0, 1.0, 2.0, 2.0], 2)
    values = np.arange(x.size, dtype=float)

    xy = select_volume_slice(x, y, z, values, "XY", coordinate_mm=1.0, tolerance_mm=1e-6)
    xz = select_volume_slice(x, y, z, values, "XZ", coordinate_mm=1.0, tolerance_mm=1e-6)
    yz = select_volume_slice(x, y, z, values, "YZ", coordinate_mm=0.0, tolerance_mm=1e-6)

    assert xy.orientation == "XY"
    assert xy.horizontal_axis == "X"
    assert xy.vertical_axis == "Y"
    assert xy.coordinate_mm == pytest.approx(1.0)
    assert xy.values.size == 4
    assert xz.horizontal_axis == "X"
    assert xz.vertical_axis == "Z"
    assert xz.values.size == 6
    assert yz.horizontal_axis == "Y"
    assert yz.vertical_axis == "Z"
    assert yz.values.size == 6
