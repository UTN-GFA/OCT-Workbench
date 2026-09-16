import numpy as np
import pytest

from extract.cuts import Cuts
from extract.derived import DerivedObject, ExtractionType, Provenance
from model.dataset import OCTDataset, Optics, ScanGrid, WindowConfig
from model.level_assembly import LevelSelection
from model.surface_assembly import SurfacePatchSpec
from transforms.base import TransformData


def test_optics_uses_static_names_and_keeps_legacy_aliases():
    optics = Optics.from_dict(
        {
            "d_fiber_um": 5.0,
            "wl_nm": 850.0,
            "f_col_mm": 18.0,
            "f_obj_mm": 9.0,
        }
    )

    assert optics.fiber_diameter_um == pytest.approx(5.0)
    assert optics.wavelength_nm == pytest.approx(850.0)
    assert optics.collimator_focal_length_mm == pytest.approx(18.0)
    assert optics.objective_focal_length_mm == pytest.approx(9.0)

    assert optics.d_fiber_um == optics.fiber_diameter_um
    assert optics.wl_nm == optics.wavelength_nm
    assert optics.f_col_mm == optics.collimator_focal_length_mm
    assert optics.f_obj_mm == optics.objective_focal_length_mm


def test_optics_accepts_static_names_as_input():
    optics = Optics.from_dict(
        {
            "fiber_diameter_um": 4.0,
            "wavelength_nm": 1310.0,
            "collimator_focal_length_mm": 20.0,
            "objective_focal_length_mm": 10.0,
        }
    )

    assert optics.fiber_diameter_um == pytest.approx(4.0)
    assert optics.wavelength_nm == pytest.approx(1310.0)
    assert optics.collimator_focal_length_mm == pytest.approx(20.0)
    assert optics.objective_focal_length_mm == pytest.approx(10.0)


def _write_static_named_dataset(path):
    x = np.array([0.0, 1.0])
    y = np.array([0.0, 0.0])
    z = np.array([0.0, 0.0])
    np.savez(
        path,
        x_mm=x,
        y_mm=y,
        z_mm=z,
        depth_m=np.array([[[0.001]], [[0.002]]]),
        amplitude=np.ones((2, 1, 1)),
        win_depth_min_m=np.array([0.001]),
        win_depth_max_m=np.array([0.002]),
        measurements_per_point=np.int32(1),
        planned_points=np.int32(2),
        acquired_points=np.int32(2),
        duration_s=np.float64(1.5),
        k_samples=np.int32(4),
        global_profile_samples=np.int32(8),
        aborted=np.bool_(False),
    )


def test_dataset_exposes_static_names_with_legacy_coordinate_aliases(tmp_path):
    path = tmp_path / "static_names.npz"
    _write_static_named_dataset(path)
    dataset = OCTDataset.from_file(path)

    assert np.array_equal(dataset.x_mm, dataset.X)
    assert np.array_equal(dataset.y_mm, dataset.Y)
    assert np.array_equal(dataset.z_mm, dataset.Z)
    assert dataset.measurements_per_point == 1
    assert dataset.planned_points == 2
    assert dataset.acquired_points == 2
    assert dataset.duration_s == pytest.approx(1.5)
    assert dataset.spectral_samples == 4
    assert dataset.profile_samples == 8
    assert dataset.scan_aborted is False
    assert dataset.position_tolerance_x_mm == pytest.approx(dataset.coordinate_tolerances_mm["X"])
    assert dataset.position_tolerance_y_mm == pytest.approx(dataset.coordinate_tolerances_mm["Y"])
    assert dataset.position_tolerance_z_mm == pytest.approx(dataset.coordinate_tolerances_mm["Z"])
    assert dataset.depth_axis_kind == "physical_depth_mm"
    assert not hasattr(dataset, "depth_mm_mm")
    assert dataset.depth_mm is not None
    assert np.allclose(dataset.physical_depth_mm, [[[1.0]], [[2.0]]])
    assert np.allclose(dataset.depth_m, [[[0.001]], [[0.002]]])


def test_work_objects_expose_mm_coordinate_aliases_without_copying_data_contracts():
    arrays = {
        "X": np.array([0.0, 1.0]),
        "Y": np.array([2.0, 3.0]),
        "Z": np.array([4.0, 5.0]),
    }
    transformed = TransformData(**arrays)
    derived = DerivedObject(
        "derived",
        arrays["X"],
        arrays["Y"],
        arrays["Z"],
        Provenance("source.npz", ExtractionType.REGION, {}, []),
    )

    assert np.array_equal(transformed.x_mm, transformed.X)
    assert np.array_equal(transformed.y_mm, transformed.Y)
    assert np.array_equal(transformed.z_mm, transformed.Z)
    assert np.array_equal(derived.x_mm, derived.X)
    assert np.array_equal(derived.y_mm, derived.Y)
    assert np.array_equal(derived.z_mm, derived.Z)


def test_transform_data_distinguishes_validity_masks_from_counts():
    transformed = TransformData(
        X=np.array([0.0, 1.0, np.nan]),
        Y=np.array([0.0, 1.0, 2.0]),
        Z=np.array([0.0, 1.0, 2.0]),
        depth_mm=np.array([[[1.0]], [[np.nan]], [[3.0]]]),
        amplitude=np.array([[[1.0]], [[2.0]], [[np.nan]]]),
    )

    assert transformed.coordinate_valid_mask.tolist() == [True, True, False]
    assert transformed.depth_mm_valid_mask.tolist() == [True, False, True]
    assert transformed.amplitude_valid_mask.tolist() == [True, True, False]
    assert transformed.valid_mask is None


def test_transform_data_exposes_one_profile_axis_by_window():
    transformed = TransformData(
        X=np.array([0.0]),
        Y=np.array([0.0]),
        Z=np.array([0.0]),
        profiles={2: np.array([[1.0, 2.0]])},
        profile_depth_axes_m={2: np.array([0.1, 0.2])},
    )

    assert np.array_equal(transformed.profile_depth_axis_m(2), [0.1, 0.2])
    assert transformed.profile_depth_axis_m(1) is None


def test_window_config_accepts_canonical_constructor_keywords():
    window = WindowConfig(window_index=3, depth_min_mm=1.0, depth_max_mm=2.0)

    assert window.win_id == 3
    assert window.z_min == pytest.approx(1.0)
    assert window.z_max == pytest.approx(2.0)


def test_physical_selection_and_cut_names_have_explicit_mm_aliases():
    window = WindowConfig(win_id=2, z_min=1.0, z_max=2.0)
    cuts = Cuts(
        dimension="1D",
        x_axis="X",
        y_axis=None,
        x_position=np.array([0.0]),
        x_depth_mm=np.array([1.0]),
        x_amplitude=None,
        y_position=None,
        y_depth_mm=None,
        y_amplitude=None,
        selected_x=0.5,
        selected_y=None,
        requested_x=0.4,
        requested_y=None,
    )

    assert window.window_index == 2
    assert window.depth_min_mm == pytest.approx(1.0)
    assert window.depth_max_mm == pytest.approx(2.0)
    assert window.depth_min_m == pytest.approx(0.001)
    assert window.depth_max_m == pytest.approx(0.002)
    assert cuts.x_position_mm is cuts.x_position
    assert cuts.selected_x_mm == pytest.approx(0.5)
    assert cuts.requested_x_mm == pytest.approx(0.4)


def test_level_selection_exposes_explicit_mm_bounds():
    selection = LevelSelection(
        z_mm=3.0,
        x_min=1.0,
        x_max=2.0,
        y_min=4.0,
        y_max=5.0,
    )

    assert selection.x_min_mm == pytest.approx(1.0)
    assert selection.x_max_mm == pytest.approx(2.0)
    assert selection.y_min_mm == pytest.approx(4.0)
    assert selection.y_max_mm == pytest.approx(5.0)


def test_surface_patch_exposes_explicit_mm_bounds():
    patch = SurfacePatchSpec(
        data=None,
        source="fixture",
        x_min=1.0,
        x_max=2.0,
        y_min=3.0,
        y_max=4.0,
    )

    assert patch.x_min_mm == pytest.approx(1.0)
    assert patch.x_max_mm == pytest.approx(2.0)
    assert patch.y_min_mm == pytest.approx(3.0)
    assert patch.y_max_mm == pytest.approx(4.0)


def test_scan_grid_exposes_explicit_mm_arrays_ranges_and_steps():
    grid = ScanGrid(
        n_points=4,
        x_unique=np.array([0.0, 1.0]),
        y_unique=np.array([0.0, 2.0]),
        z_unique=np.array([0.0]),
        nx=2,
        ny=2,
        nz=1,
    )

    assert np.array_equal(grid.x_unique_mm, grid.x_unique)
    assert grid.x_range_mm == pytest.approx((0.0, 1.0))
    assert grid.y_range_mm == pytest.approx((0.0, 2.0))
    assert grid.z_range_mm == pytest.approx((0.0, 0.0))
    assert grid.x_step_mm == pytest.approx(1.0)
    assert grid.y_step_mm == pytest.approx(2.0)
    assert grid.z_step_mm is None
