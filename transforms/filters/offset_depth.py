"""Offset OPD implementado como plugin integrado."""

PLUGIN = {
    "id": "offset_depth",
    "tipo": "filter",
    "nombre": "Offset OPD",
    "descripcion": "Desplazar OPD sin cambiar la grilla",
    "version": "1.0",
    "integrado": True,
    "parametros": [{"id": "offset_mm", "nombre": "Offset", "tipo": "float", "default": 0.0}],
}


def aplicar(superficie, parametros):
    if superficie.depth_mm is None:
        return superficie.copy()
    return superficie.con_z(superficie.z + float(parametros["offset_mm"]))
