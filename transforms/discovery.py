"""Descubrimiento de plugins de laboratorio desde una carpeta."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

from transforms.plugin_api import PluginError, PluginRegistry, PluginSpec


def discover_plugins(directory: str | Path) -> PluginRegistry:
    """Cargar plugins ``.py`` válidos sin detener la aplicación por uno roto."""
    registry = PluginRegistry()
    directory = Path(directory)
    if not directory.exists():
        return registry

    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = "oct_workbench_plugin_" + hashlib.sha1(
            str(path.resolve()).encode("utf-8")
        ).hexdigest()
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError("no se pudo crear el cargador del módulo")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            plugin = PluginSpec.from_module(module, source=str(path))
            registry.register(plugin)
        except (Exception, SystemExit) as exc:  # un plugin no debe impedir abrir el Workbench
            registry.add_error(str(path), str(exc))
    return registry


def discover_plugin_tree(root: str | Path) -> PluginRegistry:
    """Descubrir filtros y geometrías debajo de ``root``."""
    root = Path(root)
    registry = PluginRegistry()
    for kind in ("filters", "geometry"):
        child = discover_plugins(root / kind)
        for plugin in child.list(include_integrated=True):
            try:
                registry.register(plugin)
            except Exception as exc:
                registry.add_error(plugin.source, str(exc))
        registry.errors.extend(child.errors)
    return registry
