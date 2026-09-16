"""Mediana 2D implementada como plugin integrado."""

import numpy as np
from scipy.ndimage import median_filter



PLUGIN = {
    "id": "filter_median",
    "tipo": "filter",
    "nombre": "Mediana 2D",
    "nombre_parametrico": "Mediana {kernel_size}×{kernel_size}",
    "descripcion": "Filtro de mediana sobre la topografía",
    "version": "1.0",
    "integrado": True,
    "parametros": [
        {"id": "kernel_size", "nombre": "Matriz cuadrada", "tipo": "int", "default": 3, "min": 1, "max": 99},
        {"id": "win_id", "nombre": "Ventana", "tipo": "int", "default": 0, "min": 0},
    ],
}


def _canonical_unique(values, tolerance):
    finite = np.sort(np.asarray(values, dtype=float).ravel())
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return np.array([], dtype=float)
    groups = [finite[0]]
    for value in finite[1:]:
        if abs(value - groups[-1]) > tolerance:
            groups.append(value)
    return np.asarray(groups, dtype=float)


def _grid_indices(superficie):
    tolerance = max(float(superficie.coordinate_tolerance_mm), 1e-9)
    x_sorted = _canonical_unique(superficie.x, tolerance)
    y_sorted = _canonical_unique(superficie.y, tolerance)
    index_map = np.full((len(y_sorted), len(x_sorted)), -1, dtype=int)
    for index, (x_value, y_value) in enumerate(zip(superficie.x, superficie.y)):
        if not np.isfinite(x_value) or not np.isfinite(y_value):
            continue
        x_index = int(np.argmin(np.abs(x_sorted - x_value)))
        y_index = int(np.argmin(np.abs(y_sorted - y_value)))
        if abs(x_sorted[x_index] - x_value) <= tolerance and abs(y_sorted[y_index] - y_value) <= tolerance:
            index_map[y_index, x_index] = index
    return x_sorted, y_sorted, index_map


def aplicar(superficie, parametros):
    z = superficie.z
    win_id = int(parametros["win_id"])
    kernel = int(parametros["kernel_size"])
    if kernel % 2 == 0:
        kernel += 1
    if not 0 <= win_id < z.shape[2]:
        raise IndexError(f"Ventana fuera de rango: {win_id}")

    x_sorted, y_sorted, index_map = _grid_indices(superficie)
    if len(x_sorted) < 3 or len(y_sorted) < 3:
        return superficie.con_z(z)

    corrected = z.copy()
    for measurement in range(z.shape[1]):
        grid = np.full((len(y_sorted), len(x_sorted)), np.nan)
        for y_index in range(len(y_sorted)):
            for x_index in range(len(x_sorted)):
                point_index = index_map[y_index, x_index]
                if point_index >= 0:
                    grid[y_index, x_index] = z[point_index, measurement, win_id]
        nan_mask = np.isnan(grid)
        if np.all(nan_mask):
            continue
        filled = np.where(nan_mask, np.nanmedian(grid), grid)
        filtered = median_filter(filled, size=kernel)
        filtered[nan_mask] = np.nan
        for y_index in range(len(y_sorted)):
            for x_index in range(len(x_sorted)):
                point_index = index_map[y_index, x_index]
                if point_index >= 0:
                    corrected[point_index, measurement, win_id] = filtered[y_index, x_index]
    return superficie.con_z(corrected)
