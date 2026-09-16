"""Pruebas del núcleo de extracción, metadata y calidad."""

import os
import sys
from typing import get_type_hints

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model.dataset import OCTDataset, ScanGrid
from extract.cuts import extract_cuts
from gui.metadata import build_metadata_comparison, quality_summary
from oct_workbench_gui import MetadataDialog, dataset_card_text, display_scale


def make_dataset(tmp_path, name="A", offset=0.0, one_dimensional=False):
    if one_dimensional:
        x = np.linspace(0.0, 1.0, 5)
        y = np.zeros_like(x)
    else:
        x_values = np.linspace(0.0, 1.0, 5)
        y_values = np.linspace(0.0, 0.8, 4)
        x, y = [], []
        for y_value in y_values:
            for x_value in x_values:
                x.append(x_value)
                y.append(y_value)
        x, y = np.asarray(x), np.asarray(y)

    z = np.zeros_like(x)
    depth_mm = (0.5 + x * 0.1 + y * 0.2 + offset).reshape(-1, 1, 1)
    amplitude = np.full_like(depth_mm, 1000.0)
    if not one_dimensional:
        amplitude[2, 0, 0] = np.nan

    path = tmp_path / f"{name}.npz"
    np.savez(
        path,
        X=x,
        Y=y,
        Z=z,
        depth_m=(depth_mm) / 1000.0,
        amplitude=amplitude,
        win_depth_min_m=(np.array([0.3])) / 1000.0,
        win_depth_max_m=(np.array([0.8])) / 1000.0,
        SAMPLE_NAME=name,
        SCHEMA_VERSION="6.0.0",
        M_MEASUREMENTS=np.int32(1),
        N_POINTS_TOTAL=np.int32(len(x)),
        N_POINTS_ACQUIRED=np.int32(len(x)),
        ABORTED=np.bool_(False),
    )
    return OCTDataset.from_file(path)






def test_scan_grid_recovers_step_with_nonfinite_coordinate_entries():
    grid = ScanGrid(
        n_points=4,
        x_unique=np.array([0.5, 0.6, 0.7, np.nan]),
        y_unique=np.array([1.0, 1.1]),
        z_unique=np.array([0.0]),
        nx=4,
        ny=2,
        nz=1,
    )

    assert grid.x_step == pytest.approx(0.1)


def test_topography_grid_keeps_coordinate_mesh_finite(tmp_path):
    dataset = make_dataset(tmp_path)

    x_grid, y_grid, z_grid = dataset.topography_grid(0, 0)

    assert np.isfinite(x_grid).all()
    assert np.isfinite(y_grid).all()
    assert np.isnan(z_grid).sum() == 0
    assert x_grid.shape == z_grid.shape
    assert y_grid.shape == z_grid.shape


def test_extract_cuts_returns_x_and_y_profiles_for_2d(tmp_path):
    dataset = make_dataset(tmp_path)

    cuts = extract_cuts(dataset, x_value=0.5, y_value=0.4)

    assert cuts.dimension == "2D"
    assert cuts.x_axis == "X"
    assert cuts.y_axis == "Y"
    assert np.allclose(cuts.x_position, np.linspace(0.0, 1.0, 5))
    assert np.allclose(cuts.y_position, np.linspace(0.0, 0.8, 4))
    assert cuts.x_depth_mm.shape == (5,)
    assert cuts.y_depth_mm.shape == (4,)
    assert cuts.selected_x == pytest.approx(0.5)
    assert cuts.selected_y == pytest.approx(0.5333333333333333)


def test_extract_cuts_returns_direct_profile_for_1d(tmp_path):
    dataset = make_dataset(tmp_path, one_dimensional=True)

    cuts = extract_cuts(dataset, x_value=0.7, y_value=0.0)

    assert cuts.dimension == "1D"
    assert cuts.x_axis == "X"
    assert cuts.y_axis is None
    assert cuts.x_position.shape == (5,)
    assert cuts.x_depth_mm.shape == (5,)
    assert cuts.y_depth_mm is None


def test_metadata_comparison_highlights_differences_and_compatibility(tmp_path):
    dataset_a = make_dataset(tmp_path, name="A")
    dataset_b = make_dataset(tmp_path, name="B", offset=0.01)

    comparison = build_metadata_comparison(dataset_a, dataset_b)

    assert comparison.has_b is True
    assert comparison.compatible_for_visual is True
    assert comparison.compatible_for_pointwise is True
    assert comparison.value("schema_version").same is True
    assert comparison.value("sample_name").same is False
    assert comparison.value("n_points_total").same is True


def test_metadata_comparison_rejects_different_z_levels(tmp_path):
    dataset_a = make_dataset(tmp_path, name="A")
    dataset_b = make_dataset(tmp_path, name="B")
    dataset_b._Z += 1.0

    comparison = build_metadata_comparison(dataset_a, dataset_b)

    assert comparison.compatible_for_visual is True
    assert comparison.compatible_for_pointwise is False
    assert any("coordenadas" in warning.lower() for warning in comparison.warnings)


def test_metadata_dialog_annotations_resolve():
    hints = get_type_hints(MetadataDialog._compatibility_text)

    assert hints["comparison"].__name__ == "MetadataComparison"


    scale, unit = display_scale(np.array([0.000229, 0.000225]))

    assert scale == pytest.approx(1000.0)
    assert unit == "µm"


def test_quality_summary_counts_nan_and_valid_points(tmp_path):
    dataset = make_dataset(tmp_path)

    quality = quality_summary(dataset)

    assert quality.total_depth_mm_points == 20
    assert quality.valid_depth_mm_points == 20
    assert quality.total_amplitude_points == 20
    assert quality.valid_amplitude_points == 19
    assert quality.nan_amplitude_points == 1
    assert quality.total_points == dataset.n_points
    assert quality.finite_coordinate_points == dataset.n_points
    assert quality.expected_points == dataset.metadata["n_points_total"]
    assert quality.acquired_points == dataset.metadata["n_points_acquired"]
    assert quality.scan_aborted is False


def test_dataset_card_text_contains_identification_only(tmp_path):
    dataset = make_dataset(tmp_path)

    card = dataset_card_text(dataset)

    assert dataset.filename in card
    assert "OPD válidos" not in card
    assert "Amplitud válida" not in card
    assert "Adquiridos" not in card
    assert "Estado:" not in card
