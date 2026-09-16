"""Pruebas de correcciones reversibles y compatibilidad A/B."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compare import assess_comparison
from extract.cuts import extract_cuts
from transforms.base import TransformedView
from tests.plugin_transforms import MaskDepthRange, Offset
from test_core import make_dataset


def make_view(dataset, minimum, maximum, offset=0.0):
    view = TransformedView(dataset)
    view.pipeline.add(MaskDepthRange(minimum, maximum))
    if offset:
        view.pipeline.add(Offset("DEPTH", offset))
    return view


def test_mask_depth_range_masks_outliers_without_modifying_source(tmp_path):
    dataset = make_dataset(tmp_path, one_dimensional=True)
    original = dataset.depth_mm.copy()

    view = make_view(dataset, 0.55, 0.63)

    assert np.array_equal(dataset.depth_mm, original, equal_nan=True)
    assert view.depth_mm.shape == dataset.depth_mm.shape
    assert np.all(np.isfinite(view.depth_mm[(view.depth_mm >= 0.55) & (view.depth_mm <= 0.63)]))
    assert np.isnan(view.depth_mm[0]).all()
    assert view.affected_points == 2
    assert view.pipeline.steps[0].parameters == {
        "minimum_mm": 0.55,
        "maximum_mm": 0.63,
        "inclusive": True,
    }


def test_mask_depth_range_masks_corresponding_amplitude_and_preserves_metadata(tmp_path):
    dataset = make_dataset(tmp_path)
    view = make_view(dataset, 0.55, 0.62)

    assert view.sample_name == dataset.sample_name
    assert view.filename == dataset.filename
    assert view.grid is dataset.grid
    assert np.isnan(view.amplitude[0]).all()
    assert view.affected_points == 13


def test_transformed_view_works_with_existing_cut_extraction(tmp_path):
    dataset = make_dataset(tmp_path)
    view = make_view(dataset, 0.55, 0.80)

    cuts = extract_cuts(view, x_value=0.5, y_value=0.0)

    assert cuts.dimension == "2D"
    assert np.isnan(cuts.x_depth_mm).any()
    assert view.dataset is dataset


def test_mask_can_apply_one_shared_offset_without_mutating_source(tmp_path):
    dataset = make_dataset(tmp_path, one_dimensional=True)
    original = dataset.depth_mm.copy()

    view = make_view(dataset, 0.50, 0.60, offset=0.10)

    assert view.offset_mm == pytest.approx(0.10)
    assert view.depth_mm[0, 0, 0] == pytest.approx(0.60)
    assert np.array_equal(dataset.depth_mm, original, equal_nan=True)


def test_compatibility_uses_physical_tolerance_for_coordinates(tmp_path):
    dataset_a = make_dataset(tmp_path, name="A")
    dataset_b = make_dataset(tmp_path, name="B")
    dataset_a._coordinate_tolerance = 0.002
    dataset_b._coordinate_tolerance = 0.002
    dataset_b._X += 0.0008
    dataset_b._Y -= 0.0008

    assessment = assess_comparison(
        dataset_a, dataset_b,
        window_a=0, measurement_a=0,
        window_b=0, measurement_b=0,
    )

    assert not any("coordenadas" in warning.lower() for warning in assessment.warnings)

    dataset_b._Z += 0.01
    z_assessment = assess_comparison(
        dataset_a, dataset_b,
        window_a=0, measurement_a=0,
        window_b=0, measurement_b=0,
    )
    assert any("coordenadas" in warning.lower() or "rango z" in warning.lower() for warning in z_assessment.warnings)


def test_comparison_rejects_invalid_selection_and_different_offsets(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    dataset_a = make_dataset(tmp_path / "a", one_dimensional=True)
    dataset_b = make_dataset(tmp_path / "b", one_dimensional=True)

    assessment = assess_comparison(
        dataset_a, dataset_b,
        window_a=1, measurement_a=2,
        window_b=0, measurement_b=3,
        offset_a=0.0, offset_b=0.0,
    )
    assert assessment.status == "not_comparable"
    assert any("ventana" in warning.lower() or "medición" in warning.lower() for warning in assessment.warnings)

    invalid = assess_comparison(
        dataset_a, dataset_b,
        window_a=0, measurement_a=0,
        window_b=0, measurement_b=0,
        offset_a=0.1, offset_b=0.0,
    )
    assert invalid.status == "not_comparable"
    assert any("offset" in warning.lower() for warning in invalid.warnings)
