"""Recorte XY implementado como plugin integrado."""

import numpy as np


PLUGIN = {
    "id": "crop_region",
    "tipo": "filter",
    "nombre": "Recortar región",
    "descripcion": "Conservar una región rectangular en X/Y",
    "version": "1.0",
    "integrado": True,
    "cambia_numero_puntos": True,
    "parametros": [
        {"id": "x_min", "nombre": "X mínimo", "tipo": "str", "default": ""},
        {"id": "x_max", "nombre": "X máximo", "tipo": "str", "default": ""},
        {"id": "y_min", "nombre": "Y mínimo", "tipo": "str", "default": ""},
        {"id": "y_max", "nombre": "Y máximo", "tipo": "str", "default": ""},
    ],
}


def _optional_float(value, name):
    value = str(value).strip()
    if not value:
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser numérico o quedar vacío") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} debe ser finito")
    return result


def aplicar(superficie, parametros):
    x_min = _optional_float(parametros.get("x_min", ""), "X mínimo")
    x_max = _optional_float(parametros.get("x_max", ""), "X máximo")
    y_min = _optional_float(parametros.get("y_min", ""), "Y mínimo")
    y_max = _optional_float(parametros.get("y_max", ""), "Y máximo")
    if x_min is not None and x_max is not None and x_min > x_max:
        x_min, x_max = x_max, x_min
    if y_min is not None and y_max is not None and y_min > y_max:
        y_min, y_max = y_max, y_min

    mask = np.ones(len(superficie.x), dtype=bool)
    if x_min is not None:
        mask &= superficie.x >= x_min
    if x_max is not None:
        mask &= superficie.x <= x_max
    if y_min is not None:
        mask &= superficie.y >= y_min
    if y_max is not None:
        mask &= superficie.y <= y_max
    return superficie.conservar_puntos(mask)
