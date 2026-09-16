import numpy as np
import pytest

from compare import ComparisonPair
from extract import ExtractionType, Provenance, extract_profile_x
from extract.cuts import extract_cuts
from model.dataset import OCTDataset
from transforms.base import TransformedView
from extract.derived import DerivedObject


def _write_dataset(path, x, y, z, *, tolerance_x=0.001, tolerance_y=0.001, tolerance_z=0.001):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    n = len(x)
    depth_mm = np.arange(1, n + 1, dtype=float).reshape(n, 1, 1)
    np.savez(
        path,
        x_mm=x,
        y_mm=y,
        z_mm=z,
        depth_m=depth_mm / 1000.0,
        amplitude=np.ones((n, 1, 1)),
        wavelengths_nm=np.array([800.0]),
        win_depth_min_m=np.array([1e-3]),
        win_depth_max_m=np.array([2e-3]),
        position_tolerance_x_mm=tolerance_x,
        position_tolerance_y_mm=tolerance_y,
        position_tolerance_z_mm=tolerance_z,
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def test_axis_specific_tolerances_are_used_by_grid(tmp_path):
    dataset = _write_dataset(
        tmp_path / "axis_tolerance.npz",
        [0.0, 0.0005],
        [0.0, 0.0],
        [0.0, 0.0],
    )

    assert dataset.coordinate_tolerances_mm == {
        "X": pytest.approx(0.001),
        "Y": pytest.approx(0.001),
        "Z": pytest.approx(0.001),
    }
    assert dataset.grid.nx == 1


def test_axis_specific_tolerances_do_not_use_global_max(tmp_path):
    dataset = _write_dataset(
        tmp_path / "anisotropic_tolerance.npz",
        [0.0, 0.05],
        [0.0, 0.05],
        [0.0, 0.0],
        tolerance_x=0.001,
        tolerance_y=0.1,
        tolerance_z=0.001,
    )

    assert dataset.grid.nx == 2
    assert dataset.grid.ny == 1


def test_profile_and_cuts_use_persisted_axis_tolerance(tmp_path):
    dataset = _write_dataset(
        tmp_path / "jittered_row.npz",
        [0.0, 1.0, 0.0, 1.0],
        [0.0, 0.0015, 1.0, 1.0015],
        [0.0, 0.0, 0.0, 0.0],
        tolerance_y=0.002,
    )

    profile = extract_profile_x(dataset, y_value=0.0)
    cuts = extract_cuts(dataset, y_value=0.0)

    assert profile.n_points == 2
    assert len(cuts.x_position) == 2


def test_transformed_view_rejects_duplicate_xy_cells(tmp_path):
    dataset = _write_dataset(
        tmp_path / "duplicate_xy.npz",
        [0.0, 0.0, 1.0],
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    )

    with pytest.raises(ValueError, match="coordenadas X/Y duplicadas"):
        TransformedView(dataset).topography_grid()


def _derived(name, x, *, tolerance=0.001, depth_mm_value=1.0):
    provenance = Provenance("source", ExtractionType.CUSTOM, {}, [])
    return DerivedObject(
        name=name,
        X=np.asarray(x, dtype=float),
        Y=np.zeros(len(x), dtype=float),
        Z=np.zeros(len(x), dtype=float),
        depth_mm=np.full((len(x), 1, 1), depth_mm_value),
        provenance=provenance,
        metadata={"position_tolerance_mm": tolerance},
    )


def test_comparison_matches_points_within_tolerance_across_bucket_boundary():
    source_a = _derived("A", [0.00049], depth_mm_value=1.0)
    source_b = _derived("B", [0.00051], depth_mm_value=1.2)

    stats = ComparisonPair(source_a, source_b).statistics()

    assert stats.n_points_common == 1
    assert stats.mean_diff == pytest.approx(-0.2)


def test_comparison_rejects_duplicate_points_in_a():
    source_a = _derived("A", [0.0, 0.0])
    source_b = _derived("B", [0.0])

    with pytest.raises(ValueError, match="duplicada en A"):
        ComparisonPair(source_a, source_b).statistics()
