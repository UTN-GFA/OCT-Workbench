import numpy as np
import pytest

from model.dataset import DatasetType, OCTDataset
from work_io.loader import load


@pytest.fixture
def schema6_arrays():
    # Dos puntos, dos mediciones y un perfil con eje axial propio.
    return {
        "x_mm": np.array([0.0, 1.0]),
        "y_mm": np.array([0.0, 0.0]),
        "z_mm": np.array([0.0, 1.0]),
        "wavelengths_nm": np.array([800.0, 850.0]),
        "depth_m": np.array([[[1e-3], [2e-3]], [[3e-3], [4e-3]]]),
        "amplitude": np.ones((2, 2, 1)),
        "win_depth_min_m": np.array([1e-3]),
        "win_depth_max_m": np.array([5e-3]),
        "profile_mod_w0": np.ones((2, 2, 4)),
        "profile_depth_m_w0": np.linspace(1e-3, 4e-3, 4),
        "schema_version": "6.0.0",
        "software_version": "OCT Static V6.1",
        "sample_name": "schema6",
        "planned_points": 2,
        "acquired_points": 2,
        "dark": True,
        "nonlinearity": True,
        "o_d_fib_um": 5.0,
        "o_wl_nm": 850.0,
        "o_f_col_mm": 18.0,
        "o_f_obj_mm": 9.0,
    }


def _write_npz(path, data):
    np.savez(path, **data)
    return path


def _write_h5(path, data):
    h5py = pytest.importorskip("h5py")
    array_keys = {
        "x_mm", "y_mm", "z_mm", "wavelengths_nm", "depth_m", "amplitude",
        "win_depth_min_m", "win_depth_max_m", "profile_mod_w0",
        "profile_depth_m_w0",
    }
    with h5py.File(path, "w") as handle:
        for key, value in data.items():
            if key in array_keys:
                handle.create_dataset(key, data=value)
            else:
                handle.attrs[key] = value
    return path


@pytest.mark.parametrize("writer, suffix", [(_write_npz, ".npz"), (_write_h5, ".h5")])
def test_schema6_roundtrip_preserves_positions_metadata_and_profile_axis(
    tmp_path, schema6_arrays, writer, suffix
):
    path = writer(tmp_path / f"schema6{suffix}", schema6_arrays)

    dataset = OCTDataset.from_file(path)

    assert dataset.metadata["schema_version"] == "6.0.0"
    assert np.array_equal(dataset.Z, schema6_arrays["z_mm"])
    assert dataset.m_measurements == 2
    assert dataset.metadata["dark_enabled"] is True
    assert dataset.metadata["nonlinearity_enabled"] is True
    assert dataset.optics.d_fiber_um == pytest.approx(5.0)
    assert dataset.optics.wl_nm == pytest.approx(850.0)
    assert dataset.depth_mm is not None
    assert np.allclose(dataset.depth_mm, schema6_arrays["depth_m"] * 1000.0)
    assert dataset.profile_depth_axes_m[0].shape == (4,)
    assert np.allclose(dataset.profile_depth_axes_m[0], schema6_arrays["profile_depth_m_w0"])
    assert dataset.depth_axis_kind == "physical_depth_mm"
    assert dataset.is_physical_depth is True


def test_schema6_profile_payload_does_not_force_volume_classification(tmp_path, schema6_arrays):
    data = dict(schema6_arrays)
    data["x_mm"] = np.array([0.0, 1.0, 0.0, 1.0])
    data["y_mm"] = np.array([0.0, 0.0, 1.0, 1.0])
    data["z_mm"] = np.zeros(4)
    data["depth_m"] = np.ones((4, 2, 1)) * 1e-3
    data["amplitude"] = np.ones((4, 2, 1))
    data["profile_mod_w0"] = np.ones((4, 2, 4))
    data["planned_points"] = 4
    data["acquired_points"] = 4
    path = _write_npz(tmp_path / "topography_with_profiles.npz", data)

    dataset = OCTDataset.from_file(path)

    assert dataset.dataset_type == DatasetType.TOPOGRAPHY


def test_schema6_loader_rejects_inconsistent_position_lengths(tmp_path, schema6_arrays):
    data = dict(schema6_arrays)
    data["y_mm"] = np.array([0.0])
    path = _write_npz(tmp_path / "bad_lengths.npz", data)

    with pytest.raises(ValueError, match="X/Y/Z"):
        load(path)


def test_grid_uses_persisted_position_tolerance(tmp_path):
    path = tmp_path / "jittered_grid.npz"
    np.savez(
        path,
        x_mm=np.array([0.0001, 1.0001, 0.0002, 1.0002, -0.0001, 0.9999]),
        y_mm=np.array([0.0001, 0.0002, 0.9999, 1.0001, 2.0001, 1.9999]),
        z_mm=np.zeros(6),
        depth_m=np.arange(6, dtype=float).reshape(6, 1, 1) * 1e-3,
        amplitude=np.ones((6, 1, 1)),
        wavelengths_nm=np.array([800.0]),
        win_depth_min_m=np.array([0.0]),
        win_depth_max_m=np.array([0.003]),
        schema_version="6.0.0",
        position_tolerance_mm=0.002,
    )
    dataset = OCTDataset.from_file(path)
    assert (dataset.grid.nx, dataset.grid.ny) == (2, 3)
    _, _, grid = dataset.topography_grid()
    assert np.isfinite(grid).sum() == 6
