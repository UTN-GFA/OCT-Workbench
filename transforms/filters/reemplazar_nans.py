"""Filtro para reemplazar valores NaN por la mediana."""

import numpy as np


PLUGIN = {
    "id": "rellenar_nan_mediana",
    "tipo": "filter",
    "nombre": "Rellenar NaN con mediana",
    "descripcion": "Reemplaza únicamente los valores NaN por la mediana de los valores válidos.",
    "version": "1.0",
    "parametros": [],
}


def aplicar(superficie, parametros):
    """Recibe una fachada segura y devuelve otra superficie."""
    z = superficie.z.copy()

    # ================================================================
    # EDITAR SOLAMENTE ESTE BLOQUE
    # Trabajar sobre z y parámetros. No tocar callbacks, metadata ni GUI.
    # ================================================================

    nuevo_z = z.copy()

    mascara_nan = np.isnan(nuevo_z)

    if np.any(mascara_nan):
        mediana = np.nanmedian(nuevo_z)

        if np.isfinite(mediana):
            nuevo_z[mascara_nan] = mediana

    # ================================================================
    # FIN DEL BLOQUE EDITABLE
    # ================================================================

    return superficie.con_z(nuevo_z)