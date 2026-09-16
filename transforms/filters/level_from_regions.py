"""Nivelado por regiones implementado como plugin integrado."""

import json

import numpy as np



PLUGIN = {
    "id": "level_from_regions",
    "tipo": "filter",
    "nombre": "Nivelar regiones",
    "nombre_parametrico": "Nivelar regiones ({n_regions})",
    "descripcion": "Ajustar un plano usando regiones de referencia",
    "version": "1.0",
    "integrado": True,
    "parametros": [
        {"id": "regions_json", "nombre": "Regiones JSON", "tipo": "str", "default": "[]"},
        {"id": "win_id", "nombre": "Ventana", "tipo": "int", "default": 0, "min": 0},
        {"id": "measurement", "nombre": "Medición", "tipo": "int", "default": 0, "min": 0},
        {"id": "level_z_mm", "nombre": "Nivel Z", "tipo": "float", "default": 0.0},
        {"id": "level_tolerance_mm", "nombre": "Tolerancia Z", "tipo": "float", "default": 0.002, "min": 0.0},
        {"id": "n_regions", "nombre": "Regiones", "tipo": "int", "default": 1, "min": 1},
    ],
}


def aplicar(superficie, parametros):
    """Ajustar con regiones de referencia y restar el plano resultante."""
    z = superficie.z
    win_id = int(parametros["win_id"])
    measurement = int(parametros["measurement"])
    if not 0 <= measurement < z.shape[1]:
        raise IndexError(f"Medición fuera de rango: {measurement}")
    if not 0 <= win_id < z.shape[2]:
        raise IndexError(f"Ventana fuera de rango: {win_id}")

    level_z_mm = parametros["level_z_mm"]
    level_tolerance_mm = float(parametros["level_tolerance_mm"])
    level_mask = np.ones(len(superficie.x), dtype=bool)
    if level_z_mm is not None:
        level_mask = np.isfinite(superficie.coordenada_z) & (
            np.abs(superficie.coordenada_z - float(level_z_mm)) <= level_tolerance_mm
        )

    reference_mask = np.zeros(len(superficie.x), dtype=bool)
    for region in json.loads(parametros["regions_json"]):
        x0, x1, y0, y1 = sorted((float(region[0]), float(region[1]))) + sorted((float(region[2]), float(region[3])))
        reference_mask |= (
            (superficie.x >= x0)
            & (superficie.x <= x1)
            & (superficie.y >= y0)
            & (superficie.y <= y1)
        )

    selected = z[:, measurement, win_id]
    valid = reference_mask & level_mask & np.isfinite(selected)
    valid &= np.isfinite(superficie.x) & np.isfinite(superficie.y)
    if np.count_nonzero(valid) < 3:
        raise ValueError("Las regiones deben contener tres puntos no colineales")

    design = np.column_stack([
        superficie.x[valid],
        superficie.y[valid],
        np.ones(np.count_nonzero(valid)),
    ])
    if np.linalg.matrix_rank(design) < 3:
        raise ValueError("Las regiones deben contener tres puntos no colineales")
    coefficients, _, _, _ = np.linalg.lstsq(design, selected[valid], rcond=None)
    a, b, c = coefficients
    plane = a * superficie.x + b * superficie.y + c

    corrected = z.copy()
    if level_z_mm is None:
        corrected[:, :, win_id] -= plane[:, None]
    else:
        corrected[level_mask, measurement, win_id] -= plane[level_mask]
    return superficie.con_z(corrected)
