"""
extract.derived
Objeto derivado: resultado de una extracción.

Un DerivedObject es un subconjunto autocontenido de datos extraído
de un OCTDataset (posiblemente transformado). Contiene:
- Los datos extraídos (posiciones + picos).
- Proveniencia (de dónde salió y cómo).
- Clasificación propia (puede diferir del padre).

Los DerivedObjects pueden exportarse, re-transformarse, o
compararse entre sí.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class ExtractionType(Enum):
    """Tipo de extracción que generó el objeto."""
    PROFILE_X = auto()      # Perfil a Y fijo (variando X)
    PROFILE_Y = auto()      # Perfil a X fijo (variando Y)
    REGION = auto()          # Sub-región rectangular
    Z_SLICE = auto()         # Un nivel Z de un Multi-Z
    WINDOW = auto()          # Una ventana de un multi-ventana
    CUSTOM = auto()          # Extracción personalizada


@dataclass
class Provenance:
    """Historial de cómo se generó un DerivedObject."""
    source_file: str                    # Archivo original
    extraction_type: ExtractionType     # Tipo de extracción
    parameters: Dict[str, Any]          # Parámetros usados
    transforms_applied: List[str]       # Nombres de pasos del pipeline
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    parent_id: Optional[str] = None     # ID del objeto padre (si es encadenado)

    def summary(self) -> str:
        lines = [
            f"  Origen     : {self.source_file}",
            f"  Extracción : {self.extraction_type.name}",
            f"  Parámetros : {self.parameters}",
            f"  Fecha       : {self.timestamp}",
        ]
        if self.transforms_applied:
            lines.append(f"  Transforms : {' → '.join(self.transforms_applied)}")
        return "\n".join(lines)


class DerivedObject:
    """
    Objeto derivado de una extracción.

    Contiene datos autocontenidos (posiciones, OPD, amplitud)
    y metadata de proveniencia. Puede ser exportado o usado
    como input para comparaciones.

    Atributos
    ---------
    name : str
        Nombre descriptivo del objeto.
    X, Y, Z : ndarray
        Posiciones [mm].
    depth_mm : ndarray o None
        OPD extraído. Shape depende del tipo.
    amplitude : ndarray o None
        Amplitud extraída.
    provenance : Provenance
        De dónde salió.
    metadata : dict
        Metadata heredada del padre + info propia.
    """

    _counter = 0  # Para IDs únicos

    def __init__(
        self,
        name: str,
        X: np.ndarray,
        Y: np.ndarray,
        Z: np.ndarray,
        provenance: Provenance,
        depth_mm: Optional[np.ndarray] = None,
        amplitude: Optional[np.ndarray] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        DerivedObject._counter += 1
        self._id = f"derived_{DerivedObject._counter:04d}"

        self.name = name
        self.X = X
        self.Y = Y
        self.Z = Z
        self.depth_mm = depth_mm
        self.amplitude = amplitude
        self.provenance = provenance
        self.metadata = metadata or {}

    @property
    def id(self) -> str:
        return self._id

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
    def coordinate_tolerance_mm(self) -> float:
        """Tolerancia espacial heredada o declarada por el objeto."""
        return max(self.coordinate_tolerances_mm.values())

    @property
    def coordinate_tolerances_mm(self) -> Dict[str, float]:
        """Tolerancias espaciales por eje, heredadas o declaradas."""
        metadata = self.metadata
        scalar = metadata.get("position_tolerance_mm", 1e-9)
        try:
            scalar = max(float(scalar), 1e-9)
        except (TypeError, ValueError):
            scalar = 1e-9
        result = {}
        for axis in ("X", "Y", "Z"):
            value = metadata.get(f"position_tolerance_{axis.lower()}_mm", scalar)
            try:
                result[axis] = max(float(value), 1e-9)
            except (TypeError, ValueError):
                result[axis] = scalar
        return result

    @property
    def n_points(self) -> int:
        return len(self.X)

    @property
    def is_1d(self) -> bool:
        """Es un perfil (una sola dimensión varía significativamente)."""
        x_u = len(np.unique(np.round(self.X, 6)))
        y_u = len(np.unique(np.round(self.Y, 6)))
        return (x_u > 1 and y_u <= 1) or (y_u > 1 and x_u <= 1)

    @property
    def is_2d(self) -> bool:
        """Es una topografía (dos dimensiones varían)."""
        x_u = len(np.unique(np.round(self.X, 6)))
        y_u = len(np.unique(np.round(self.Y, 6)))
        return x_u > 1 and y_u > 1

    @property
    def x_range(self) -> Tuple[float, float]:
        return (float(self.X.min()), float(self.X.max()))

    @property
    def y_range(self) -> Tuple[float, float]:
        return (float(self.Y.min()), float(self.Y.max()))

    def profile_data(
        self, win_id: int = 0, measurement: int = 0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Retornar datos de perfil (posición, valor).

        Para PROFILE_X: retorna (X, depth_mm).
        Para PROFILE_Y: retorna (Y, depth_mm).
        """
        if self.depth_mm is None:
            raise ValueError("No hay datos de OPD")

        z = self.depth_mm[:, measurement, win_id]

        if self.provenance.extraction_type == ExtractionType.PROFILE_Y:
            sort_idx = np.argsort(self.Y)
            return self.Y[sort_idx], z[sort_idx]
        else:
            sort_idx = np.argsort(self.X)
            return self.X[sort_idx], z[sort_idx]

    def to_export_dict(self) -> Dict[str, Any]:
        """
        Convertir a un payload canónico Schema 6 compatible con el exporter.

        Se conserva el nombre histórico del método por compatibilidad de API,
        pero ya no genera una segunda representación persistente: Schema 6 es
        el único contrato de salida vigente del Workbench.
        """
        # Import local para evitar el ciclo extract → export → extract durante
        # la carga de módulos. La serialización canónica vive en exporter.py.
        from export.exporter import _resolve_to_data

        return _resolve_to_data(self)

    def summary(self) -> str:
        lines = [
            f"{'─' * 50}",
            f"  DerivedObject: {self.name}",
            f"  ID: {self._id}",
            f"{'─' * 50}",
            f"  Puntos  : {self.n_points}",
            f"  Tipo    : {'1D' if self.is_1d else '2D' if self.is_2d else 'otro'}",
            f"  X rango : [{self.x_range[0]:.4f}, {self.x_range[1]:.4f}] mm",
            f"  Y rango : [{self.y_range[0]:.4f}, {self.y_range[1]:.4f}] mm",
        ]

        if self.depth_mm is not None:
            z_valid = self.depth_mm[np.isfinite(self.depth_mm)]
            if len(z_valid) > 0:
                lines.append(f"  OPD     : [{z_valid.min():.6f}, {z_valid.max():.6f}] mm")
                lines.append(f"  OPD shape: {self.depth_mm.shape}")

        lines.append(f"\n  Proveniencia:")
        lines.append(self.provenance.summary())
        lines.append(f"{'─' * 50}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"DerivedObject('{self.name}', "
            f"{self.provenance.extraction_type.name}, "
            f"n={self.n_points})"
        )
