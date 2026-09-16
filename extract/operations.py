"""
extract.operations
Operaciones de extracción de datos.

Cada función toma un TransformedView (o OCTDataset) y retorna
un DerivedObject autocontenido con proveniencia.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from extract.derived import (
    DerivedObject, ExtractionType, Provenance,
)
from model.dataset import _canonical_unique


def extract_profile_x(
    view,
    y_value: Optional[float] = None,
    win_id: Optional[int] = None,
    measurement: Optional[int] = None,
    name: Optional[str] = None,
    requested_y_mm: Optional[float] = None,
    window_index: Optional[int] = None,
    measurement_index: Optional[int] = None,
) -> DerivedObject:
    """
    Extraer un perfil en X a Y fijo.

    Busca la fila de Y más cercana al valor dado y extrae
    todos los puntos de esa fila.

    Parameters
    ----------
    view : TransformedView o OCTDataset
        Fuente de datos (ya transformados si viene de un view).
    y_value : float
        Posición Y del corte [mm].
    win_id : int
        Ventana de OPD.
    measurement : int
        Índice de medición.
    name : str, opcional
        Nombre del objeto derivado.

    Returns
    -------
    DerivedObject con el perfil extraído.
    """
    if requested_y_mm is not None:
        if y_value is not None and not np.isclose(y_value, requested_y_mm):
            raise ValueError("y_value y requested_y_mm no pueden diferir")
        y_value = requested_y_mm
    if y_value is None:
        raise TypeError("extract_profile_x requiere y_value o requested_y_mm")
    win_id = _resolve_index_alias(win_id, window_index, "win_id", "window_index")
    measurement = _resolve_index_alias(
        measurement, measurement_index, "measurement", "measurement_index"
    )

    td, dataset = _get_data_and_dataset(view)
    td = td.apply_mask()

    # Encontrar el Y más cercano
    tolerance_y = _coordinate_tolerance(td, dataset, "Y")
    y_unique = _canonical_unique(td.Y, tolerance=tolerance_y)
    y_actual = y_unique[np.argmin(np.abs(y_unique - y_value))]
    mask = np.isclose(td.Y, y_actual, atol=tolerance_y, rtol=0.0)

    X_prof = td.X[mask]
    Y_prof = td.Y[mask]
    Z_prof = td.Z[mask]

    depth_mm_prof = _select_channel(td.depth_mm, mask, measurement, win_id)
    amplitude_prof = _select_channel(td.amplitude, mask, measurement, win_id)

    # Ordenar por X
    sort_idx = np.argsort(X_prof)
    X_prof = X_prof[sort_idx]
    Y_prof = Y_prof[sort_idx]
    Z_prof = Z_prof[sort_idx]
    if depth_mm_prof is not None:
        depth_mm_prof = depth_mm_prof[sort_idx]
    if amplitude_prof is not None:
        amplitude_prof = amplitude_prof[sort_idx]

    provenance = _build_provenance(
        dataset, view,
        ExtractionType.PROFILE_X,
        {"y_value": y_value, "y_actual": float(y_actual),
         "win_id": win_id, "measurement": measurement},
    )

    if name is None:
        name = f"Perfil X @ Y={y_actual:.4f}mm"

    return DerivedObject(
        name=name,
        X=X_prof, Y=Y_prof, Z=Z_prof,
        depth_mm=depth_mm_prof, amplitude=amplitude_prof,
        provenance=provenance,
        metadata=_inherited_metadata(dataset),
    )


def extract_profile_y(
    view,
    x_value: Optional[float] = None,
    win_id: Optional[int] = None,
    measurement: Optional[int] = None,
    name: Optional[str] = None,
    requested_x_mm: Optional[float] = None,
    window_index: Optional[int] = None,
    measurement_index: Optional[int] = None,
) -> DerivedObject:
    """
    Extraer un perfil en Y a X fijo.

    Busca la columna de X más cercana al valor dado y extrae
    todos los puntos de esa columna.
    """
    if requested_x_mm is not None:
        if x_value is not None and not np.isclose(x_value, requested_x_mm):
            raise ValueError("x_value y requested_x_mm no pueden diferir")
        x_value = requested_x_mm
    if x_value is None:
        raise TypeError("extract_profile_y requiere x_value o requested_x_mm")
    win_id = _resolve_index_alias(win_id, window_index, "win_id", "window_index")
    measurement = _resolve_index_alias(
        measurement, measurement_index, "measurement", "measurement_index"
    )

    td, dataset = _get_data_and_dataset(view)
    td = td.apply_mask()

    tolerance_x = _coordinate_tolerance(td, dataset, "X")
    x_unique = _canonical_unique(td.X, tolerance=tolerance_x)
    x_actual = x_unique[np.argmin(np.abs(x_unique - x_value))]
    mask = np.isclose(td.X, x_actual, atol=tolerance_x, rtol=0.0)

    X_prof = td.X[mask]
    Y_prof = td.Y[mask]
    Z_prof = td.Z[mask]

    depth_mm_prof = _select_channel(td.depth_mm, mask, measurement, win_id)
    amplitude_prof = _select_channel(td.amplitude, mask, measurement, win_id)

    sort_idx = np.argsort(Y_prof)
    X_prof = X_prof[sort_idx]
    Y_prof = Y_prof[sort_idx]
    Z_prof = Z_prof[sort_idx]
    if depth_mm_prof is not None:
        depth_mm_prof = depth_mm_prof[sort_idx]
    if amplitude_prof is not None:
        amplitude_prof = amplitude_prof[sort_idx]

    provenance = _build_provenance(
        dataset, view,
        ExtractionType.PROFILE_Y,
        {"x_value": x_value, "x_actual": float(x_actual),
         "win_id": win_id, "measurement": measurement},
    )

    if name is None:
        name = f"Perfil Y @ X={x_actual:.4f}mm"

    return DerivedObject(
        name=name,
        X=X_prof, Y=Y_prof, Z=Z_prof,
        depth_mm=depth_mm_prof, amplitude=amplitude_prof,
        provenance=provenance,
        metadata=_inherited_metadata(dataset),
    )


def extract_region(
    view,
    x_min: Optional[float] = None,
    x_max: Optional[float] = None,
    y_min: Optional[float] = None,
    y_max: Optional[float] = None,
    name: Optional[str] = None,
    requested_x_min_mm: Optional[float] = None,
    requested_x_max_mm: Optional[float] = None,
    requested_y_min_mm: Optional[float] = None,
    requested_y_max_mm: Optional[float] = None,
) -> DerivedObject:
    """
    Extraer una sub-región rectangular.

    Los límites no especificados se toman del rango completo.
    """
    aliases = (
        ("x_min", x_min, requested_x_min_mm),
        ("x_max", x_max, requested_x_max_mm),
        ("y_min", y_min, requested_y_min_mm),
        ("y_max", y_max, requested_y_max_mm),
    )
    resolved = {}
    for label, legacy, canonical in aliases:
        if canonical is not None and legacy is not None and not np.isclose(legacy, canonical):
            raise ValueError(f"{label} y su alias requested_{label}_mm no pueden diferir")
        resolved[label] = canonical if canonical is not None else legacy
    x_min, x_max = resolved["x_min"], resolved["x_max"]
    y_min, y_max = resolved["y_min"], resolved["y_max"]

    td, dataset = _get_data_and_dataset(view)
    td = td.apply_mask()

    mask = np.ones(td.n_points, dtype=bool)

    x_min_actual = float(td.X.min()) if x_min is None else x_min
    x_max_actual = float(td.X.max()) if x_max is None else x_max
    y_min_actual = float(td.Y.min()) if y_min is None else y_min
    y_max_actual = float(td.Y.max()) if y_max is None else y_max

    mask &= td.X >= x_min_actual
    mask &= td.X <= x_max_actual
    mask &= td.Y >= y_min_actual
    mask &= td.Y <= y_max_actual

    X_reg = td.X[mask]
    Y_reg = td.Y[mask]
    Z_reg = td.Z[mask]
    depth_mm_reg = td.depth_mm[mask] if td.depth_mm is not None else None
    amp_reg = td.amplitude[mask] if td.amplitude is not None else None

    provenance = _build_provenance(
        dataset, view,
        ExtractionType.REGION,
        {"x_min": x_min_actual, "x_max": x_max_actual,
         "y_min": y_min_actual, "y_max": y_max_actual},
    )

    if name is None:
        name = (
            f"Región [{x_min_actual:.3f}:{x_max_actual:.3f}] × "
            f"[{y_min_actual:.3f}:{y_max_actual:.3f}]"
        )

    return DerivedObject(
        name=name,
        X=X_reg, Y=Y_reg, Z=Z_reg,
        depth_mm=depth_mm_reg, amplitude=amp_reg,
        provenance=provenance,
        metadata=_inherited_metadata(dataset),
    )


def extract_z_slice(
    view,
    z_value: Optional[float] = None,
    name: Optional[str] = None,
    requested_z_mm: Optional[float] = None,
) -> DerivedObject:
    """
    Extraer un nivel Z de un dataset Multi-Z.

    Busca el Z más cercano al valor dado y extrae todos los
    puntos de ese nivel.
    """
    if requested_z_mm is not None:
        if z_value is not None and not np.isclose(z_value, requested_z_mm):
            raise ValueError("z_value y requested_z_mm no pueden diferir")
        z_value = requested_z_mm
    if z_value is None:
        raise TypeError("extract_z_slice requiere z_value o requested_z_mm")

    td, dataset = _get_data_and_dataset(view)
    td = td.apply_mask()

    tolerance_z = _coordinate_tolerance(td, dataset, "Z")
    z_unique = _canonical_unique(td.Z, tolerance=tolerance_z)
    if len(z_unique) <= 1:
        raise ValueError("El dataset no es Multi-Z (solo tiene 1 nivel Z)")

    z_actual = z_unique[np.argmin(np.abs(z_unique - z_value))]
    mask = np.isclose(td.Z, z_actual, atol=tolerance_z, rtol=0.0)

    X_sl = td.X[mask]
    Y_sl = td.Y[mask]
    Z_sl = td.Z[mask]
    depth_mm_sl = td.depth_mm[mask] if td.depth_mm is not None else None
    amp_sl = td.amplitude[mask] if td.amplitude is not None else None

    provenance = _build_provenance(
        dataset, view,
        ExtractionType.Z_SLICE,
        {"z_value": z_value, "z_actual": float(z_actual)},
    )

    if name is None:
        name = f"Z-slice @ Z={z_actual:.4f}mm"

    return DerivedObject(
        name=name,
        X=X_sl, Y=Y_sl, Z=Z_sl,
        depth_mm=depth_mm_sl, amplitude=amp_sl,
        provenance=provenance,
        metadata=_inherited_metadata(dataset),
    )


def extract_window(
    view,
    win_id: Optional[int] = None,
    name: Optional[str] = None,
    window_index: Optional[int] = None,
) -> DerivedObject:
    """
    Extraer una sola ventana de OPD de un dataset multi-ventana.

    Reduce la dimensión de ventanas: depth_mm pasa de
    (n, M, N_win) a (n, M, 1).
    """
    win_id = _resolve_index_alias(win_id, window_index, "win_id", "window_index")

    td, dataset = _get_data_and_dataset(view)
    td = td.apply_mask()

    if td.depth_mm is None:
        raise ValueError("No hay datos de OPD")

    if not 0 <= win_id < td.depth_mm.shape[2]:
        raise IndexError(
            f"Ventana fuera de rango: {win_id} (válidas: 0..{td.depth_mm.shape[2] - 1})"
        )

    depth_mm_win = td.depth_mm[:, :, win_id:win_id + 1]
    amplitude_window = (
        td.amplitude[:, :, win_id:win_id + 1]
        if td.amplitude is not None else None
    )

    provenance = _build_provenance(
        dataset, view,
        ExtractionType.WINDOW,
        {"win_id": win_id},
    )

    if name is None:
        name = f"Ventana W{win_id}"

    return DerivedObject(
        name=name,
        X=td.X.copy(), Y=td.Y.copy(), Z=td.Z.copy(),
        depth_mm=depth_mm_win, amplitude=amplitude_window,
        provenance=provenance,
        metadata=_metadata_for_window(dataset, win_id),
    )


# ── Helpers ────────────────────────────────────────────────────────────────


def _inherited_metadata(dataset) -> dict:
    metadata = dict(dataset.metadata)
    if dataset.windows:
        metadata["window_z_min_mm"] = np.asarray(
            [window.z_min for window in dataset.windows], dtype=float
        )
        metadata["window_z_max_mm"] = np.asarray(
            [window.z_max for window in dataset.windows], dtype=float
        )
    return metadata


def _metadata_for_window(dataset, win_id: int) -> dict:
    metadata = _inherited_metadata(dataset)
    if dataset.windows:
        window = dataset.windows[win_id]
        metadata["window_z_min_mm"] = np.asarray([window.z_min], dtype=float)
        metadata["window_z_max_mm"] = np.asarray([window.z_max], dtype=float)
    return metadata


def _resolve_index_alias(
    legacy: Optional[int],
    canonical: Optional[int],
    legacy_name: str,
    canonical_name: str,
) -> int:
    if legacy is None and canonical is None:
        return 0
    if legacy is None:
        return int(canonical)
    if canonical is None:
        return int(legacy)
    if int(legacy) != int(canonical):
        raise ValueError(f"{legacy_name} y {canonical_name} no pueden diferir")
    return int(legacy)


def _select_channel(values, point_mask, measurement: int, win_id: int):
    if values is None:
        return None
    if values.ndim != 3:
        raise ValueError(f"Se esperaba un array (punto, M, ventana), recibido {values.shape}")
    if not 0 <= measurement < values.shape[1]:
        raise IndexError(f"Medición fuera de rango: {measurement}")
    if not 0 <= win_id < values.shape[2]:
        raise IndexError(f"Ventana fuera de rango: {win_id}")
    return values[point_mask, measurement:measurement + 1, win_id:win_id + 1]


def _get_data_and_dataset(view):
    """
    Obtener TransformData y OCTDataset desde un view o dataset.

    Acepta tanto TransformedView como OCTDataset directamente.
    """
    from transforms.base import TransformedView, TransformData

    if isinstance(view, TransformedView):
        td = view.transformed_data
        dataset = view.dataset
    else:
        # Es un OCTDataset directo
        dataset = view
        td = TransformData(
            X=dataset.X.copy(),
            Y=dataset.Y.copy(),
            Z=dataset.Z.copy(),
            coordinate_tolerance_mm=dataset.coordinate_tolerance_mm,
            coordinate_tolerances_mm=dataset.coordinate_tolerances_mm,
            depth_mm=dataset.depth_mm.copy() if dataset.has_peaks else None,
            amplitude=dataset.amplitude.copy() if dataset.has_peaks else None,
        )
    return td, dataset


def _coordinate_tolerance(td, dataset, axis: str) -> float:
    """Resolver la tolerancia física de un eje para datos directos o transformados."""
    tolerances = getattr(td, "coordinate_tolerances_mm", None)
    if isinstance(tolerances, dict) and axis in tolerances:
        return max(float(tolerances[axis]), 1e-9)
    tolerances = getattr(dataset, "coordinate_tolerances_mm", None)
    if isinstance(tolerances, dict) and axis in tolerances:
        return max(float(tolerances[axis]), 1e-9)
    return max(float(getattr(td, "coordinate_tolerance_mm", 1e-9)), 1e-9)


def _build_provenance(dataset, view, ext_type, params) -> Provenance:
    """Construir Provenance con info del pipeline."""
    from transforms.base import TransformedView

    transforms = []
    if isinstance(view, TransformedView):
        transforms = [t.name for t in view.pipeline.steps]

    return Provenance(
        source_file=dataset.filepath,
        extraction_type=ext_type,
        parameters=params,
        transforms_applied=transforms,
    )
