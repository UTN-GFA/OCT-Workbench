"""Inspección de metadata y calidad de datasets OCT."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from model.dataset import OCTDataset


@dataclass(frozen=True)
class MetadataValue:
    """Valor de un campo de metadata para A y B."""

    key: str
    label: str
    value_a: Any
    value_b: Any
    same: bool
    severity: str


@dataclass(frozen=True)
class MetadataComparison:
    """Comparación de metadata entre dos datasets."""

    rows: tuple[MetadataValue, ...]
    has_b: bool
    compatible_for_visual: bool
    compatible_for_pointwise: bool
    warnings: tuple[str, ...]

    def value(self, key: str) -> MetadataValue:
        for row in self.rows:
            if row.key == key:
                return row
        raise KeyError(key)


@dataclass(frozen=True)
class QualitySummary:
    """Conteo de valores válidos y faltantes."""

    total_depth_mm_points: int
    valid_depth_mm_points: int
    nan_depth_mm_points: int
    total_amplitude_points: int
    valid_amplitude_points: int
    nan_amplitude_points: int
    total_points: int = 0
    finite_coordinate_points: int = 0
    expected_points: Optional[int] = None
    acquired_points: Optional[int] = None
    scan_aborted: bool = False

    @property
    def depth_mm_valid_percent(self) -> float:
        return _percent(self.valid_depth_mm_points, self.total_depth_mm_points)

    @property
    def amplitude_valid_percent(self) -> float:
        return _percent(self.valid_amplitude_points, self.total_amplitude_points)


_METADATA_FIELDS = (
    ("sample_name", "Muestra"),
    ("schema_version", "Schema"),
    ("software_version", "Software"),
    ("format", "Formato"),
    ("dataset_type", "Tipo de barrido"),
    ("n_points_total", "Puntos"),
    ("m_measurements", "Mediciones por punto"),
    ("n_windows", "Ventanas OPD"),
    ("scan_mode", "Modo de barrido"),
    ("start_time", "Inicio"),
    ("duration_sec", "Duración (s)"),
    ("aborted", "Scan abortado"),
    ("x_range", "Rango X (mm)"),
    ("y_range", "Rango Y (mm)"),
    ("x_step", "Paso X (mm)"),
    ("y_step", "Paso Y (mm)"),
)


def quality_summary(dataset: OCTDataset) -> QualitySummary:
    """Resumir validez de payloads, coordenadas y estado de adquisición."""
    depth_mm = np.asarray(dataset.depth_mm) if dataset.depth_mm is not None else np.array([])
    amp = np.asarray(dataset.amplitude) if dataset.amplitude is not None else np.array([])
    depth_mm_total = int(depth_mm.size)
    amp_total = int(amp.size)
    depth_mm_valid = int(np.isfinite(depth_mm).sum())
    amp_valid = int(np.isfinite(amp).sum())
    coordinates = np.column_stack((dataset.X, dataset.Y, dataset.Z))
    finite_coordinates = int(np.isfinite(coordinates).all(axis=1).sum())
    metadata = dataset.metadata
    return QualitySummary(
        total_depth_mm_points=depth_mm_total,
        valid_depth_mm_points=depth_mm_valid,
        nan_depth_mm_points=depth_mm_total - depth_mm_valid,
        total_amplitude_points=amp_total,
        valid_amplitude_points=amp_valid,
        nan_amplitude_points=amp_total - amp_valid,
        total_points=dataset.n_points,
        finite_coordinate_points=finite_coordinates,
        expected_points=_optional_int(metadata.get("n_points_total")),
        acquired_points=_optional_int(metadata.get("n_points_acquired")),
        scan_aborted=bool(metadata.get("aborted", False)),
    )


def build_metadata_comparison(
    dataset_a: OCTDataset,
    dataset_b: Optional[OCTDataset] = None,
) -> MetadataComparison:
    """Construir la tabla de metadata de A o la comparación A/B."""
    rows = []
    warnings = []
    for key, label in _METADATA_FIELDS:
        value_a = _metadata_value(dataset_a, key)
        value_b = _metadata_value(dataset_b, key) if dataset_b is not None else None
        same = dataset_b is None or _values_equal(value_a, value_b)
        severity = "same" if dataset_b is None or same else "different"
        rows.append(MetadataValue(key, label, value_a, value_b, same, severity))

    if dataset_b is None:
        return MetadataComparison(tuple(rows), False, True, True, tuple())

    if dataset_a.dataset_type != dataset_b.dataset_type:
        warnings.append("A y B no son del mismo tipo de barrido")
    if dataset_a.grid.nx != dataset_b.grid.nx or dataset_a.grid.ny != dataset_b.grid.ny:
        warnings.append("Las dimensiones de la grilla no coinciden")
    if not _range_close(dataset_a.grid.x_range, dataset_b.grid.x_range):
        warnings.append("El rango X de A y B no coincide")
    if not _range_close(dataset_a.grid.y_range, dataset_b.grid.y_range):
        warnings.append("El rango Y de A y B no coincide")

    pointwise = _same_coordinates(dataset_a, dataset_b)
    if not pointwise:
        warnings.append("Las coordenadas no coinciden punto a punto")
    return MetadataComparison(
        tuple(rows), True, True, pointwise, tuple(dict.fromkeys(warnings))
    )


def _metadata_value(dataset: Optional[OCTDataset], key: str) -> Any:
    if dataset is None:
        return None
    if key == "format":
        return dataset.format.upper()
    if key == "dataset_type":
        return dataset.dataset_type.name
    if key == "n_windows":
        return dataset.n_windows
    if key == "x_range":
        return tuple(round(v, 9) for v in dataset.grid.x_range)
    if key == "y_range":
        return tuple(round(v, 9) for v in dataset.grid.y_range)
    if key == "x_step":
        return _round_optional(dataset.grid.x_step)
    if key == "y_step":
        return _round_optional(dataset.grid.y_step)
    if key == "n_points_total":
        return dataset.metadata.get(key, dataset.n_points)
    return dataset.metadata.get(key)


def _same_coordinates(a: OCTDataset, b: OCTDataset) -> bool:
    return (
        a.X.shape == b.X.shape
        and a.Y.shape == b.Y.shape
        and a.Z.shape == b.Z.shape
        and np.allclose(a.X, b.X, equal_nan=True)
        and np.allclose(a.Y, b.Y, equal_nan=True)
        and np.allclose(a.Z, b.Z, equal_nan=True)
    )


def _round_optional(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(float(value), 12)


def _range_close(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return bool(np.allclose(a, b, rtol=0.0, atol=1e-9))


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, tuple) or isinstance(b, tuple):
        try:
            return bool(np.allclose(a, b, equal_nan=True))
        except (TypeError, ValueError):
            return a == b
    return a == b


def _percent(valid: int, total: int) -> float:
    return 100.0 if total == 0 else 100.0 * valid / total


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
