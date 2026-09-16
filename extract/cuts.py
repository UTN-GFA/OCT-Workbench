"""Cortes 1D/2D sobre datasets o vistas transformadas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from model.dataset import _canonical_unique


@dataclass(frozen=True)
class Cuts:
    """Perfiles obtenidos al cortar una medición 1D o 2D."""

    dimension: str
    x_axis: str
    y_axis: Optional[str]
    x_position: np.ndarray
    x_depth_mm: np.ndarray
    x_amplitude: Optional[np.ndarray]
    y_position: Optional[np.ndarray]
    y_depth_mm: Optional[np.ndarray]
    y_amplitude: Optional[np.ndarray]
    selected_x: Optional[float]
    selected_y: Optional[float]
    requested_x: Optional[float]
    requested_y: Optional[float]

    @property
    def x_position_mm(self) -> np.ndarray:
        return self.x_position

    @property
    def y_position_mm(self) -> Optional[np.ndarray]:
        return self.y_position

    @property
    def selected_x_mm(self) -> Optional[float]:
        return self.selected_x

    @property
    def selected_y_mm(self) -> Optional[float]:
        return self.selected_y

    @property
    def requested_x_mm(self) -> Optional[float]:
        return self.requested_x

    @property
    def requested_y_mm(self) -> Optional[float]:
        return self.requested_y


def extract_cuts(
    source: Any,
    *,
    x_value: Optional[float] = None,
    y_value: Optional[float] = None,
    win_id: Optional[int] = None,
    measurement: Optional[int] = None,
    requested_x_mm: Optional[float] = None,
    requested_y_mm: Optional[float] = None,
    window_index: Optional[int] = None,
    measurement_index: Optional[int] = None,
) -> Cuts:
    """Extraer el perfil 1D o los dos cortes de una medición.

    ``source`` puede ser un ``OCTDataset`` o una ``TransformedView``.
    En una grilla 2D, ``x_value`` fija el corte Y y ``y_value`` fija
    el corte X. Se usa la coordenada adquirida más cercana y se devuelve
    también la coordenada realmente utilizada.
    """
    if requested_x_mm is not None:
        if x_value is not None and not np.isclose(x_value, requested_x_mm):
            raise ValueError("x_value y requested_x_mm no pueden diferir")
        x_value = requested_x_mm
    if requested_y_mm is not None:
        if y_value is not None and not np.isclose(y_value, requested_y_mm):
            raise ValueError("y_value y requested_y_mm no pueden diferir")
        y_value = requested_y_mm
    win_id = _resolve_index_alias(win_id, window_index, "win_id", "window_index")
    measurement = _resolve_index_alias(
        measurement, measurement_index, "measurement", "measurement_index"
    )

    depth_mm_all = getattr(source, "depth_mm", None)
    if depth_mm_all is None:
        raise ValueError("La medición no contiene datos OPD")
    _validate_indices(depth_mm_all, win_id, measurement)

    depth_mm = np.asarray(depth_mm_all[:, measurement, win_id], dtype=float)
    amplitude_all = getattr(source, "amplitude", None)
    amp = None if amplitude_all is None else np.asarray(
        amplitude_all[:, measurement, win_id], dtype=float
    )
    x = np.asarray(source.X, dtype=float)
    y = np.asarray(source.Y, dtype=float)
    tolerances = _source_coordinate_tolerances(source)
    tolerance_x = tolerances["X"]
    tolerance_y = tolerances["Y"]
    varies_x = _varies(x, tolerance_x)
    varies_y = _varies(y, tolerance_y)

    if varies_x and not varies_y:
        order = np.argsort(x)
        return Cuts(
            dimension="1D", x_axis="X", y_axis=None,
            x_position=x[order], x_depth_mm=depth_mm[order],
            x_amplitude=amp[order] if amp is not None else None,
            y_position=None, y_depth_mm=None, y_amplitude=None,
            selected_x=None, selected_y=None,
            requested_x=x_value, requested_y=y_value,
        )

    if varies_y and not varies_x:
        order = np.argsort(y)
        return Cuts(
            dimension="1D", x_axis="Y", y_axis=None,
            x_position=y[order], x_depth_mm=depth_mm[order],
            x_amplitude=amp[order] if amp is not None else None,
            y_position=None, y_depth_mm=None, y_amplitude=None,
            selected_x=None, selected_y=None,
            requested_x=x_value, requested_y=y_value,
        )

    if not varies_x and not varies_y:
        raise ValueError("La medición no contiene un barrido 1D o 2D")

    requested_x = float(np.mean(x)) if x_value is None else float(x_value)
    requested_y = float(np.mean(y)) if y_value is None else float(y_value)
    x_target = _nearest_unique(x, requested_x, tolerance_x)
    y_target = _nearest_unique(y, requested_y, tolerance_y)

    mask_x = np.isclose(y, y_target, atol=tolerance_y, rtol=0.0)
    mask_y = np.isclose(x, x_target, atol=tolerance_x, rtol=0.0)
    x_order = np.argsort(x[mask_x])
    y_order = np.argsort(y[mask_y])

    return Cuts(
        dimension="2D", x_axis="X", y_axis="Y",
        x_position=x[mask_x][x_order], x_depth_mm=depth_mm[mask_x][x_order],
        x_amplitude=amp[mask_x][x_order] if amp is not None else None,
        y_position=y[mask_y][y_order], y_depth_mm=depth_mm[mask_y][y_order],
        y_amplitude=amp[mask_y][y_order] if amp is not None else None,
        selected_x=x_target, selected_y=y_target,
        requested_x=requested_x, requested_y=requested_y,
    )


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


def _validate_indices(depth_mm: np.ndarray, win_id: int, measurement: int) -> None:
    if not 0 <= measurement < depth_mm.shape[1]:
        raise IndexError(f"Medición fuera de rango: M{measurement}")
    if not 0 <= win_id < depth_mm.shape[2]:
        raise IndexError(f"Ventana fuera de rango: W{win_id}")


def _source_coordinate_tolerances(source: Any) -> dict[str, float]:
    raw = getattr(source, "coordinate_tolerances_mm", None)
    if isinstance(raw, dict):
        return {axis: max(float(raw.get(axis, 1e-9)), 1e-9) for axis in ("X", "Y", "Z")}
    scalar = max(float(getattr(source, "coordinate_tolerance_mm", 1e-9)), 1e-9)
    return {axis: scalar for axis in ("X", "Y", "Z")}


def _nearest_unique(values: np.ndarray, requested: float, tolerance: float) -> float:
    unique = _canonical_unique(values, tolerance=tolerance)
    return float(unique[np.argmin(np.abs(unique - requested))])


def _varies(values: np.ndarray, tolerance: float) -> bool:
    return _canonical_unique(values, tolerance=tolerance).size > 1
