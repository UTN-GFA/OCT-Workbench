"""Máscara de OPD implementada como plugin integrado."""

import numpy as np



PLUGIN = {
    "id": "mask_depth_range",
    "tipo": "filter",
    "nombre": "Máscara OPD",
    "descripcion": "Enmascarar OPD y amplitud fuera de rango",
    "version": "1.0",
    "integrado": True,
    "modifica_amplitud": True,
    "parametros": [
        {"id": "minimum_mm", "nombre": "Mínimo", "tipo": "float", "default": 0.0},
        {"id": "maximum_mm", "nombre": "Máximo", "tipo": "float", "default": 1.0},
        {"id": "inclusive", "nombre": "Límites inclusivos", "tipo": "bool", "default": True},
    ],
}


def aplicar(superficie, parametros):
    minimum_mm = float(parametros["minimum_mm"])
    maximum_mm = float(parametros["maximum_mm"])
    if not np.isfinite(minimum_mm) or not np.isfinite(maximum_mm):
        raise ValueError("Los límites de OPD deben ser finitos")
    if minimum_mm >= maximum_mm:
        raise ValueError("El mínimo de OPD debe ser menor que el máximo")

    z = superficie.z
    invalid = (
        ~np.isfinite(z)
        | (z < minimum_mm)
        | (z > maximum_mm)
    )
    masked_z = z.copy()
    masked_z[invalid] = np.nan
    if superficie.amplitude is None:
        return superficie.con_z(masked_z)
    masked_amplitude = superficie.amplitude
    masked_amplitude[invalid] = np.nan
    return superficie.con_z_y_amplitud(masked_z, masked_amplitude)
