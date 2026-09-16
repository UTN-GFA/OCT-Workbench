"""Plugin local demostrativo: rotación física XY sin remuestreo."""

PLUGIN = {
    "id": "rotar_90",
    "tipo": "geometry",
    "nombre": "Rotar 90°",
    "descripcion": "Rotar X/Y alrededor del centro físico sin interpolar valores",
    "version": "1.0",
    "parametros": [
        {
            "id": "sentido",
            "nombre": "Sentido",
            "tipo": "choice",
            "opciones": ["1", "-1"],
            "default": "1",
        },
    ],
}


def aplicar(superficie, parametros):
    return superficie.rotar_90(int(parametros["sentido"]))
