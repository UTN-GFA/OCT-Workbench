from pathlib import Path

import numpy as np

from transforms.base import TransformData
from transforms.discovery import discover_plugin_tree


def test_real_rotation_plugin_is_discovered_and_uses_surface_facade():
    registry = discover_plugin_tree(Path(__file__).resolve().parents[1] / "transforms")

    assert registry.ids("geometry") == ["rotar_90"]
    assert registry.errors == []

    data = TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([10.0, 20.0]),
        Z=np.array([0.0, 0.0]),
        depth_mm=np.array([[[1.0]], [[2.0]]]),
    )
    result = registry.create("rotar_90", {"sentido": "1"}).apply(data)

    assert np.array_equal(result.X, np.array([5.5, -4.5]))
    assert np.array_equal(result.Y, np.array([14.5, 15.5]))
    assert np.array_equal(result.depth_mm, data.depth_mm)
    assert np.array_equal(data.X, np.array([0.0, 1.0]))
