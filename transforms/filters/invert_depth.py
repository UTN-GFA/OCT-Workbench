"""Inversión de OPD implementada como plugin integrado."""



PLUGIN = {
    "id": "invert_depth",
    "tipo": "filter",
    "nombre": "Invertir OPD",
    "descripcion": "Invertir el signo del canal OPD",
    "version": "1.0",
    "integrado": True,
}


def aplicar(superficie, parametros):
    if superficie.depth_mm is None:
        return superficie.copy()
    return superficie.con_z(-superficie.z)
