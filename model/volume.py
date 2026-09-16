"""Estructura genérica de niveles para mediciones 2D y 3D.

El dataset original permanece inmutable. ``VolumeLayout`` describe la geometría
observada y ``LevelSelection`` representa exclusiones reversibles para la vista.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

import numpy as np


def _cluster_axis(values: np.ndarray, tolerance_mm: float) -> Tuple[np.ndarray, Tuple[np.ndarray, ...]]:
    """Agrupar valores físicos cercanos y devolver centros e índices originales."""
    values = np.asarray(values, dtype=float).ravel()
    finite_indices = np.flatnonzero(np.isfinite(values))
    if finite_indices.size == 0:
        return np.array([], dtype=float), tuple()
    ordered = finite_indices[np.argsort(values[finite_indices], kind="stable")]
    groups = []
    current = [int(ordered[0])]
    for index in ordered[1:]:
        if abs(values[int(index)] - values[current[-1]]) <= tolerance_mm:
            current.append(int(index))
        else:
            groups.append(np.asarray(current, dtype=int))
            current = [int(index)]
    groups.append(np.asarray(current, dtype=int))
    centers = np.asarray([float(np.mean(values[group])) for group in groups], dtype=float)
    return centers, tuple(groups)


@dataclass(frozen=True)
class LevelInfo:
    """Descripción física y de puntos de un nivel Z."""

    index: int
    z_mm: float
    point_indices: np.ndarray
    x_unique: np.ndarray
    y_unique: np.ndarray

    @property
    def n_points(self) -> int:
        return int(self.point_indices.size)

    @property
    def nx(self) -> int:
        return int(self.x_unique.size)

    @property
    def ny(self) -> int:
        return int(self.y_unique.size)

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.nx, self.ny


@dataclass(frozen=True)
class VolumeLayout:
    """Layout común para una medición 2D (un nivel) o 3D (varios niveles)."""

    x_unique: np.ndarray
    y_unique: np.ndarray
    levels: Tuple[LevelInfo, ...]
    tolerance_mm: float

    @classmethod
    def from_coordinates(
        cls,
        x: Iterable[float],
        y: Iterable[float],
        z: Iterable[float],
        tolerance_mm: float = 1e-6,
        tolerance_x_mm: Optional[float] = None,
        tolerance_y_mm: Optional[float] = None,
        tolerance_z_mm: Optional[float] = None,
    ) -> "VolumeLayout":
        x = np.asarray(x, dtype=float).ravel()
        y = np.asarray(y, dtype=float).ravel()
        z = np.asarray(z, dtype=float).ravel()
        if not (x.size == y.size == z.size):
            raise ValueError("X, Y y Z deben tener la misma cantidad de puntos")
        tolerance_x_mm = tolerance_mm if tolerance_x_mm is None else tolerance_x_mm
        tolerance_y_mm = tolerance_mm if tolerance_y_mm is None else tolerance_y_mm
        tolerance_z_mm = tolerance_mm if tolerance_z_mm is None else tolerance_z_mm
        tolerances = (tolerance_x_mm, tolerance_y_mm, tolerance_z_mm)
        if any(float(value) <= 0 for value in tolerances):
            raise ValueError("las tolerancias deben ser positivas")

        x_unique, _ = _cluster_axis(x, tolerance_x_mm)
        y_unique, _ = _cluster_axis(y, tolerance_y_mm)
        z_unique, z_groups = _cluster_axis(z, tolerance_z_mm)

        levels = []
        for level_index, (z_mm, z_group) in enumerate(zip(z_unique, z_groups)):
            valid = z_group[np.isfinite(x[z_group]) & np.isfinite(y[z_group])]
            level_x, _ = _cluster_axis(x[valid], tolerance_x_mm)
            level_y, _ = _cluster_axis(y[valid], tolerance_y_mm)
            levels.append(
                LevelInfo(
                    index=level_index,
                    z_mm=float(z_mm),
                    point_indices=valid.copy(),
                    x_unique=level_x,
                    y_unique=level_y,
                )
            )

        nonfinite_z = np.flatnonzero(~np.isfinite(z))
        if nonfinite_z.size:
            valid = nonfinite_z[np.isfinite(x[nonfinite_z]) & np.isfinite(y[nonfinite_z])]
            if valid.size:
                level_x, _ = _cluster_axis(x[valid], tolerance_x_mm)
                level_y, _ = _cluster_axis(y[valid], tolerance_y_mm)
                levels.append(
                    LevelInfo(
                        index=len(levels),
                        z_mm=float("nan"),
                        point_indices=valid.copy(),
                        x_unique=level_x,
                        y_unique=level_y,
                    )
                )

        if not levels:
            raise ValueError("No hay puntos con coordenadas válidas para construir niveles")
        return cls(
            x_unique=x_unique,
            y_unique=y_unique,
            levels=tuple(levels),
            tolerance_mm=float(max(tolerances)),
        )

    @property
    def n_levels(self) -> int:
        return len(self.levels)

    @property
    def dimensions(self) -> tuple[int, int, int]:
        return self.x_unique.size, self.y_unique.size, self.n_levels

    @property
    def z_values_mm(self) -> np.ndarray:
        return np.asarray([level.z_mm for level in self.levels], dtype=float)

    def level_for_z(self, z_mm: float) -> LevelInfo:
        """Devolver el nivel físico más cercano a ``z_mm``."""
        if not np.isfinite(z_mm):
            raise ValueError("z_mm debe ser finito")
        finite = np.isfinite(self.z_values_mm)
        if not finite.any():
            raise ValueError("El layout no tiene niveles Z físicos")
        indices = np.flatnonzero(finite)
        return self.levels[int(indices[np.argmin(np.abs(self.z_values_mm[finite] - z_mm))])]


@dataclass(frozen=True)
class VolumeSlice:
    """Puntos de un plano ortogonal seleccionado físicamente."""

    orientation: str
    coordinate_mm: float
    horizontal_axis: str
    vertical_axis: str
    horizontal: np.ndarray
    vertical: np.ndarray
    values: np.ndarray
    point_indices: np.ndarray

    @property
    def n_points(self) -> int:
        return int(self.values.size)


def select_volume_slice(
    x: Iterable[float],
    y: Iterable[float],
    z: Iterable[float],
    values: Iterable[float],
    orientation: str,
    coordinate_mm: float | None = None,
    tolerance_mm: float = 1e-6,
) -> VolumeSlice:
    """Seleccionar un plano ``XY``, ``XZ`` o ``YZ`` sin regularizar la nube.

    ``values`` debe tener un valor por punto. La función conserva sólo los
    puntos del grupo físico más cercano a la coordenada solicitada y deja que
    la capa visual decida si los dibuja como nube o como grilla incompleta.
    """
    orientation = str(orientation).upper()
    if orientation not in {"XY", "XZ", "YZ"}:
        raise ValueError("orientation debe ser XY, XZ o YZ")
    if tolerance_mm <= 0:
        raise ValueError("tolerance_mm debe ser positiva")

    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()
    values = np.asarray(values).ravel()
    if not (x.size == y.size == z.size == values.size):
        raise ValueError("X, Y, Z y values deben tener la misma cantidad de puntos")

    layout = VolumeLayout.from_coordinates(x, y, z, tolerance_mm=tolerance_mm)
    if orientation == "XY":
        centers = layout.z_values_mm
        finite = np.isfinite(centers)
        if not finite.any():
            raise ValueError("No hay niveles Z físicos para seleccionar un plano XY")
        candidate = centers[finite][0] if coordinate_mm is None else float(coordinate_mm)
        if not np.isfinite(candidate):
            raise ValueError("coordinate_mm debe ser finito")
        level = layout.level_for_z(candidate)
        indices = level.point_indices
        return VolumeSlice(
            orientation="XY",
            coordinate_mm=level.z_mm,
            horizontal_axis="X",
            vertical_axis="Y",
            horizontal=x[indices],
            vertical=y[indices],
            values=values[indices],
            point_indices=indices.copy(),
        )

    coordinate_values = y if orientation == "XZ" else x
    centers, groups = _cluster_axis(coordinate_values, tolerance_mm)
    if not centers.size:
        raise ValueError(f"No hay coordenadas válidas para seleccionar un plano {orientation}")
    candidate = centers[0] if coordinate_mm is None else float(coordinate_mm)
    if not np.isfinite(candidate):
        raise ValueError("coordinate_mm debe ser finito")
    group_index = int(np.argmin(np.abs(centers - candidate)))
    indices = groups[group_index]
    if orientation == "XZ":
        horizontal_axis, vertical_axis = "X", "Z"
        horizontal, vertical = x[indices], z[indices]
    else:
        horizontal_axis, vertical_axis = "Y", "Z"
        horizontal, vertical = y[indices], z[indices]
    return VolumeSlice(
        orientation=orientation,
        coordinate_mm=float(centers[group_index]),
        horizontal_axis=horizontal_axis,
        vertical_axis=vertical_axis,
        horizontal=horizontal,
        vertical=vertical,
        values=values[indices],
        point_indices=indices.copy(),
    )


@dataclass(frozen=True)
class LevelSelection:
    """Selección inmutable de niveles activos y niveles excluidos."""

    layout: VolumeLayout
    _excluded: frozenset[int] = frozenset()

    @property
    def excluded_indices(self) -> tuple[int, ...]:
        return tuple(sorted(self._excluded))

    @property
    def active_indices(self) -> tuple[int, ...]:
        return tuple(level.index for level in self.layout.levels if level.index not in self._excluded)

    @property
    def active_levels(self) -> tuple[LevelInfo, ...]:
        return tuple(self.layout.levels[index] for index in self.active_indices)

    def exclude(self, level_index: int) -> "LevelSelection":
        self._validate_index(level_index)
        return LevelSelection(self.layout, self._excluded | {int(level_index)})

    def restore(self, level_index: int) -> "LevelSelection":
        self._validate_index(level_index)
        return LevelSelection(self.layout, self._excluded - {int(level_index)})

    def _validate_index(self, level_index: int) -> None:
        if not 0 <= int(level_index) < self.layout.n_levels:
            raise IndexError(f"Nivel fuera de rango: {level_index}")
