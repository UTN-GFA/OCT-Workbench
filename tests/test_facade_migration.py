import numpy as np

from transforms.base import TransformData
from transforms.plugin_surface import Superficie
from tests.plugin_transforms import CenterOrigin, InvertAxis, Offset, OffsetMinimumToZero


def make_nan_data():
    return TransformData(
        X=np.array([0.0, 1.0, np.nan]),
        Y=np.array([10.0, 20.0, 30.0]),
        Z=np.array([100.0, np.nan, 300.0]),
        depth_mm=np.array([2.0, np.nan, 5.0]),
        amplitude=np.array([10.0, 11.0, 12.0]),
        mask=np.array([True, False, True]),
        units={"length": "mm", "depth_mm": "mm"},
        metadata={"fixture": "migration"},
        provenance=[{"operation": "fixture"}],
    )


def test_superficie_coordinate_helpers_are_shape_safe_and_non_destructive():
    source = make_nan_data()
    surface = Superficie.from_data(source)

    result = (
        surface.con_x(np.array([4.0, 5.0, np.nan]))
        .con_y(np.array([0.0, 10.0, 20.0]))
        .con_coordenada_z(np.array([7.0, np.nan, 9.0]))
    )

    assert np.array_equal(result.X, np.array([4.0, 5.0, np.nan]), equal_nan=True)
    assert np.array_equal(result.Y, np.array([0.0, 10.0, 20.0]))
    assert np.array_equal(result.Z, np.array([7.0, np.nan, 9.0]), equal_nan=True)
    assert np.array_equal(source.X, np.array([0.0, 1.0, np.nan]), equal_nan=True)
    assert np.array_equal(source.Y, np.array([10.0, 20.0, 30.0]))
    assert np.array_equal(source.Z, np.array([100.0, np.nan, 300.0]), equal_nan=True)


def test_superficie_desplazar_and_centrar_origen_ignore_nan_coordinates():
    source = make_nan_data()

    shifted = Superficie.from_data(source).desplazar("X", 2.5).to_data()
    centered = Superficie.from_data(source).centrar_origen().to_data()

    assert np.array_equal(shifted.X, np.array([2.5, 3.5, np.nan]), equal_nan=True)
    assert np.array_equal(centered.X, np.array([-0.5, 0.5, np.nan]), equal_nan=True)
    assert np.array_equal(centered.Y, np.array([-10.0, 0.0, 10.0]))


def test_historical_safe_transforms_match_superficie_helpers():
    source = make_nan_data()

    expected_invert_x = Superficie.from_data(source).reordenar_eje("X", -1).to_data()
    expected_offset_y = Superficie.from_data(source).desplazar("Y", 3.0).to_data()
    expected_center = Superficie.from_data(source).centrar_origen().to_data()
    expected_depth_mm = Superficie.from_data(source).con_z(
        Superficie.from_data(source).z - 2.0
    ).to_data()

    actual_invert_x = InvertAxis("X").apply(source)
    actual_offset_y = Offset("Y", 3.0).apply(source)
    actual_center = CenterOrigin().apply(source)
    actual_depth_mm = OffsetMinimumToZero().apply(source)

    assert np.array_equal(actual_invert_x.X, expected_invert_x.X, equal_nan=True)
    assert np.array_equal(actual_offset_y.Y, expected_offset_y.Y, equal_nan=True)
    assert np.array_equal(actual_center.X, expected_center.X, equal_nan=True)
    assert np.array_equal(actual_center.Y, expected_center.Y, equal_nan=True)
    assert np.array_equal(actual_depth_mm.depth_mm, expected_depth_mm.depth_mm, equal_nan=True)
