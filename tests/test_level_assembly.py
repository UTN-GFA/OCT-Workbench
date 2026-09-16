import numpy as np

from transforms.base import TransformData
from model.level_assembly import LevelSelection, assemble_levels, derived_from_assembly
from model.dataset import OCTDataset
from export.exporter import to_npz


def _source_data():
    # Nivel 0: grilla completa 2x2; Nivel 1: grilla completa 2x2; Nivel 2: no se usará.
    x = np.tile([0.0, 1.0, 0.0, 1.0], 3)
    y = np.tile([0.0, 0.0, 1.0, 1.0], 3)
    z = np.repeat([0.0, 1.0, 2.0], 4)
    depth_mm = (10.0 + z + x + 2.0 * y)[:, None, None]
    amplitude = np.ones_like(depth_mm)
    return TransformData(X=x, Y=y, Z=z, depth_mm=depth_mm, amplitude=amplitude)


def test_assemble_selected_levels_applies_per_level_delta_z_and_excludes_disabled():
    result = assemble_levels(
        _source_data(),
        [
            LevelSelection(0.0, 0.0, 1.0, 0.0, 1.0, delta_z_mm=0.0),
            LevelSelection(1.0, 0.0, 1.0, 1.0, 1.0, delta_z_mm=0.5),
            LevelSelection(2.0, enabled=False),
        ],
    )

    assert result.data.n_points == 6
    assert set(np.unique(result.data.Z)) == {0.0, 1.5}
    assert not np.any(np.isclose(result.data.Z, 2.0))
    assert result.data.depth_mm.shape == (6, 1, 1)
    assert result.warnings == []


def test_assemble_levels_keeps_missing_grid_points_as_nan_and_warns():
    source = _source_data()
    keep = np.ones(source.n_points, dtype=bool)
    keep[3] = False  # Falta el punto X=1,Y=1 del Nivel 0.
    source = TransformData(
        X=source.X[keep], Y=source.Y[keep], Z=source.Z[keep],
        depth_mm=source.depth_mm[keep], amplitude=source.amplitude[keep],
    )

    result = assemble_levels(
        source,
        [LevelSelection(0.0, 0.0, 1.0, 0.0, 1.0)],
    )

    assert result.data.n_points == 4
    assert np.count_nonzero(np.isnan(result.data.depth_mm[:, 0, 0])) == 1
    assert any("Nivel Z=0" in warning for warning in result.warnings)




def test_assemble_levels_clusters_acquisition_jitter_without_cartesian_explosion():
    from oct_workbench_gui import _native_patch_grid

    source = TransformData(
        X=np.array([0.0, 1.0003, 0.0002, 0.9998, 0.0001, 1.0001]),
        Y=np.array([0.0001, 0.0, 0.5002, 0.5000, 1.0003, 1.0000]),
        Z=np.zeros(6),
        coordinate_tolerance_mm=0.002,
        depth_mm=np.arange(6, dtype=float)[:, None, None],
        amplitude=np.ones((6, 1, 1)),
    )

    result = assemble_levels(
        source,
        [LevelSelection(0.0, 0.0, 1.0, 0.0, 1.0, tolerance_mm=0.002)],
    )

    assert result.data.n_points == 6
    grid = _native_patch_grid(
        result.data.X,
        result.data.Y,
        result.data.depth_mm[:, 0, 0],
        tolerance=0.002,
    )
    assert grid is not None
    assert grid[2].shape == (3, 2)


def test_derived_assembly_can_be_saved_and_reopened_as_dataset(tmp_path):
    result = assemble_levels(
        _source_data(),
        [LevelSelection(0.0, 0.0, 1.0, 0.0, 1.0)],
    )
    derived = derived_from_assembly(result, "/tmp/muestra1.npz", "Muestra 1*")
    path = to_npz(derived, str(tmp_path / "muestra1_star.npz"))
    reopened = OCTDataset.from_file(path)

    assert reopened.sample_name == "Muestra 1*"
    assert reopened.n_points == 4
    assert "Muestra 1*" in reopened.metadata.get("sample_name", "")
    assert reopened.metadata.get("derived_from") == "/tmp/muestra1.npz"
