"""Ensamblado conservador de superficies por parches nativos.

Cada parche conserva su propia malla XY, extensión, resolución y posición Z.
Este módulo no interpola, no voxeliza y no rellena huecos entre puntos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from transforms.base import TransformData


@dataclass(frozen=True)
class SurfacePatchSpec:
    """Especificación de un parche que se incorpora a una superficie compuesta."""

    data: Optional[TransformData]
    source: str
    name: str = ""
    z_mm: Optional[float] = None
    x_min: Optional[float] = None
    x_max: Optional[float] = None
    y_min: Optional[float] = None
    y_max: Optional[float] = None
    delta_z_mm: float = 0.0
    tolerance_mm: Optional[float] = None

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


@dataclass
class SurfaceAssemblyResult:
    """Resultado derivado de concatenar parches sin remuestreo."""

    data: TransformData
    patch_stats: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _select_patch(spec: SurfacePatchSpec) -> np.ndarray:
    data = spec.data
    tolerance = max(
        float(spec.tolerance_mm if spec.tolerance_mm is not None else data.coordinate_tolerance_mm),
        1e-9,
    )
    mask = np.isfinite(data.X) & np.isfinite(data.Y) & np.isfinite(data.Z)
    if spec.z_mm is not None:
        mask &= np.abs(data.Z - float(spec.z_mm)) <= tolerance
    if spec.x_min is not None:
        mask &= data.X >= float(spec.x_min) - tolerance
    if spec.x_max is not None:
        mask &= data.X <= float(spec.x_max) + tolerance
    if spec.y_min is not None:
        mask &= data.Y >= float(spec.y_min) - tolerance
    if spec.y_max is not None:
        mask &= data.Y <= float(spec.y_max) + tolerance
    if data.mask is not None:
        mask &= np.asarray(data.mask, dtype=bool)
    return mask


def _estimate_step(values: np.ndarray, tolerance: float) -> Optional[float]:
    unique = np.unique(np.round(values[np.isfinite(values)], decimals=12))
    if unique.size < 2:
        return None
    differences = np.diff(unique)
    differences = differences[differences > tolerance]
    if differences.size == 0:
        return None
    candidate = float(differences[0])
    if np.allclose(differences, candidate, rtol=1e-7, atol=max(tolerance * 2.0, 1e-9)):
        return candidate
    return None


def _stack_optional(chunks: List[Optional[np.ndarray]], lengths: List[int], warnings: List[str], label: str):
    present = [chunk for chunk in chunks if chunk is not None]
    if not present:
        return None
    reference = present[0]
    tail_shape = reference.shape[1:]
    dtype = np.result_type(*(chunk.dtype for chunk in present))
    output = []
    for chunk, length in zip(chunks, lengths):
        if chunk is None:
            warnings.append(f"Parche sin {label}: se conservaron NaN en el resultado")
            output.append(np.full((length,) + tail_shape, np.nan, dtype=dtype))
        else:
            if chunk.shape[1:] != tail_shape:
                raise ValueError(f"Los parches tienen formas incompatibles para {label}")
            output.append(np.asarray(chunk, dtype=dtype))
    return np.concatenate(output, axis=0)


def _surface_units(data: TransformData) -> Dict[str, str]:
    """Resolver unidades físicas del contrato nativo del ensamblador."""
    aliases = {
        "mm": "mm",
        "millimeter": "mm",
        "millimeters": "mm",
        "milimetro": "mm",
        "milímetros": "mm",
    }
    result = {}
    for key in ("X", "Y", "Z", "depth_mm"):
        value = str(data.units.get(key, "mm")).strip().lower()
        if value not in aliases:
            raise ValueError(f"Unidades incompatibles en {key}: {value!r}; se requiere mm")
        result[key] = aliases[value]
    return result


def assemble_surface_patches(patches: List[SurfacePatchSpec]) -> SurfaceAssemblyResult:
    """Concatenar parches con grillas nativas y dominios XY independientes.

    La función sólo selecciona puntos existentes y aplica ``delta_z_mm`` a su
    coordenada Z. No construye productos cartesianos, no interpola y no crea
    puntos para cubrir huecos.
    """
    if not patches:
        raise ValueError("Se requiere al menos un parche")

    x_chunks: List[np.ndarray] = []
    y_chunks: List[np.ndarray] = []
    z_chunks: List[np.ndarray] = []
    depth_mm_chunks: List[Optional[np.ndarray]] = []
    amplitude_chunks: List[Optional[np.ndarray]] = []
    lengths: List[int] = []
    warnings: List[str] = []
    patch_stats: List[Dict[str, Any]] = []
    provenance: List[Dict[str, Any]] = []
    patch_units = [_surface_units(spec.data) for spec in patches]
    target_units = patch_units[0]
    for index, current_units in enumerate(patch_units[1:], start=1):
        for key in target_units:
            if current_units[key] != target_units[key]:
                raise ValueError(
                    f"Unidades incompatibles en {key}: "
                    f"{target_units[key]} / {current_units[key]}"
                )
    units: Dict[str, str] = dict(patches[0].data.units)
    units.update(target_units)
    tolerance = max(
        max(float(p.tolerance_mm if p.tolerance_mm is not None else p.data.coordinate_tolerance_mm) for p in patches),
        1e-9,
    )

    for index, spec in enumerate(patches):
        if spec.data is None:
            raise ValueError(f"Parche {spec.name or index + 1}: faltan datos de superficie")
        data = spec.data
        selected = _select_patch(spec)
        x = np.asarray(data.X[selected], dtype=float)
        y = np.asarray(data.Y[selected], dtype=float)
        z = np.asarray(data.Z[selected], dtype=float) + float(spec.delta_z_mm)
        count = int(x.size)
        lengths.append(count)
        x_chunks.append(x)
        y_chunks.append(y)
        z_chunks.append(z)
        depth_mm_chunks.append(data.depth_mm[selected] if data.depth_mm is not None else None)
        amplitude_chunks.append(data.amplitude[selected] if data.amplitude is not None else None)

        if count == 0:
            warnings.append(f"Parche {spec.name or index + 1} ({spec.source}): sin puntos seleccionados")
            patch_stats.append({
                "name": spec.name or f"parche_{index + 1}",
                "source": spec.source,
                "n_points": 0,
                "z_mm": spec.z_mm,
                "delta_z_mm": float(spec.delta_z_mm),
                "step_x_mm": None,
                "step_y_mm": None,
            })
            continue

        patch_stats.append({
            "name": spec.name or f"parche_{index + 1}",
            "source": spec.source,
            "n_points": count,
            "x_min_mm": float(np.min(x)),
            "x_max_mm": float(np.max(x)),
            "y_min_mm": float(np.min(y)),
            "y_max_mm": float(np.max(y)),
            "z_mm": float(np.median(z)),
            "source_z_mm": spec.z_mm,
            "delta_z_mm": float(spec.delta_z_mm),
            "step_x_mm": _estimate_step(x, tolerance),
            "step_y_mm": _estimate_step(y, tolerance),
        })
        provenance.append({
            "operation": "surface_patch",
            "patch_index": index,
            "name": spec.name or f"parche_{index + 1}",
            "source": spec.source,
            "z_mm": spec.z_mm,
            "delta_z_mm": float(spec.delta_z_mm),
            "x_min": spec.x_min,
            "x_max": spec.x_max,
            "y_min": spec.y_min,
            "y_max": spec.y_max,
            "n_points": count,
        })

    result_metadata = {
        "derived_operation": "ensamblado_superficies_nativas",
        "surface_patches": patch_stats,
        "resampling": "none",
        "position_tolerance_mm": tolerance,
        "position_tolerance_um": tolerance * 1000.0,
    }
    for data in (spec.data for spec in patches):
        for key, value in data.units.items():
            if key in units and units[key] != value:
                warnings.append(f"Unidades incompatibles en {key}: {units[key]} / {value}")

    result_data = TransformData(
        X=np.concatenate(x_chunks) if x_chunks else np.empty(0, dtype=float),
        Y=np.concatenate(y_chunks) if y_chunks else np.empty(0, dtype=float),
        Z=np.concatenate(z_chunks) if z_chunks else np.empty(0, dtype=float),
        coordinate_tolerance_mm=tolerance,
        depth_mm=_stack_optional(depth_mm_chunks, lengths, warnings, "OPD"),
        amplitude=_stack_optional(amplitude_chunks, lengths, warnings, "amplitud"),
        units=units,
        metadata=result_metadata,
        provenance=provenance,
    )
    return SurfaceAssemblyResult(data=result_data, patch_stats=patch_stats, warnings=warnings)


def derived_from_surface_assembly(
    result: SurfaceAssemblyResult,
    sources: Dict[str, str],
    name: str,
):
    """Crear un DerivedObject reabrible a partir de parches A/B nativos."""
    from extract.derived import DerivedObject, ExtractionType, Provenance

    parameters = {
        "sources": dict(sources),
        "patches": list(result.patch_stats),
        "warnings": list(result.warnings),
        "operation": "ensamblado_superficies_nativas",
        "resampling": "none",
    }
    metadata = dict(result.data.metadata)
    metadata.update({
        "sample_name": name,
        "derived_operation": "ensamblado_superficies_nativas",
        "derived_from_sources": dict(sources),
        "assembly_warnings": list(result.warnings),
    })
    source_file = "; ".join(f"{slot}: {path}" for slot, path in sorted(sources.items()))
    provenance = Provenance(
        source_file=source_file,
        extraction_type=ExtractionType.CUSTOM,
        parameters=parameters,
        transforms_applied=["Ensamblado de superficies nativas"],
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
