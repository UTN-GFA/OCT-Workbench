"""Centrado de origen implementado como plugin integrado."""

import numpy as np



PLUGIN = {
    "id": "center_origin",
    "tipo": "geometry",
    "nombre": "Centrar origen",
    "descripcion": "Mover el origen XY al centro físico",
    "version": "1.0",
    "integrado": True,
}


def aplicar(superficie, parametros):
    result = superficie
    for axis in ("x", "y"):
        values = getattr(result, axis)
        finite = values[np.isfinite(values)]
        if finite.size:
            center = (float(finite.min()) + float(finite.max())) / 2.0
            result = result.con_x(values - center) if axis == "x" else result.con_y(values - center)
    return result
