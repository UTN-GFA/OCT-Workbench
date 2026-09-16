import json

import numpy as np
import pytest

from export.exporter import to_npz
from model.dataset import OCTDataset
from model.surface_assembly import (
    SurfacePatchSpec,
    assemble_surface_patches,
    derived_from_surface_assembly,
)
from transforms.base import TransformData


def _grid_patch(x_values, y_values, z_value, source):
    xx, yy = np.meshgrid(np.asarray(x_values, dtype=float), np.asarray(y_values, dtype=float), indexing="xy")
    x = xx.ravel()
    y = yy.ravel()
    z = np.full(x.shape, z_value, dtype=float)
    depth_mm = (x + 2.0 * y)[:, None, None]
    return TransformData(
        X=x,
        Y=y,
        Z=z,
        depth_mm=depth_mm,
        amplitude=np.ones_like(depth_mm),
        metadata={"source": source},
    )


def test_surface_assembly_keeps_native_steps_extents_and_physical_z():
    lower = _grid_patch(
        np.arange(0.0, 3.0, 0.5),
        np.arange(0.0, 5.0 + 0.001, 0.5),
        0.0,
        "A",
    )
    upper = _grid_patch(
        np.arange(3.0, 7.0 + 0.001, 0.3),
        np.arange(0.0, 4.0 + 0.001, 0.3),
        4.0,
        "B",
    )

    result = assemble_surface_patches([
        SurfacePatchSpec(data=lower, source="A", name="inferior", z_mm=0.0),
        SurfacePatchSpec(data=upper, source="B", name="superior", z_mm=4.0),
    ])

    assert result.data.n_points == lower.n_points + upper.n_points
    assert set(np.unique(result.data.Z)) == {0.0, 4.0}
    assert result.data.X.min() == 0.0
    assert result.data.X.max() == pytest.approx(6.9)
    assert result.data.Y.min() == 0.0
    assert result.data.Y.max() == pytest.approx(5.0)
    assert len(result.patch_stats) == 2
    assert result.patch_stats[0]["step_x_mm"] == pytest.approx(0.5)
    assert result.patch_stats[1]["step_x_mm"] == pytest.approx(0.3)
    assert result.patch_stats[0]["y_max_mm"] == pytest.approx(5.0)
    assert result.patch_stats[1]["y_max_mm"] == pytest.approx(3.9)
    assert result.warnings == []




def test_reopened_surface_assembly_keeps_tolerance_for_native_grid(tmp_path):
    from oct_workbench_gui import _native_patch_grid

    data = TransformData(
        X=np.array([0.0, 1.0, 0.0004, 1.0003, 0.0002, 0.9998]),
        Y=np.array([0.0, 0.0003, 0.5, 0.5002, 1.0, 1.0004]),
        Z=np.zeros(6),
        coordinate_tolerance_mm=0.002,
        depth_mm=np.arange(6, dtype=float)[:, None, None],
        amplitude=np.ones((6, 1, 1)),
    )
    result = assemble_surface_patches([
        SurfacePatchSpec(data=data, source="A", name="jitter", tolerance_mm=0.002),
    ])
    derived = derived_from_surface_assembly(result, {"A": "/tmp/a.npz"}, "Jitter")
    reopened = OCTDataset.from_file(to_npz(derived, str(tmp_path / "jitter.npz")))

    assert reopened.coordinate_tolerance_mm == pytest.approx(0.002)
    grid = _native_patch_grid(reopened.X, reopened.Y, reopened.depth_mm[:, 0, 0], reopened.coordinate_tolerance_mm)
    assert grid is not None
    assert grid[2].shape == (3, 2)


def test_surface_assembly_does_not_fill_discontinuous_x_gaps():
    data = TransformData(
        X=np.array([0.0, 1.0, 4.0, 5.0]),
        Y=np.zeros(4),
        Z=np.zeros(4),
        depth_mm=np.ones((4, 1, 1)),
    )

    result = assemble_surface_patches([
        SurfacePatchSpec(data=data, source="A", name="discontinua", z_mm=0.0),
    ])

    assert result.data.n_points == 4
    assert not np.any(np.isclose(result.data.X, 2.0))
    assert not np.any(np.isclose(result.data.X, 3.0))
    assert result.patch_stats[0]["n_points"] == 4


def test_surface_assembly_derivative_preserves_two_sources_and_patch_metadata(tmp_path):
    lower = _grid_patch([0.0, 0.5], [0.0, 0.5], 0.0, "A")
    upper = _grid_patch([3.0, 3.3], [0.0, 0.3], 4.0, "B")
    result = assemble_surface_patches([
        SurfacePatchSpec(data=lower, source="A", name="inferior", z_mm=0.0),
        SurfacePatchSpec(data=upper, source="B", name="superior", z_mm=4.0),
    ])

    derived = derived_from_surface_assembly(
        result,
        {"A": "/tmp/a.npz", "B": "/tmp/b.npz"},
        "Escalón compuesto",
    )
    assert result.data.metadata["position_tolerance_mm"] == pytest.approx(0.002)
    assert result.data.metadata["position_tolerance_um"] == pytest.approx(2.0)
    assert derived.metadata["derived_operation"] == "ensamblado_superficies_nativas"
    assert derived.metadata["position_tolerance_mm"] == pytest.approx(0.002)
    assert len(derived.metadata["surface_patches"]) == 2
    assert derived.provenance.parameters["sources"]["A"] == "/tmp/a.npz"

    path = to_npz(derived, str(tmp_path / "escalon.npz"))
    reopened = OCTDataset.from_file(path)
    assert reopened.sample_name == "Escalón compuesto"
    assert reopened.n_points == result.data.n_points
    extraction_parameters = json.loads(reopened.metadata["extraction_parameters"])
    assert extraction_parameters["operation"] == "ensamblado_superficies_nativas"
    assert extraction_parameters["resampling"] == "none"
    assert len(extraction_parameters["patches"]) == 2
