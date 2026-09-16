"""Offset geométrico implementado como plugin integrado."""

PLUGIN = {
    "id": "offset_geometry",
    "tipo": "geometry",
    "nombre": "Offset geométrico",
    "nombre_parametrico": "Offset {axis} {value_mm}",
    "descripcion": "Desplazar una coordenada física sin remuestrear",
    "version": "1.0",
    "integrado": True,
    "parametros": [
        {"id": "axis", "nombre": "Eje", "tipo": "choice", "opciones": ["X", "Y", "Z"], "default": "X"},
        {"id": "value_mm", "nombre": "Offset", "tipo": "float", "default": 0.0},
    ],
}


def aplicar(superficie, parametros):
    axis = str(parametros["axis"]).upper()
    value = float(parametros["value_mm"])
    if axis == "X":
        return superficie.con_x(superficie.x + value)
    if axis == "Y":
        return superficie.con_y(superficie.y + value)
    if axis == "Z":
        return superficie.con_coordenada_z(superficie.coordenada_z + value)
    raise ValueError(f"Eje inválido: {axis!r}. Usar X, Y o Z")
