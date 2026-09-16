"""Plantilla para un filtro OPD sencillo.

USO:
1. Copiar este archivo con otro nombre que termine en ``.py``.
2. Completar ``PLUGIN``.
3. Modificar solamente el bloque marcado dentro de ``aplicar``.

El Workbench descubre el archivo automáticamente. No hace falta importar
clases internas ni registrar botones.
"""

PLUGIN = {
    "id": "reemplazar_por_id",
    "tipo": "filter",
    "nombre": "Reemplazar por nombre visible",
    "descripcion": "Explicación breve para el laboratorio",
    "version": "1.0",
    "parametros": [
        {
            "id": "intensidad",
            "nombre": "Intensidad",
            "tipo": "float",
            "unidad": "",
            "default": 1.0,
            "min": 0.0,
            "max": 100.0,
        },
    ],
}


def aplicar(superficie, parametros):
    """Recibe una fachada segura y devuelve otra superficie."""
    z = superficie.z.copy()

    # ================================================================
    # EDITAR SOLAMENTE ESTE BLOQUE
    # Trabajar sobre z y parámetros. No tocar callbacks, metadata ni GUI.
    # ================================================================
    intensidad = parametros["intensidad"]
    nuevo_z = z * intensidad
    # ================================================================
    # FIN DEL BLOQUE EDITABLE
    # ================================================================

    return superficie.con_z(nuevo_z)
