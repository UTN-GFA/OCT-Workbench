"""
compare.pair
Par de comparación: dos fuentes de datos para contrastar.

Un ComparisonPair envuelve dos datasets/views/derivados y
ofrece operaciones de comparación no destructivas.
Los resultados son DerivedObjects o dicts exportables.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

from model.dataset import OCTDataset, _canonical_unique
from transforms.base import TransformedView, TransformData
from extract.derived import (
    DerivedObject, ExtractionType, Provenance,
)


# Tipo aceptado como fuente
Source = Union[OCTDataset, TransformedView, DerivedObject]

_DEPTH_UNIT_ALIASES = {
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",
    "milimetro": "mm",
    "milímetros": "mm",
    "cm": "cm",
    "centimeter": "cm",
    "centimeters": "cm",
    "centimetro": "cm",
    "centímetros": "cm",
}


def _source_coordinate_tolerances(source: Source) -> Dict[str, float]:
    """Obtener tolerancias espaciales por eje declaradas por una fuente."""
    raw = getattr(source, "coordinate_tolerances_mm", None)
    if isinstance(raw, dict):
        return {
            axis: max(float(raw.get(axis, 1e-9)), 1e-9)
            for axis in ("X", "Y", "Z")
        }
    try:
        scalar = float(getattr(source, "coordinate_tolerance_mm"))
    except (AttributeError, TypeError, ValueError):
        scalar = 1e-9
    scalar = max(scalar, 1e-9)
    return {axis: scalar for axis in ("X", "Y", "Z")}


def _bucket_key(x: float, y: float, z: float, tolerances: Dict[str, float]):
    """Obtener un bucket espacial; el bucket no decide igualdad física."""
    return (
        int(np.floor(x / tolerances["X"])),
        int(np.floor(y / tolerances["Y"])),
        int(np.floor(z / tolerances["Z"])),
    )


def _neighbor_keys(key):
    return (
        (key[0] + dx, key[1] + dy, key[2] + dz)
        for dx, dy, dz in product((-1, 0, 1), repeat=3)
    )


def _positions_close(td: TransformData, i: int, j: int, tolerances: Dict[str, float]) -> bool:
    return (
        abs(td.X[i] - td.X[j]) <= tolerances["X"]
        and abs(td.Y[i] - td.Y[j]) <= tolerances["Y"]
        and abs(td.Z[i] - td.Z[j]) <= tolerances["Z"]
    )


def _validate_unique_positions(td: TransformData, label: str, tolerances: Dict[str, float]) -> None:
    """Rechazar coordenadas duplicadas dentro de la tolerancia física."""
    buckets = {}
    for index in range(td.n_points):
        if not np.isfinite(td.X[index]) or not np.isfinite(td.Y[index]) or not np.isfinite(td.Z[index]):
            continue
        key = _bucket_key(td.X[index], td.Y[index], td.Z[index], tolerances)
        for neighbor in _neighbor_keys(key):
            for previous in buckets.get(neighbor, ()):
                if _positions_close(td, index, previous, tolerances):
                    raise ValueError(f"Coordenada duplicada en {label}: {index} y {previous}")
        buckets.setdefault(key, []).append(index)


def _source_units(source: Source) -> Dict[str, str]:
    """Resolver unidades declaradas, con mm como unidad canónica histórica."""
    if isinstance(source, TransformedView):
        units = source.transformed_data.units
    elif isinstance(source, (OCTDataset, DerivedObject)):
        units = source.metadata.get("units", {})
    else:
        units = {}
    resolved = dict(units) if isinstance(units, dict) else {}
    resolved.setdefault("depth_mm", "mm")
    resolved.setdefault("X", "mm")
    resolved.setdefault("Y", "mm")
    resolved.setdefault("Z", "mm")
    return resolved


def _source_depth_axis_kind(source: Source) -> str:
    """Resolver la semántica del canal de profundidad de una fuente."""
    if isinstance(source, TransformedView):
        metadata = source.dataset.metadata
    elif isinstance(source, (OCTDataset, DerivedObject)):
        metadata = source.metadata
    else:
        metadata = {}
    kind = str(metadata.get("depth_axis_kind", "physical_depth_mm"))
    if kind not in {"physical_depth_mm"}:
        raise ValueError(f"depth_axis_kind no soportado: {kind!r}")
    return kind


def _normalize_depth_unit(unit: Any) -> str:
    value = str(unit).strip().lower()
    return _DEPTH_UNIT_ALIASES.get(value, value)


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


def _resolve(source: Source) -> Tuple[TransformData, str]:
    """
    Resolver una fuente a TransformData + nombre.
    Acepta OCTDataset, TransformedView o DerivedObject.
    """
    if isinstance(source, TransformedView):
        td = source.transformed_data.apply_mask()
        name = source.dataset.filename
    elif isinstance(source, OCTDataset):
        td = TransformData(
            X=source.X.copy(), Y=source.Y.copy(), Z=source.Z.copy(),
            coordinate_tolerance_mm=source.coordinate_tolerance_mm,
            coordinate_tolerances_mm=source.coordinate_tolerances_mm,
            depth_mm=source.depth_mm.copy() if source.has_peaks else None,
            amplitude=source.amplitude.copy() if source.has_peaks else None,
        )
        name = source.filename
    elif isinstance(source, DerivedObject):
        td = TransformData(
            X=source.X.copy(), Y=source.Y.copy(), Z=source.Z.copy(),
            coordinate_tolerance_mm=source.coordinate_tolerance_mm,
            coordinate_tolerances_mm=source.coordinate_tolerances_mm,
            depth_mm=source.depth_mm.copy() if source.depth_mm is not None else None,
            amplitude=source.amplitude.copy() if source.amplitude is not None else None,
        )
        name = source.name
    else:
        raise TypeError(f"Fuente no soportada: {type(source)}")
    return td, name


@dataclass
class ComparisonStats:
    """Estadísticas de una comparación entre dos superficies."""
    n_points_a: int
    n_points_b: int
    n_points_common: int

    # Estadísticas de A
    mean_a: float
    std_a: float
    pv_a: float      # pico-valle

    # Estadísticas de B
    mean_b: float
    std_b: float
    pv_b: float

    # Estadísticas de la diferencia
    mean_diff: float
    std_diff: float
    pv_diff: float
    rms_diff: float
    max_abs_diff: float
    depth_mm_unit: str = "mm"
    depth_axis_kind: str = "physical_depth_mm"

    def summary(self) -> str:
        lines = [
            f"{'═' * 50}",
            f"  Comparación de superficies",
            f"{'═' * 50}",
            f"  Puntos A          : {self.n_points_a}",
            f"  Puntos B          : {self.n_points_b}",
            f"  Puntos comunes    : {self.n_points_common}",
            f"",
            f"  {'':20s} {'A':>12s} {'B':>12s} {'A − B':>12s}",
            f"  {'─' * 56}",
            f"  {'Media':20s} {self.mean_a:12.6f} {self.mean_b:12.6f} {self.mean_diff:12.6f}",
            f"  {'STD':20s} {self.std_a:12.6f} {self.std_b:12.6f} {self.std_diff:12.6f}",
            f"  {'Pico-Valle':20s} {self.pv_a:12.6f} {self.pv_b:12.6f} {self.pv_diff:12.6f}",
            f"  {'RMS diff':20s} {'':12s} {'':12s} {self.rms_diff:12.6f}",
            f"  {'Máx |diff|':20s} {'':12s} {'':12s} {self.max_abs_diff:12.6f}",
            f"{'═' * 50}",
        ]
        return "\n".join(lines)


class ComparisonPair:
    """
    Par de comparación entre dos fuentes de datos.

    Acepta cualquier combinación de OCTDataset, TransformedView
    o DerivedObject como fuentes A y B.

    Uso típico:
        pair = ComparisonPair(view_a, view_b)
        diff = pair.difference(win_id=0)
        stats = pair.statistics(win_id=0)
        print(stats.summary())
    """

    def __init__(self, source_a: Source, source_b: Source) -> None:
        self._td_a, self._name_a = _resolve(source_a)
        self._td_b, self._name_b = _resolve(source_b)
        self._source_a = source_a
        self._source_b = source_b
        self._units_a = _source_units(source_a)
        self._units_b = _source_units(source_b)
        self._depth_axis_kind_a = _source_depth_axis_kind(source_a)
        self._depth_axis_kind_b = _source_depth_axis_kind(source_b)
        if self._depth_axis_kind_a != self._depth_axis_kind_b:
            raise ValueError(
                "ejes de profundidad incompatibles: "
                f"A={self._depth_axis_kind_a!r}, B={self._depth_axis_kind_b!r}"
            )
        self._depth_axis_kind = self._depth_axis_kind_a
        self._depth_mm_unit = _normalize_depth_unit(self._units_a["depth_mm"])
        if self._depth_mm_unit != _normalize_depth_unit(self._units_b["depth_mm"]):
            raise ValueError(
                "unidades OPD incompatibles: "
                f"A={self._units_a['depth_mm']!r}, B={self._units_b['depth_mm']!r}"
            )

    @property
    def name_a(self) -> str:
        return self._name_a

    @property
    def name_b(self) -> str:
        return self._name_b

    # ── Alineación de grillas ──────────────────────────────────────────

    def _align_grids(
        self, win_id: Optional[int] = None, measurement: Optional[int] = None
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Alinear las dos fuentes a una grilla común.

        Busca puntos con posiciones XY coincidentes (dentro de
        tolerancia). Retorna (x_common, y_common, z_a, z_b)
        solo para los puntos que existen en ambos.
        """
        td_a, td_b = self._td_a, self._td_b

        if td_a.depth_mm is None or td_b.depth_mm is None:
            raise ValueError("Ambas fuentes necesitan datos de OPD")

        _validate_selection(td_a, win_id, measurement)
        _validate_selection(td_b, win_id, measurement)
        z_a = td_a.depth_mm[:, measurement, win_id]
        z_b = td_b.depth_mm[:, measurement, win_id]

        # Los buckets sólo aceleran la búsqueda; la igualdad se decide
        # comparando cada eje contra la tolerancia física común.
        tolerances_a = _source_coordinate_tolerances(self._source_a)
        tolerances_b = _source_coordinate_tolerances(self._source_b)
        tolerances = {
            axis: max(tolerances_a[axis], tolerances_b[axis])
            for axis in ("X", "Y", "Z")
        }
        _validate_unique_positions(td_a, "A", tolerances)
        _validate_unique_positions(td_b, "B", tolerances)

        b_lookup = {}
        for j in range(td_b.n_points):
            if not np.isfinite(td_b.X[j]) or not np.isfinite(td_b.Y[j]) or not np.isfinite(td_b.Z[j]):
                continue
            key = _bucket_key(td_b.X[j], td_b.Y[j], td_b.Z[j], tolerances)
            b_lookup.setdefault(key, []).append(j)

        x_common, y_common, z_common = [], [], []
        za_common, zb_common = [], []
        used_b = set()
        for i in range(td_a.n_points):
            if not np.isfinite(td_a.X[i]) or not np.isfinite(td_a.Y[i]) or not np.isfinite(td_a.Z[i]):
                continue
            key = _bucket_key(td_a.X[i], td_a.Y[i], td_a.Z[i], tolerances)
            candidates = []
            for neighbor in _neighbor_keys(key):
                for candidate in b_lookup.get(neighbor, ()):
                    if (
                        abs(td_a.X[i] - td_b.X[candidate]) <= tolerances["X"]
                        and abs(td_a.Y[i] - td_b.Y[candidate]) <= tolerances["Y"]
                        and abs(td_a.Z[i] - td_b.Z[candidate]) <= tolerances["Z"]
                    ):
                        candidates.append(candidate)
            if len(candidates) > 1:
                raise ValueError(f"Emparejamiento ambiguo para el punto {i} de A")
            if candidates:
                j = candidates[0]
                if j in used_b:
                    raise ValueError("El emparejamiento A/B no es uno-a-uno")
                used_b.add(j)
                x_common.append(td_a.X[i])
                y_common.append(td_a.Y[i])
                z_common.append(td_a.Z[i])
                za_common.append(z_a[i])
                zb_common.append(z_b[j])

        return (
            np.array(x_common), np.array(y_common), np.array(z_common),
            np.array(za_common), np.array(zb_common),
        )

    # ── Diferencia ─────────────────────────────────────────────────────

    def difference(
        self,
        win_id: Optional[int] = None,
        measurement: Optional[int] = None,
        name: Optional[str] = None,
        window_index: Optional[int] = None,
        measurement_index: Optional[int] = None,
    ) -> DerivedObject:
        """
        Calcular A − B en los puntos comunes.

        Retorna un DerivedObject con la diferencia punto a punto.
        """
        win_id = _resolve_index_alias(win_id, window_index, "win_id", "window_index")
        measurement = _resolve_index_alias(
            measurement, measurement_index, "measurement", "measurement_index"
        )
        x, y, z, za, zb = self._align_grids(win_id, measurement)

        if len(x) == 0:
            raise ValueError("No hay puntos comunes entre A y B")

        diff = za - zb

        # Empaquetar como depth_mm shape (n, 1, 1)
        depth_mm_diff = diff.reshape(-1, 1, 1)

        provenance = Provenance(
            source_file=f"{self._name_a} vs {self._name_b}",
            extraction_type=ExtractionType.CUSTOM,
            parameters={
                "operation": "difference",
                "win_id": win_id,
                "measurement": measurement,
                "n_common": len(x),
            },
            transforms_applied=[],
        )

        if name is None:
            name = f"Diff: {self._name_a} − {self._name_b}"

        return DerivedObject(
            name=name,
            X=x, Y=y, Z=z,
            depth_mm=depth_mm_diff,
            provenance=provenance,
            metadata={
                "units": {"depth_mm": self._depth_mm_unit},
                "depth_axis_kind": self._depth_axis_kind,
            },
        )

    # ── Estadísticas ───────────────────────────────────────────────────

    def statistics(
        self,
        win_id: Optional[int] = None,
        measurement: Optional[int] = None,
        window_index: Optional[int] = None,
        measurement_index: Optional[int] = None,
    ) -> ComparisonStats:
        """
        Calcular estadísticas comparativas entre A y B.
        """
        win_id = _resolve_index_alias(win_id, window_index, "win_id", "window_index")
        measurement = _resolve_index_alias(
            measurement, measurement_index, "measurement", "measurement_index"
        )
        x, y, z, za, zb = self._align_grids(win_id, measurement)

        # Filtrar NaN
        valid = np.isfinite(za) & np.isfinite(zb)
        za_v = za[valid]
        zb_v = zb[valid]
        if za_v.size == 0:
            raise ValueError("No hay puntos válidos comunes entre A y B")
        diff = za_v - zb_v

        return ComparisonStats(
            n_points_a=self._td_a.n_points,
            n_points_b=self._td_b.n_points,
            n_points_common=int(np.sum(valid)),
            mean_a=float(np.mean(za_v)),
            std_a=float(np.std(za_v)),
            pv_a=float(np.ptp(za_v)),
            mean_b=float(np.mean(zb_v)),
            std_b=float(np.std(zb_v)),
            pv_b=float(np.ptp(zb_v)),
            mean_diff=float(np.mean(diff)),
            std_diff=float(np.std(diff)),
            pv_diff=float(np.ptp(diff)),
            rms_diff=float(np.sqrt(np.mean(diff ** 2))),
            max_abs_diff=float(np.max(np.abs(diff))),
            depth_mm_unit=self._depth_mm_unit,
            depth_axis_kind=self._depth_axis_kind,
        )

    # ── Perfiles ───────────────────────────────────────────────────────

    def profile_comparison(
        self,
        axis: str = "X",
        position: float = 0.0,
        win_id: Optional[int] = None,
        measurement: Optional[int] = None,
        window_index: Optional[int] = None,
        measurement_index: Optional[int] = None,
    ) -> Dict[str, np.ndarray]:
        """
        Comparar perfiles de A y B a una posición dada.

        Parameters
        ----------
        axis : "X" o "Y"
            Eje a lo largo del cual se extrae el perfil.
        position : float
            Posición fija en el otro eje [mm].

        Returns
        -------
        dict con keys: "pos_a", "z_a", "pos_b", "z_b"
        """
        win_id = _resolve_index_alias(win_id, window_index, "win_id", "window_index")
        measurement = _resolve_index_alias(
            measurement, measurement_index, "measurement", "measurement_index"
        )
        axis = axis.upper()
        if axis not in ("X", "Y"):
            raise ValueError("Eje debe ser 'X' o 'Y'")
        _validate_selection(self._td_a, win_id, measurement)
        _validate_selection(self._td_b, win_id, measurement)

        def _extract_line(source, td, ax, pos, win, meas):
            tolerances = _source_coordinate_tolerances(source)
            if ax == "X":
                y_u = _canonical_unique(td.Y, tolerance=tolerances["Y"])
                y_act = y_u[np.argmin(np.abs(y_u - pos))]
                mask = np.isclose(td.Y, y_act, atol=tolerances["Y"], rtol=0.0)
                pos_arr = td.X[mask]
            else:
                x_u = _canonical_unique(td.X, tolerance=tolerances["X"])
                x_act = x_u[np.argmin(np.abs(x_u - pos))]
                mask = np.isclose(td.X, x_act, atol=tolerances["X"], rtol=0.0)
                pos_arr = td.Y[mask]

            z_arr = td.depth_mm[mask, meas, win] if td.depth_mm is not None else np.zeros(mask.sum())
            sort = np.argsort(pos_arr)
            return pos_arr[sort], z_arr[sort]

        pos_a, z_a = _extract_line(self._source_a, self._td_a, axis, position, win_id, measurement)
        pos_b, z_b = _extract_line(self._source_b, self._td_b, axis, position, win_id, measurement)

        return {"pos_a": pos_a, "z_a": z_a, "pos_b": pos_b, "z_b": z_b}

    def __repr__(self) -> str:
        return f"ComparisonPair('{self._name_a}' vs '{self._name_b}')"


def _validate_selection(td: TransformData, win_id: int, measurement: int) -> None:
    if td.depth_mm is None or td.depth_mm.ndim != 3:
        raise ValueError("Los datos de comparación deben tener shape (punto, M, ventana)")
    if measurement < 0 or measurement >= td.depth_mm.shape[1]:
        raise IndexError(f"Medición fuera de rango: {measurement}")
    if win_id < 0 or win_id >= td.depth_mm.shape[2]:
        raise IndexError(f"Ventana fuera de rango: {win_id}")
