"""
transforms.base
Sistema de transformaciones no destructivas.

Cada Transform opera sobre arrays (posiciones + datos) y retorna
copias modificadas. El TransformPipeline apila transformaciones
y las aplica en orden. TransformedView envuelve un OCTDataset
original y expone los datos transformados.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from model.dataset import _canonical_unique, _nearest_index


# ── Contenedor de datos transformables ─────────────────────────────────────

@dataclass
class TransformData:
    """
    Contenedor con los arrays que las transformaciones modifican.

    Es una copia de trabajo — el OCTDataset original nunca se toca.
    """
    X: np.ndarray                          # Posiciones X [mm]
    Y: np.ndarray                          # Posiciones Y [mm]
    Z: np.ndarray                          # Posiciones Z motor [mm]
    coordinate_tolerance_mm: float = 0.002
    coordinate_tolerances_mm: Optional[Dict[str, float]] = None
    depth_mm: Optional[np.ndarray] = None       # (n_pts, M, N_win)
    amplitude: Optional[np.ndarray] = None # (n_pts, M, N_win)
    spectra: Optional[np.ndarray] = None   # (n_pts, M, K) or (n_pts, K)
    profiles: Optional[Dict[int, np.ndarray]] = None
    profile_depth_axes_m: Optional[Dict[int, np.ndarray]] = None
    mask: Optional[np.ndarray] = None      # (n_pts,) bool — True = válido
    units: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: List[Dict[str, Any]] = field(default_factory=list)

    def copy(self) -> TransformData:
        """Copia profunda de todos los arrays."""
        return TransformData(
            X=self.X.copy(),
            Y=self.Y.copy(),
            Z=self.Z.copy(),
            coordinate_tolerance_mm=self.coordinate_tolerance_mm,
            coordinate_tolerances_mm=copy.deepcopy(self.coordinate_tolerances_mm),
            depth_mm=self.depth_mm.copy() if self.depth_mm is not None else None,
            amplitude=self.amplitude.copy() if self.amplitude is not None else None,
            spectra=self.spectra.copy() if self.spectra is not None else None,
            profiles={key: value.copy() for key, value in self.profiles.items()} if self.profiles is not None else None,
            profile_depth_axes_m={key: value.copy() for key, value in self.profile_depth_axes_m.items()} if self.profile_depth_axes_m is not None else None,
            mask=self.mask.copy() if self.mask is not None else None,
            units=copy.deepcopy(self.units),
            metadata=copy.deepcopy(self.metadata),
            provenance=copy.deepcopy(self.provenance),
        )

    @property
    def n_points(self) -> int:
        return len(self.X)

    @property
    def x_mm(self) -> np.ndarray:
        """Alias nominal explícito para la coordenada X en mm."""
        return self.X

    @property
    def y_mm(self) -> np.ndarray:
        """Alias nominal explícito para la coordenada Y en mm."""
        return self.Y

    @property
    def z_mm(self) -> np.ndarray:
        """Alias nominal explícito para la coordenada Z en mm."""
        return self.Z

    @property
    def coordinate_valid_mask(self) -> np.ndarray:
        """Máscara booleana por punto para coordenadas finitas."""
        return np.isfinite(self.X) & np.isfinite(self.Y) & np.isfinite(self.Z)

    @staticmethod
    def _channel_valid_mask(channel: Optional[np.ndarray]) -> Optional[np.ndarray]:
        if channel is None:
            return None
        values = np.asarray(channel)
        if values.ndim <= 1:
            return np.isfinite(values)
        return np.all(np.isfinite(values), axis=tuple(range(1, values.ndim)))

    @property
    def depth_mm_valid_mask(self) -> Optional[np.ndarray]:
        """Máscara booleana por punto para valores OPD finitos."""
        return self._channel_valid_mask(self.depth_mm)

    @property
    def amplitude_valid_mask(self) -> Optional[np.ndarray]:
        """Máscara booleana por punto para amplitudes finitas."""
        return self._channel_valid_mask(self.amplitude)

    @property
    def valid_mask(self) -> Optional[np.ndarray]:
        """Máscara explícita del pipeline; no se confunde con conteos derivados."""
        return self.mask

    def profile_depth_axis_m(self, window_index: int) -> Optional[np.ndarray]:
        """Obtener la copia del eje axial individual de una ventana."""
        if self.profile_depth_axes_m is None:
            return None
        axis = self.profile_depth_axes_m.get(int(window_index))
        return None if axis is None else axis.copy()

    def apply_mask(self) -> TransformData:
        """
        Aplicar máscara: eliminar puntos donde mask == False.
        Retorna nuevo TransformData sin máscara.
        """
        if self.mask is None or np.all(self.mask):
            return self

        m = self.mask
        return TransformData(
            X=self.X[m],
            Y=self.Y[m],
            Z=self.Z[m],
            coordinate_tolerance_mm=self.coordinate_tolerance_mm,
            coordinate_tolerances_mm=copy.deepcopy(self.coordinate_tolerances_mm),
            depth_mm=self.depth_mm[m] if self.depth_mm is not None else None,
            amplitude=self.amplitude[m] if self.amplitude is not None else None,
            spectra=self.spectra[m] if self.spectra is not None else None,
            profiles={key: value[m] for key, value in self.profiles.items()} if self.profiles is not None else None,
            profile_depth_axes_m={key: value.copy() for key, value in self.profile_depth_axes_m.items()} if self.profile_depth_axes_m is not None else None,
            mask=None,
            units=copy.deepcopy(self.units),
            metadata=copy.deepcopy(self.metadata),
            provenance=copy.deepcopy(self.provenance),
        )


# ── Transform base ────────────────────────────────────────────────────────

class Transform(ABC):
    """
    Clase base para todas las transformaciones.

    Cada subclase implementa apply() que recibe un TransformData
    y retorna uno nuevo (modificado). El original no se toca.
    """

    @abstractmethod
    def apply(self, data: TransformData) -> TransformData:
        """Aplicar la transformación y retornar datos nuevos."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre corto para display."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Descripción legible de lo que hace."""
        ...

    def cancellation_key(self):
        """Clave para transformaciones consecutivas que se cancelan."""
        return None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.description})"


# ── Pipeline ───────────────────────────────────────────────────────────────

class TransformPipeline:
    """
    Pipeline ordenado de transformaciones.

    Aplica las transformaciones en secuencia sobre una copia de los
    datos originales. Soporta undo (quitar la última), clear, y
    acceso por índice.
    """

    def __init__(self) -> None:
        self._transforms: List[Transform] = []

    def add(self, transform: Transform) -> None:
        """Agregar una transformación al final del pipeline.

        Las transformaciones consecutivas con la misma clave de cancelación
        se eliminan por pares, manteniendo el historial como estado neto.
        """
        cancellation_key = transform.cancellation_key()
        if cancellation_key is not None and self._transforms:
            previous = self._transforms[-1]
            if previous.cancellation_key() == cancellation_key:
                self._transforms.pop()
                return
        self._transforms.append(transform)

    def remove(self, index: int) -> Transform:
        """Quitar una transformación por índice."""
        return self._transforms.pop(index)

    def undo(self) -> Optional[Transform]:
        """Quitar la última transformación. Retorna la removida o None."""
        if self._transforms:
            return self._transforms.pop()
        return None

    def rewind_to(self, index: int) -> List[Transform]:
        """Conservar el paso ``index`` y quitar todos los pasos posteriores."""
        index = int(index)
        if index < 0 or index >= len(self._transforms):
            raise IndexError(f"Índice de historial inválido: {index}")
        removed = self._transforms[index + 1 :]
        del self._transforms[index + 1 :]
        return removed

    def clear(self) -> None:
        """Limpiar todo el pipeline."""
        self._transforms.clear()

    def apply(self, data: TransformData) -> TransformData:
        """
        Aplicar todas las transformaciones en orden.
        Recibe datos originales, retorna datos transformados.
        """
        result = data.copy()
        for t in self._transforms:
            result = t.apply(result)
            result.provenance.append({
                "name": t.name,
                "description": t.description,
            })
        return result

    @property
    def steps(self) -> List[Transform]:
        """Lista de transformaciones (read-only)."""
        return list(self._transforms)

    @property
    def is_empty(self) -> bool:
        return len(self._transforms) == 0

    def __len__(self) -> int:
        return len(self._transforms)

    def __repr__(self) -> str:
        if not self._transforms:
            return "TransformPipeline(vacío)"
        items = ", ".join(t.name for t in self._transforms)
        return f"TransformPipeline([{items}])"

    def summary(self) -> str:
        """Resumen legible del pipeline."""
        if not self._transforms:
            return "  Pipeline vacío (datos originales)"
        lines = [f"  Pipeline ({len(self._transforms)} pasos):"]
        for i, t in enumerate(self._transforms):
            lines.append(f"    {i + 1}. {t.name}: {t.description}")
        return "\n".join(lines)


# ── TransformedView ────────────────────────────────────────────────────────

class TransformedView:
    """
    Vista transformada de un OCTDataset.

    Envuelve el dataset original y un pipeline de transformaciones.
    Los datos transformados se recalculan cada vez que se pide
    (lazy, no cachea). El dataset original nunca se modifica.

    Uso típico:
        ds = OCTDataset.from_file("scan.npz")
        view = TransformedView(ds)
        registry = discover_plugin_tree("transforms")
        view.pipeline.add(registry.create("invert_axis", {"axis": "Z"}))
        view.pipeline.add(registry.create("level_plane", {"win_id": 0, "measurement": 0}))
        view.pipeline.add(registry.create("crop_region", {"x_min": "0.1", "x_max": "0.8"}))

        # Acceder a datos transformados
        tdata = view.transformed_data
        xg, yg, zg = view.topography_grid()
    """

    def __init__(self, dataset) -> None:
        """
        Parameters
        ----------
        dataset : OCTDataset
            Dataset original (nunca se modifica).
        """
        self._dataset = dataset
        self._pipeline = TransformPipeline()
        self._cache = None  # Se invalida al modificar el pipeline

    @property
    def dataset(self):
        """Dataset original (read-only)."""
        return self._dataset

    @property
    def pipeline(self) -> TransformPipeline:
        """Pipeline de transformaciones."""
        return self._pipeline

    def _original_data(self) -> TransformData:
        """Crear TransformData desde el dataset original."""
        ds = self._dataset
        return TransformData(
            X=ds.X.copy(),
            Y=ds.Y.copy(),
            Z=ds.Z.copy(),
            coordinate_tolerance_mm=ds.coordinate_tolerance_mm,
            coordinate_tolerances_mm=ds.coordinate_tolerances_mm,
            depth_mm=ds.depth_mm.copy() if ds.has_peaks else None,
            amplitude=ds.amplitude.copy() if ds.has_peaks else None,
            spectra=ds.spectra,
            profiles=ds.profiles,
            profile_depth_axes_m=ds.profile_depth_axes_m,
            mask=None,
            units=copy.deepcopy(ds.metadata.get("units", {})),
            metadata=ds.metadata,
        )

    @property
    def transformed_data(self) -> TransformData:
        """Datos con todas las transformaciones aplicadas."""
        original = self._original_data()
        if self._pipeline.is_empty:
            return original
        return self._pipeline.apply(original)

    def topography_grid(
        self, win_id: int = 0, measurement: int = 0
    ):
        """
        Reconstruir grilla 2D de topografía desde datos transformados.

        Returns
        -------
        x_grid, y_grid, z_grid : ndarray (ny, nx)
        """
        td = self.transformed_data

        if td.depth_mm is None:
            raise ValueError("No hay datos de OPD")

        # Aplicar máscara si existe
        td = td.apply_mask()

        if not 0 <= measurement < td.depth_mm.shape[1]:
            raise IndexError(f"Medición fuera de rango: {measurement}")
        if not 0 <= win_id < td.depth_mm.shape[2]:
            raise IndexError(f"Ventana fuera de rango: {win_id}")

        tolerances = self._dataset.coordinate_tolerances_mm
        x_tolerance = tolerances["X"]
        y_tolerance = tolerances["Y"]
        x_sorted = _canonical_unique(td.X, tolerance=x_tolerance)
        y_sorted = _canonical_unique(td.Y, tolerance=y_tolerance)
        nx, ny = len(x_sorted), len(y_sorted)

        x_grid, y_grid = np.meshgrid(x_sorted, y_sorted)
        z_grid = np.full((ny, nx), np.nan)
        z_vals = td.depth_mm[:, measurement, win_id]
        occupied = set()

        for idx in range(td.n_points):
            if not np.isfinite(td.X[idx]) or not np.isfinite(td.Y[idx]):
                continue
            xi = _nearest_index(x_sorted, td.X[idx])
            yi = _nearest_index(y_sorted, td.Y[idx])
            if (
                0 <= xi < nx
                and 0 <= yi < ny
                and abs(x_sorted[xi] - td.X[idx]) <= x_tolerance
                and abs(y_sorted[yi] - td.Y[idx]) <= y_tolerance
            ):
                if (xi, yi) in occupied:
                    raise ValueError(
                        "La grilla contiene coordenadas X/Y duplicadas; "
                        "no es una topografía 2D única"
                    )
                occupied.add((xi, yi))
                z_grid[yi, xi] = z_vals[idx]

        return x_grid, y_grid, z_grid

    def profile_1d(
        self, win_id: int = 0, measurement: int = 0
    ):
        """
        Extraer perfil 1D desde datos transformados.

        Returns
        -------
        x, z : ndarray (n_pts,)
        """
        td = self.transformed_data
        td = td.apply_mask()

        if td.depth_mm is None:
            raise ValueError("No hay datos de OPD")

        z_vals = td.depth_mm[:, measurement, win_id]

        # Ordenar por X
        sort_idx = np.argsort(td.X)
        return td.X[sort_idx], z_vals[sort_idx]

    @property
    def X(self):
        return self.transformed_data.X

    @property
    def Y(self):
        return self.transformed_data.Y

    @property
    def Z(self):
        return self.transformed_data.Z

    @property
    def depth_mm(self):
        return self.transformed_data.depth_mm

    @property
    def amplitude(self):
        return self.transformed_data.amplitude

    @property
    def affected_points(self) -> int:
        """Cantidad de puntos con al menos una celda inválida."""
        depth_mm = self.depth_mm
        if depth_mm is None:
            return 0
        return int(np.count_nonzero(np.any(~np.isfinite(depth_mm), axis=tuple(range(1, depth_mm.ndim)))))

    @property
    def invalid_cells(self) -> int:
        depth_mm = self.depth_mm
        return 0 if depth_mm is None else int(np.count_nonzero(~np.isfinite(depth_mm)))

    @property
    def offset_mm(self) -> float:
        total = 0.0
        for step in self.pipeline.steps:
            axis = getattr(step, "_axis", None)
            if axis == "DEPTH":
                total += float(getattr(step, "_value", 0.0))
                continue
            spec = getattr(step, "spec", None)
            plugin_id = getattr(spec, "id", None)
            if plugin_id == "offset_depth":
                total += float(getattr(step, "parameters", {}).get("offset_mm", 0.0))
            elif plugin_id == "offset_minimum_to_zero":
                total += float(getattr(step, "offset_mm", 0.0))
        return total

    @property
    def parameters(self) -> dict:
        return {
            "steps": [
                {
                    "name": step.name,
                    "description": step.description,
                    "parameters": getattr(step, "parameters", {}),
                }
                for step in self.pipeline.steps
            ]
        }

    def __getattr__(self, name):
        # Metadata y atributos estructurales siguen perteneciendo al dataset.
        return getattr(self._dataset, name)

    def __repr__(self) -> str:
        return (
            f"TransformedView({self._dataset.filename}, "
            f"pipeline={len(self._pipeline)} pasos)"
        )
