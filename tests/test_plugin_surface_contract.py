"""Pruebas del contrato de preservación de la fachada de plugins."""

import numpy as np
import pytest

from transforms.base import TransformData
from transforms.plugin_api import PluginSpec, PluginTransform, PluginValidationError


def test_plugin_cannot_drop_metadata_or_mask_when_returning_raw_transform_data():
    source = TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 1.0]),
        Z=np.array([0.0, 0.0]),
        depth_mm=np.ones((2, 1)),
        mask=np.array([True, False]),
        units={"depth_mm": "mm"},
        metadata={"sample": "A"},
    )
    spec = PluginSpec(
        id="drop_metadata",
        kind="geometry",
        name="Pierde metadata",
        description="Debe ser rechazado",
        apply_function=lambda superficie, parametros: TransformData(
            X=superficie.X,
            Y=superficie.Y,
            Z=superficie.Z,
            depth_mm=superficie.depth_mm,
        ),
    )

    with pytest.raises(PluginValidationError, match="metadata|unidades|máscara"):
        PluginTransform(spec).apply(source)


def _amplitude_source() -> TransformData:
    return TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 1.0]),
        Z=np.array([0.0, 0.0]),
        depth_mm=np.array([[0.2], [0.8]]),
        amplitude=np.array([[100.0], [200.0]]),
        metadata={"sample": "A"},
    )


def test_surface_explicitly_replaces_depth_mm_and_amplitude_together():
    from transforms.plugin_surface import Superficie

    source = _amplitude_source()
    result = Superficie.from_data(source).con_z_y_amplitud(
        np.array([[0.2], [np.nan]]),
        np.array([[100.0], [np.nan]]),
    ).to_data()

    assert np.isnan(result.depth_mm[1, 0])
    assert np.isnan(result.amplitude[1, 0])
    assert np.array_equal(source.depth_mm, np.array([[0.2], [0.8]]), equal_nan=True)
    assert np.array_equal(source.amplitude, np.array([[100.0], [200.0]]), equal_nan=True)


def test_plugin_cannot_change_amplitude_without_explicit_declaration():
    source = _amplitude_source()
    spec = PluginSpec(
        id="implicit_amplitude",
        kind="filter",
        name="Amplitud implícita",
        description="Debe ser rechazado",
        apply_function=lambda superficie, parametros: superficie.con_z_y_amplitud(
            superficie.z,
            superficie.amplitude * 0.5,
        ),
    )

    with pytest.raises(PluginValidationError, match="amplitud sin declararlo"):
        PluginTransform(spec).apply(source)


def test_plugin_can_change_amplitude_when_declared_explicitly():
    source = _amplitude_source()

    class Module:
        PLUGIN = {
            "id": "explicit_amplitude",
            "tipo": "filter",
            "nombre": "Amplitud explícita",
            "descripcion": "Puede cambiar OPD y amplitud",
            "modifica_amplitud": True,
        }

        @staticmethod
        def aplicar(superficie, parametros):
            return superficie.con_z_y_amplitud(
                superficie.z,
                superficie.amplitude * 0.5,
            )

    spec = PluginSpec.from_module(Module)
    result = PluginTransform(spec).apply(source)

    assert np.array_equal(result.amplitude, np.array([[50.0], [100.0]]))
    assert np.array_equal(source.amplitude, np.array([[100.0], [200.0]]))


def test_plugin_cannot_remove_depth_mm_from_existing_data():
    source = _amplitude_source()
    spec = PluginSpec(
        id="drop_depth_mm",
        kind="geometry",
        name="Elimina OPD",
        description="Debe ser rechazado",
        apply_function=lambda superficie, parametros: TransformData(
            X=superficie.X,
            Y=superficie.Y,
            Z=superficie.Z,
            amplitude=superficie.amplitude,
            metadata=superficie.metadata,
        ),
    )

    with pytest.raises(PluginValidationError, match="eliminar los datos OPD"):
        PluginTransform(spec).apply(source)
