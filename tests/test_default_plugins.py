from pathlib import Path

import numpy as np

from transforms.base import TransformData
from transforms.discovery import discover_plugin_tree


def test_default_filters_are_discovered_as_integrated_plugins_without_duplicate_local_controls():
    registry = discover_plugin_tree(Path(__file__).resolve().parents[1] / "transforms")

    visible_filters = registry.ids("filter")
    all_filters = registry.ids("filter", include_integrated=True)

    assert "rotar_90" not in visible_filters
    assert "filter_median" in all_filters
    assert "mask_depth_range" in all_filters
    assert "offset_minimum_to_zero" in all_filters
    assert "filter_median" not in visible_filters
    assert "rotar_90" in registry.ids("geometry")


def test_default_mask_plugin_preserves_depth_mm_amplitude_alignment_and_source():
    registry = discover_plugin_tree(Path(__file__).resolve().parents[1] / "transforms")
    source = TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 0.0]),
        Z=np.array([0.0, 0.0]),
        depth_mm=np.array([[[0.2]], [[0.8]]]),
        amplitude=np.array([[[10.0]], [[20.0]]]),
    )

    result = registry.create("mask_depth_range", {"minimum_mm": 0.0, "maximum_mm": 0.5}).apply(source)

    assert np.isfinite(result.depth_mm[0, 0, 0])
    assert np.isnan(result.depth_mm[1, 0, 0])
    assert np.isnan(result.amplitude[1, 0, 0])
    assert np.array_equal(source.depth_mm, np.array([[[0.2]], [[0.8]]]))
    assert np.array_equal(source.amplitude, np.array([[[10.0]], [[20.0]]]))
