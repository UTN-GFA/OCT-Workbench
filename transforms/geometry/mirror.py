"""Espejado X/Y implementado como plugin integrado."""

import numpy as np

PLUGIN = {
    "id": "mirror",
    "tipo": "geometry",
    "nombre": "Espejar eje",
    "nombre_parametrico": "Espejar {axis}",
    "descripcion": "Espejar datos respecto al centro físico del eje",
    "version": "1.0",
    "integrado": True,
    "cancellation_group": "mirror",
    "parametros": [{"id": "axis", "nombre": "Eje", "tipo": "choice", "opciones": ["X", "Y"], "default": "X"}],
}


def aplicar(superficie, parametros):
    axis = str(parametros["axis"]).upper()
    if axis not in {"X", "Y"}:
        raise ValueError(f"Eje inválido: {axis!r}. Usar X o Y")
    values = superficie.x if axis == "X" else superficie.y
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return superficie.copy()
    mirrored = finite.min() + finite.max() - values
    return superficie.con_x(mirrored) if axis == "X" else superficie.con_y(mirrored)
