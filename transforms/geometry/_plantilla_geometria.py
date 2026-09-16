"""Plantilla para una transformación geométrica.

USO:
1. Copiar este archivo con otro nombre que termine en ``.py``.
2. Completar ``PLUGIN``.
3. Modificar solamente el bloque marcado dentro de ``aplicar``.

La fachada conserva mallas, NaN, máscara, metadata y unidades. No hace falta
manipular ``TransformData`` ni registrar la operación manualmente.
"""

PLUGIN = {
    "id": "reemplazar_por_id",
    "tipo": "geometry",
    "nombre": "Reemplazar por nombre visible",
    "descripcion": "Explicación breve para el laboratorio",
    "version": "1.0",
    "parametros": [],
}


def aplicar(superficie, parametros):
    """Recibe una fachada segura y devuelve otra superficie."""

    # ================================================================
    # EDITAR SOLAMENTE ESTE BLOQUE
    # Helpers disponibles: espejar, reordenar_eje y rotar_90.
    # ================================================================
    resultado = superficie.espejar("X")
    # ================================================================
    # FIN DEL BLOQUE EDITABLE
    # ================================================================

    return resultado
