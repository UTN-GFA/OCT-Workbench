from pathlib import Path

import numpy as np
import pytest

from transforms.base import TransformData
from transforms.discovery import discover_plugins
from transforms.plugin_api import PluginValidationError


def make_data():
    return TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 1.0]),
        Z=np.array([0.0, 0.0]),
        depth_mm=np.array([[[1.0]], [[2.0]]]),
        mask=np.array([True, True]),
    )


def write_plugin(directory: Path, filename: str, source: str) -> Path:
    path = directory / filename
    path.write_text(source, encoding="utf-8")
    return path


def test_discovery_loads_simple_filter_and_preserves_transform_contract(tmp_path):
    write_plugin(
        tmp_path,
        "add_offset.py",
        '''
PLUGIN = {
    "id": "add_offset",
    "tipo": "filter",
    "nombre": "Sumar offset",
    "descripcion": "Suma un valor a OPD",
    "parametros": [{"id": "offset", "tipo": "float", "default": 0.5}],
}

def aplicar(data, parametros):
    return data.depth_mm + parametros["offset"]
''',
    )

    registry = discover_plugins(tmp_path)
    transform = registry.create("add_offset", {"offset": 0.5})
    original = make_data()
    result = transform.apply(original)

    assert registry.ids("filter") == ["add_offset"]
    assert np.array_equal(result.X, original.X)
    assert np.array_equal(result.mask, original.mask)
    assert np.array_equal(result.depth_mm, np.array([[[1.5]], [[2.5]]]))
    assert np.array_equal(original.depth_mm, np.array([[[1.0]], [[2.0]]]))


def test_discovery_loads_geometry_that_returns_transform_data(tmp_path):
    write_plugin(
        tmp_path,
        "shift_x.py",
        '''
PLUGIN = {
    "id": "shift_x",
    "tipo": "geometry",
    "nombre": "Desplazar X",
    "descripcion": "Desplaza las coordenadas X",
}

def aplicar(data, parametros):
    result = data.copy()
    result.X = result.X + 2.0
    return result
''',
    )

    transform = discover_plugins(tmp_path).create("shift_x")
    result = transform.apply(make_data())

    assert np.array_equal(result.X, np.array([2.0, 3.0]))
    assert np.array_equal(result.depth_mm, np.array([[[1.0]], [[2.0]]]))


def test_invalid_plugin_is_reported_without_breaking_other_plugins(tmp_path):
    write_plugin(
        tmp_path,
        "valid.py",
        '''
PLUGIN = {"id": "valid", "tipo": "filter", "nombre": "Válido"}
def aplicar(data, parametros):
    return data.depth_mm.copy()
''',
    )
    write_plugin(
        tmp_path,
        "broken.py",
        '''
PLUGIN = {"id": "broken", "tipo": "filter", "nombre": "Roto"}
# Falta aplicar a propósito
''',
    )

    registry = discover_plugins(tmp_path)

    assert registry.ids("filter") == ["valid"]
    assert len(registry.errors) == 1
    assert "aplicar" in registry.errors[0].message


def test_plugin_parameters_are_validated_before_creation(tmp_path):
    write_plugin(
        tmp_path,
        "limited.py",
        '''
PLUGIN = {
    "id": "limited",
    "tipo": "filter",
    "nombre": "Limitado",
    "parametros": [{"id": "amount", "tipo": "float", "default": 1.0, "min": 0.0, "max": 2.0}],
}
def aplicar(data, parametros):
    return data.depth_mm * parametros["amount"]
''',
    )
    registry = discover_plugins(tmp_path)

    with pytest.raises(PluginValidationError, match="amount"):
        registry.create("limited", {"amount": 3.0})


def test_private_files_are_templates_not_plugins(tmp_path):
    write_plugin(
        tmp_path,
        "_plantilla_filtro.py",
        '''
PLUGIN = {"id": "template", "tipo": "filter", "nombre": "Plantilla"}
def aplicar(data, parametros):
    return data.depth_mm
''',
    )

    assert discover_plugins(tmp_path).ids() == []


def test_plugin_system_exit_is_reported_without_terminating_discovery(tmp_path):
    write_plugin(tmp_path, "exits.py", "raise SystemExit('plugin abortó')")

    registry = discover_plugins(tmp_path)

    assert len(registry.errors) == 1
    assert "plugin abortó" in registry.errors[0].message
