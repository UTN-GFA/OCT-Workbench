import numpy as np
import pytest

from transforms.base import TransformData
from tests.plugin_transforms import Mirror
from transforms.plugin_api import PluginSpec, PluginTransform
from transforms.plugin_surface import PluginSurfaceError, Superficie


def make_data():
    return TransformData(
        X=np.array([0.0, 1.0, np.nan]),
        Y=np.array([10.0, 20.0, 30.0]),
        Z=np.array([0.0, 0.0, 0.0]),
        depth_mm=np.array([1.0, np.nan, 3.0]),
        amplitude=np.array([10.0, 11.0, 12.0]),
        mask=np.array([True, False, True]),
        units={"length": "mm", "depth_mm": "mm"},
        metadata={"sample": "mirror-equivalence"},
        provenance=[{"operation": "fixture"}],
        coordinate_tolerance_mm=1e-6,
    )


def test_superficie_con_z_preserves_metadata_mask_nan_and_source():
    source = make_data()
    surface = Superficie.from_data(source)
    replacement = np.array([9.0, np.nan, 7.0])

    result = surface.con_z(replacement).to_data()

    assert np.array_equal(result.depth_mm, replacement, equal_nan=True)
    assert np.array_equal(result.mask, source.mask)
    assert np.array_equal(result.amplitude, source.amplitude)
    assert result.units == source.units
    assert result.metadata == source.metadata
    assert result.provenance == source.provenance
    assert np.array_equal(source.depth_mm, np.array([1.0, np.nan, 3.0]), equal_nan=True)


def test_superficie_espejar_is_nan_safe_and_preserves_other_arrays():
    source = make_data()

    result = Superficie.from_data(source).espejar("X").to_data()

    assert np.array_equal(result.X, np.array([1.0, 0.0, np.nan]), equal_nan=True)
    assert np.array_equal(result.Y, source.Y)
    assert np.array_equal(result.Z, source.Z)
    assert np.array_equal(result.depth_mm, source.depth_mm, equal_nan=True)
    assert np.array_equal(result.mask, source.mask)
    assert np.array_equal(source.X, np.array([0.0, 1.0, np.nan]), equal_nan=True)


def test_superficie_rotar_90_preserves_point_order_and_values():
    source = TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([10.0, 20.0]),
        Z=np.array([0.0, 0.0]),
        depth_mm=np.array([[[1.0]], [[2.0]]]),
    )

    result = Superficie.from_data(source).rotar_90().to_data()

    assert np.array_equal(result.X, np.array([5.5, -4.5]))
    assert np.array_equal(result.Y, np.array([14.5, 15.5]))
    assert np.array_equal(result.depth_mm, source.depth_mm)


def test_superficie_rejects_z_with_wrong_shape():
    surface = Superficie.from_data(make_data())

    with pytest.raises(PluginSurfaceError, match="shape"):
        surface.con_z(np.zeros(2))


def test_plugin_mirror_and_facade_are_equivalent_with_nan_coordinates():
    source = make_data()
    spec = PluginSpec(
        id="espejar_x_facade",
        kind="geometry",
        name="Espejar X fachada",
        description="Equivalencia del helper de laboratorio",
        apply_function=lambda superficie, parametros: superficie.espejar("X"),
    )

    expected = Mirror("X").apply(source)
    plugin = PluginTransform(spec).apply(source)

    assert np.array_equal(expected.X, plugin.X, equal_nan=True)
    assert np.array_equal(expected.Y, plugin.Y, equal_nan=True)
    assert np.array_equal(expected.Z, plugin.Z, equal_nan=True)
    assert np.array_equal(expected.depth_mm, plugin.depth_mm, equal_nan=True)
    assert np.array_equal(expected.mask, plugin.mask)
    assert expected.metadata == plugin.metadata == source.metadata
    assert expected.provenance == plugin.provenance == source.provenance
