"""Offset automático implementado como plugin integrado."""

import numpy as np

PLUGIN = {
    "id": "offset_minimum_to_zero",
    "tipo": "filter",
    "nombre": "Offset OPD automático",
    "descripcion": "Llevar el mínimo OPD finito a cero",
    "version": "1.0",
    "integrado": True,
}


def aplicar(superficie, parametros):
    if superficie.depth_mm is None:
        return superficie.copy()
    finite = superficie.z[np.isfinite(superficie.z)]
    if finite.size == 0:
        return superficie.copy()
    return superficie.con_z(superficie.z - float(np.min(finite)))
