from pathlib import Path

import numpy as np

from transforms.base import TransformData
from transforms.discovery import discover_plugin_tree


def test_default_geometry_plugins_are_integrated_without_duplicate_local_controls():
    registry = discover_plugin_tree(Path(__file__).resolve().parents[1] / "transforms")

    assert registry.ids("geometry") == ["rotar_90"]
    assert set(registry.ids("geometry", include_integrated=True)) >= {
        "invert_axis", "mirror", "offset_geometry", "center_origin", "rotar_90",
    }


def test_integrated_geometry_plugins_preserve_coordinates_and_source():
    registry = discover_plugin_tree(Path(__file__).resolve().parents[1] / "transforms")
    source = TransformData(
        X=np.array([1.0, 3.0]),
        Y=np.array([2.0, 4.0]),
        Z=np.array([5.0, 6.0]),
        depth_mm=np.array([[[0.2]], [[0.8]]]),
    )

    inverted = registry.create("invert_axis", {"axis": "X"}).apply(source)
    mirrored = registry.create("mirror", {"axis": "X"}).apply(source)
    offset = registry.create("offset_geometry", {"axis": "Y", "value_mm": 2.5}).apply(source)
    centered = registry.create("center_origin").apply(source)

    assert np.array_equal(inverted.X, -source.X)
    assert np.array_equal(mirrored.X, np.array([3.0, 1.0]))
    assert np.array_equal(offset.Y, source.Y + 2.5)
    assert np.allclose(centered.X, [-1.0, 1.0])
    assert np.array_equal(source.X, [1.0, 3.0])
