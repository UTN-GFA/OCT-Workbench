"""Inversión de ejes implementada como plugin integrado."""

PLUGIN = {
    "id": "invert_axis",
    "tipo": "geometry",
    "nombre": "Invertir eje",
    "nombre_parametrico": "Invertir {axis}",
    "descripcion": "Invertir un eje físico o el signo OPD",
    "version": "1.0",
    "integrado": True,
    "cancellation_group": "invert_axis",
    "parametros": [{"id": "axis", "nombre": "Eje", "tipo": "choice", "opciones": ["X", "Y", "Z", "DEPTH"], "default": "X"}],
}


def aplicar(superficie, parametros):
    axis = str(parametros["axis"]).upper()
    if axis == "DEPTH":
        if superficie.depth_mm is None:
            return superficie.copy()
        return superficie.con_z(-superficie.z)
    if axis == "X":
        return superficie.con_x(-superficie.x)
    if axis == "Y":
        return superficie.con_y(-superficie.y)
    if axis == "Z":
        return superficie.con_coordenada_z(-superficie.coordenada_z)
    raise ValueError(f"Eje inválido: {axis!r}. Usar X, Y, Z u OPD")
