"""Ensamblado conservador de Niveles de una misma Muestra/medición."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from transforms.base import TransformData
from model.volume import _cluster_axis


@dataclass(frozen=True)
class LevelSelection:
    """Selección rectangular de Medidas/Puntos pertenecientes a un Nivel."""

    z_mm: float
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    delta_z_mm: float = 0.0
    enabled: bool = True
    tolerance_mm: float = 0.002

    @property
    def x_min_mm(self) -> Optional[float]:
        return self.x_min

    @property
    def x_max_mm(self) -> Optional[float]:
        return self.x_max

    @property
    def y_min_mm(self) -> Optional[float]:
        return self.y_min

    @property
    def y_max_mm(self) -> Optional[float]:
        return self.y_max

    def contains(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        mask = np.isfinite(x) & np.isfinite(y)
        if self.x_min is not None:
            mask &= x >= self.x_min - self.tolerance_mm
        if self.x_max is not None:
            mask &= x <= self.x_max + self.tolerance_mm
        if self.y_min is not None:
            mask &= y >= self.y_min - self.tolerance_mm
        if self.y_max is not None:
            mask &= y <= self.y_max + self.tolerance_mm
        return mask


@dataclass
class LevelAssemblyResult:
    data: TransformData
    warnings: List[str] = field(default_factory=list)
    stats: List[Dict[str, Any]] = field(default_factory=list)


def _unique_in_range(values: np.ndarray, lower, upper, tolerance: float) -> np.ndarray:
    finite = np.asarray(values, dtype=float).ravel()
    finite = finite[np.isfinite(finite)]
    if lower is not None:
        finite = finite[finite >= lower - tolerance]
    if upper is not None:
        finite = finite[finite <= upper + tolerance]
    if finite.size == 0:
        return np.empty(0, dtype=float)
    centers, _ = _cluster_axis(finite, max(float(tolerance), 1e-9))
    return centers


def assemble_levels(data: TransformData, selections: List[LevelSelection]) -> LevelAssemblyResult:
    """Construir una Muestra derivada uniendo sólo Niveles seleccionados.

    La grilla esperada de cada Nivel es el producto cartesiano de sus valores
    X/Y disponibles dentro de la selección. Si falta una combinación, se crea
    el punto con OPD/amplitud en ``NaN`` y se informa una advertencia.
    """
    tolerance = max(float(data.coordinate_tolerance_mm), 1e-9)
    out_x: List[float] = []
    out_y: List[float] = []
    out_z: List[float] = []
    depth_mm_rows: List[np.ndarray] = []
    amplitude_rows: List[np.ndarray] = []
    warnings: List[str] = []
    stats: List[Dict[str, Any]] = []

    for selection in selections:
        if not selection.enabled:
            continue
        level_mask = np.isfinite(data.Z) & (
            np.abs(data.Z - selection.z_mm) <= max(selection.tolerance_mm, tolerance)
        )
        level_indices = np.flatnonzero(level_mask)
        region_mask = level_mask & selection.contains(data.X, data.Y)
        region_indices = np.flatnonzero(region_mask)
        xs = _unique_in_range(data.X[level_mask], selection.x_min, selection.x_max, tolerance)
        ys = _unique_in_range(data.Y[level_mask], selection.y_min, selection.y_max, tolerance)
        expected = int(xs.size * ys.size)
        if expected == 0:
            warnings.append(f"Nivel Z={selection.z_mm:g}: no hay Medidas/Puntos en la selección")
            stats.append({"z_mm": selection.z_mm, "expected": 0, "available": 0, "missing": 0})
            continue

        available = 0
        missing = 0
        for x_value in xs:
            for y_value in ys:
                matches = region_indices[
                    (np.abs(data.X[region_indices] - x_value) <= tolerance)
                    & (np.abs(data.Y[region_indices] - y_value) <= tolerance)
                ]
                if matches.size:
                    index = int(matches[0])
                    available += 1
                    if matches.size > 1:
                        warnings.append(
                            f"Nivel Z={selection.z_mm:g}: Medida/Punto duplicada en "
                            f"X={x_value:g}, Y={y_value:g}"
                        )
                    z_value = float(data.Z[index]) + selection.delta_z_mm
                    x_output = float(data.X[index])
                    y_output = float(data.Y[index])
                    depth_mm_value = data.depth_mm[index].copy() if data.depth_mm is not None else None
                    amplitude_value = data.amplitude[index].copy() if data.amplitude is not None else None
                else:
                    missing += 1
                    z_value = float(selection.z_mm) + selection.delta_z_mm
                    x_output = float(x_value)
                    y_output = float(y_value)
                    depth_mm_value = np.full(data.depth_mm.shape[1:], np.nan, dtype=data.depth_mm.dtype) if data.depth_mm is not None else None
                    amplitude_value = np.full(data.amplitude.shape[1:], np.nan, dtype=data.amplitude.dtype) if data.amplitude is not None else None
                out_x.append(x_output)
                out_y.append(y_output)
                out_z.append(z_value)
                if depth_mm_value is not None:
                    depth_mm_rows.append(depth_mm_value)
                if amplitude_value is not None:
                    amplitude_rows.append(amplitude_value)

        if missing:
            warnings.append(
                f"Nivel Z={selection.z_mm:g}: faltan {missing} de {expected} "
                "Medidas/Puntos esperadas; se conservaron como NaN"
            )
        stats.append({
            "z_mm": selection.z_mm,
            "delta_z_mm": selection.delta_z_mm,
            "expected": expected,
            "available": available,
            "missing": missing,
            "selected_source_points": int(region_indices.size),
            "source_level_points": int(level_indices.size),
        })

    if data.depth_mm is not None:
        depth_mm = np.stack(depth_mm_rows) if depth_mm_rows else np.empty((0,) + data.depth_mm.shape[1:], dtype=data.depth_mm.dtype)
    else:
        depth_mm = None
    if data.amplitude is not None:
        amplitude = np.stack(amplitude_rows) if amplitude_rows else np.empty((0,) + data.amplitude.shape[1:], dtype=data.amplitude.dtype)
    else:
        amplitude = None
    result_data = TransformData(
        X=np.asarray(out_x, dtype=float),
        Y=np.asarray(out_y, dtype=float),
        Z=np.asarray(out_z, dtype=float),
        coordinate_tolerance_mm=data.coordinate_tolerance_mm,
        depth_mm=depth_mm,
        amplitude=amplitude,
        units=dict(data.units),
        metadata=dict(data.metadata),
        provenance=list(data.provenance),
    )
    return LevelAssemblyResult(data=result_data, warnings=warnings, stats=stats)


def derived_from_assembly(result: LevelAssemblyResult, source_file: str, name: str):
    """Crear un DerivedObject reabrible a partir de un ensamblado."""
    from extract.derived import DerivedObject, ExtractionType, Provenance

    parameters = {
        "levels": result.stats,
        "warnings": list(result.warnings),
        "operation": "ensamblado_de_niveles",
    }
    metadata = dict(result.data.metadata)
    metadata.update({
        "sample_name": name,
        "derived_from": source_file,
        "derived_operation": "ensamblado_de_niveles",
        "assembly_warnings": list(result.warnings),
    })
    provenance = Provenance(
        source_file=source_file,
        extraction_type=ExtractionType.CUSTOM,
        parameters=parameters,
        transforms_applied=["Ensamblado de Niveles"],
    )
    return DerivedObject(
        name=name,
        X=result.data.X.copy(),
        Y=result.data.Y.copy(),
        Z=result.data.Z.copy(),
        depth_mm=result.data.depth_mm.copy() if result.data.depth_mm is not None else None,
        amplitude=result.data.amplitude.copy() if result.data.amplitude is not None else None,
        provenance=provenance,
        metadata=metadata,
    )
