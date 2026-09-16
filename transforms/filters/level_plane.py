"""Nivelado por plano implementado como plugin integrado."""

import numpy as np



PLUGIN = {
    "id": "level_plane",
    "tipo": "filter",
    "nombre": "Nivelar plano",
    "descripcion": "Calcular plano ajustado menos OPD mediante mínimos cuadrados",
    "version": "1.0",
    "integrado": True,
    "parametros": [
        {"id": "win_id", "nombre": "Ventana", "tipo": "int", "default": 0, "min": 0},
        {"id": "measurement", "nombre": "Medición", "tipo": "int", "default": 0, "min": 0},
    ],
}


def aplicar(superficie, parametros):
    """Ajustar y restar un plano a la ventana/medición seleccionada."""
    z = superficie.z
    win_id = int(parametros["win_id"])
    measurement = int(parametros["measurement"])
    if not 0 <= measurement < z.shape[1]:
        raise IndexError(f"Medición fuera de rango: {measurement}")
    if not 0 <= win_id < z.shape[2]:
        raise IndexError(f"Ventana fuera de rango: {win_id}")

    selected = z[:, measurement, win_id]
    valid = (
        np.isfinite(selected)
        & np.isfinite(superficie.x)
        & np.isfinite(superficie.y)
    )
    if np.count_nonzero(valid) < 3:
        return superficie.con_z(z)

    design = np.column_stack([
        superficie.x[valid],
        superficie.y[valid],
        np.ones(np.count_nonzero(valid)),
    ])
    coefficients, _, _, _ = np.linalg.lstsq(
        design,
        selected[valid],
        rcond=None,
    )
    a, b, c = coefficients
    plane = a * superficie.x + b * superficie.y + c
    corrected = z.copy()
    corrected[:, measurement, win_id] = plane - corrected[:, measurement, win_id]
    return superficie.con_z(corrected)
