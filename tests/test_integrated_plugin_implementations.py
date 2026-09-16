import ast
from pathlib import Path

import numpy as np

from transforms.base import TransformData
from transforms.discovery import discover_plugin_tree


ROOT = Path(__file__).resolve().parents[1]
INTEGRATED_PLUGIN_DIRS = (
    ROOT / "transforms" / "filters",
    ROOT / "transforms" / "geometry",
)


def test_integrated_plugins_contain_their_own_operation():
    delegated_modules = {
        "transforms.surface",
        "transforms.depth",
        "transforms.geometric",
    }
    violations = []
    for directory in INTEGRATED_PLUGIN_DIRS:
        for path in sorted(directory.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            integrated = any(
                isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "PLUGIN" for target in node.targets)
                and isinstance(node.value, ast.Dict)
                and any(
                    isinstance(key, ast.Constant)
                    and key.value == "integrado"
                    and isinstance(value, ast.Constant)
                    and value.value is True
                    for key, value in zip(node.value.keys, node.value.values)
                )
                for node in tree.body
            )
            if not integrated:
                continue
            for node in tree.body:
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module in delegated_modules:
                        violations.append(f"{path.name}: from {module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in delegated_modules:
                            violations.append(f"{path.name}: import {alias.name}")
    assert violations == []


def test_integrated_plugins_do_not_delegate_math_to_surface_helpers():
    delegated_helpers = ("desplazar(", "espejar(", "reordenar_eje(", "centrar_origen(")
    violations = []
    for directory in INTEGRATED_PLUGIN_DIRS:
        for path in sorted(directory.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if '"integrado": True' not in text:
                continue
            for helper in delegated_helpers:
                if helper in text:
                    violations.append(f"{path.name}: {helper}")
    assert violations == []


def test_level_plane_plugin_applies_plane_minus_measurement_without_mutating_input():
    x = np.array([0.0, 1.0, 0.0, 1.0, 2.0])
    y = np.array([0.0, 0.0, 1.0, 1.0, 2.0])
    plane = 2.0 * x + 3.0 * y + 5.0
    residual = np.array([0.2, -0.4, 0.7, -0.1, 0.5])
    depth_mm = (plane + residual)[:, None, None]
    data = TransformData(X=x, Y=y, Z=np.zeros(5), depth_mm=depth_mm)
    registry = discover_plugin_tree(ROOT / "transforms")
    design = np.column_stack([x, y, np.ones(x.size)])
    coefficients, _, _, _ = np.linalg.lstsq(design, depth_mm[:, 0, 0], rcond=None)
    expected = design @ coefficients - depth_mm[:, 0, 0]

    result = registry.create("level_plane", {"win_id": 0, "measurement": 0}).apply(data)

    assert np.allclose(result.depth_mm[:, 0, 0], expected)
    assert not np.allclose(result.depth_mm[:, 0, 0], -expected)
    assert np.array_equal(data.depth_mm[:, 0, 0], depth_mm[:, 0, 0])
