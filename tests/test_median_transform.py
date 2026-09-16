import numpy as np

from transforms.base import TransformData
from tests.plugin_transforms import FilterMedian


def test_filter_median_reduces_local_spike_without_mutating_source():
    x_values = np.arange(5.0)
    y_values = np.arange(5.0)
    X, Y = np.meshgrid(x_values, y_values)
    depth_mm_grid = np.ones((5, 5), dtype=float)
    depth_mm_grid[2, 2] = 99.0
    depth_mm_grid[0, 0] = np.nan
    data = TransformData(
        X=X.ravel(),
        Y=Y.ravel(),
        Z=np.zeros(25),
        depth_mm=depth_mm_grid.reshape(25, 1, 1),
        units={"depth_mm": "mm", "X": "mm", "Y": "mm"},
        metadata={"source_id": "synthetic"},
    )
    original = data.depth_mm.copy()

    result = FilterMedian(kernel_size=4).apply(data)

    assert result.depth_mm[12, 0, 0] == 1.0
    assert np.isnan(result.depth_mm[0, 0, 0])
    assert np.array_equal(data.depth_mm, original, equal_nan=True)
    assert result.units == data.units
    assert result.metadata == data.metadata
    assert FilterMedian(kernel_size=4).name == "Mediana 5×5"
