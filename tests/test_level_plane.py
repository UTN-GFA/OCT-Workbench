import numpy as np
import pytest

from transforms.base import TransformData
from tests.plugin_transforms import LevelFromRegions


def test_level_plane_fits_selected_region_and_applies_to_whole_level():
    x = np.array([0.0, 1.0, 0.0, 1.0, 2.0])
    y = np.array([0.0, 0.0, 1.0, 1.0, 2.0])
    z = np.zeros(5)
    depth_mm = np.array([5.0, 7.0, 8.0, 10.0, 11.0], dtype=float)[:, None, None]
    data = TransformData(X=x, Y=y, Z=z, depth_mm=depth_mm)

    result = LevelFromRegions(
        regions=[(0.0, 1.0, 0.0, 1.0)],
        win_id=0, measurement=0, level_z_mm=0.0, level_tolerance_mm=1e-6,
    ).apply(data)

    assert np.allclose(result.depth_mm[:4, 0, 0], 0.0)
    assert result.depth_mm[4, 0, 0] == pytest.approx(-4.0)
    assert np.array_equal(data.depth_mm[:, 0, 0], [5.0, 7.0, 8.0, 10.0, 11.0])


def test_level_plane_rejects_degenerate_region():
    data = TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 0.0]),
        Z=np.zeros(2),
        depth_mm=np.ones((2, 1, 1)),
    )
    with pytest.raises(ValueError, match="tres puntos no colineales"):
        LevelFromRegions(
            regions=[(0.0, 1.0, 0.0, 0.0)],
            win_id=0, measurement=0, level_z_mm=0.0, level_tolerance_mm=1e-6,
        ).apply(data)
