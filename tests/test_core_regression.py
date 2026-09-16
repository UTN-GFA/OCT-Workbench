import numpy as np
import pytest

from extract import extract_profile_x
from model.dataset import OCTDataset
from transforms.base import TransformedView
from tests.plugin_transforms import FilterMedian, LevelFromRegions, LevelPlane


def make_multim_dataset(tmp_path):
    x = np.array([0.0, 1.0, 0.0, 1.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    z = np.zeros(4)
    depth_mm = np.zeros((4, 2, 1))
    depth_mm[:, 0, 0] = 10.0 + x + y
    depth_mm[:, 1, 0] = 100.0 + 2.0 * x + y
    amplitude = np.ones_like(depth_mm)
    path = tmp_path / "multi_m.npz"
    np.savez(
        path,
        x_mm=x, y_mm=y, z_mm=z,
        wavelengths_nm=np.array([800.0]),
        depth_m=depth_mm / 1000.0,
        amplitude=amplitude,
        win_depth_min_m=np.array([1e-3]),
        win_depth_max_m=np.array([2e-3]),
        schema_version="6.0.0",
    )
    return OCTDataset.from_file(path)


def test_dataset_arrays_and_metadata_are_defensive(tmp_path):
    dataset = make_multim_dataset(tmp_path)
    x = dataset.X
    x[0] = 999.0
    metadata = dataset.metadata
    metadata["sample_name"] = "mutated"

    assert dataset.X[0] == 0.0
    assert dataset.sample_name != "mutated"


def test_level_plane_changes_only_selected_measurement(tmp_path):
    dataset = make_multim_dataset(tmp_path)
    view = TransformedView(dataset)
    view.pipeline.add(LevelPlane(win_id=0, measurement=0))
    transformed = view.transformed_data

    assert np.allclose(transformed.depth_mm[:, 1, 0], dataset.depth_mm[:, 1, 0])
    assert not np.allclose(transformed.depth_mm[:, 0, 0], dataset.depth_mm[:, 0, 0])


def test_level_plane_rejects_negative_window_and_measurement(tmp_path):
    dataset = make_multim_dataset(tmp_path)

    with pytest.raises(ValueError, match="win_id no puede ser menor"):
        LevelPlane(win_id=-1, measurement=0)

    with pytest.raises(ValueError, match="measurement no puede ser menor"):
        LevelPlane(win_id=0, measurement=-1)



def test_surface_transforms_reject_negative_window(tmp_path):
    dataset = make_multim_dataset(tmp_path)

    with pytest.raises(ValueError, match="win_id no puede ser menor"):
        FilterMedian(win_id=-1)
    with pytest.raises(ValueError, match="win_id no puede ser menor"):
        LevelFromRegions(regions=[(-1.0, 2.0, -1.0, 2.0)], win_id=-1)



def test_profile_extraction_selects_measurement_and_window(tmp_path):
    dataset = make_multim_dataset(tmp_path)
    profile = extract_profile_x(dataset, y_value=0.0, measurement=1, win_id=0)

    assert profile.depth_mm.shape == (2, 1, 1)
    assert np.allclose(profile.depth_mm[:, 0, 0], [100.0, 102.0])


def test_topography_grid_rejects_multiz_duplicate_xy(tmp_path):
    dataset = make_multim_dataset(tmp_path)
    path = tmp_path / "multiz.npz"
    np.savez(
        path,
        x_mm=np.array([0.0, 0.0]),
        y_mm=np.array([0.0, 0.0]),
        z_mm=np.array([0.0, 1.0]),
        wavelengths_nm=np.array([800.0]),
        depth_m=np.ones((2, 1, 1)) * 1e-3,
        amplitude=np.ones((2, 1, 1)),
        win_depth_min_m=np.array([1e-3]),
        win_depth_max_m=np.array([2e-3]),
        schema_version="6.0.0",
    )
    multiz = OCTDataset.from_file(path)

    with pytest.raises(ValueError, match="única cota Z"):
        multiz.topography_grid()


def test_transformed_view_reuses_persisted_coordinate_tolerance(tmp_path):
    path = tmp_path / "jittered.npz"
    np.savez(
        path,
        x_mm=np.array([0.0, 1.0005, 0.0004, 1.0001]),
        y_mm=np.array([0.0, 0.0002, 1.0004, 1.0001]),
        z_mm=np.zeros(4),
        wavelengths_nm=np.array([800.0]),
        depth_m=np.arange(4, dtype=float).reshape(4, 1, 1) / 1000.0,
        amplitude=np.ones((4, 1, 1)),
        win_depth_min_m=np.array([1e-3]),
        win_depth_max_m=np.array([2e-3]),
        position_tolerance_mm=np.array(0.002),
        schema_version="6.0.0",
    )
    dataset = OCTDataset.from_file(path)
    view = TransformedView(dataset)

    dataset_grid = dataset.topography_grid()[2]
    view_grid = view.topography_grid()[2]

    assert dataset_grid.shape == (2, 2)
    assert view_grid.shape == (2, 2)
    assert np.isfinite(view_grid).all()


def test_surface_filter_is_not_gaussian_or_outlier_api():
    """La limpieza de topografía queda limitada a mediana 2D explícita."""
    import transforms

    assert not hasattr(transforms, "FilterGaussian")
    assert not hasattr(transforms, "RemoveOutliers")
