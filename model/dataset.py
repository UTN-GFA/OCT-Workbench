"""
model.dataset
Modelo de datos OCT inmutable con clasificación automática.

OCTDataset es la representación en memoria de un archivo OCT.
Los datos originales nunca se modifican; las transformaciones
generan vistas nuevas (ver módulo transforms).
"""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from model.volume import VolumeLayout


# ── Clasificación del dataset ──────────────────────────────────────────────

class DatasetType(Enum):
    """Tipo de medición detectado automáticamente."""
    SINGLE_POINT = auto()    # Un solo punto de medición
    PROFILE_1D   = auto()    # Barrido lineal (1 eje varía)
    TOPOGRAPHY   = auto()    # Barrido XY a Z fijo
    MULTI_Z      = auto()    # Barrido XY a múltiples Z (stack de foco)
    VOLUME       = auto()    # Tomografía volumétrica (con perfiles axiales)
    UNKNOWN      = auto()


# ── Metadata estructurada ──────────────────────────────────────────────────

@dataclass(frozen=True)
class Optics:
    """Parámetros ópticos del sistema."""
    fiber_diameter_um: Optional[float] = None   # Diámetro de fibra [µm]
    wavelength_nm: Optional[float] = None       # Longitud de onda central [nm]
    collimator_focal_length_mm: Optional[float] = None  # Focal del colimador [mm]
    objective_focal_length_mm: Optional[float] = None   # Focal del objetivo [mm]

    # Aliases de compatibilidad con el contrato histórico del Workbench.
    @property
    def d_fiber_um(self) -> Optional[float]:
        return self.fiber_diameter_um

    @property
    def wl_nm(self) -> Optional[float]:
        return self.wavelength_nm

    @property
    def f_col_mm(self) -> Optional[float]:
        return self.collimator_focal_length_mm

    @property
    def f_obj_mm(self) -> Optional[float]:
        return self.objective_focal_length_mm

    @property
    def na(self) -> Optional[float]:
        """Apertura numérica estimada (si hay datos suficientes)."""
        if (
            self.fiber_diameter_um
            and self.collimator_focal_length_mm
            and self.objective_focal_length_mm
        ):
            w_col = self.fiber_diameter_um * 1e-3 * self.collimator_focal_length_mm
            return w_col / (2 * self.objective_focal_length_mm)
        return None

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> Optics:
        if not d:
            return cls()
        return cls(
            fiber_diameter_um=d.get("fiber_diameter_um", d.get("d_fiber_um")),
            wavelength_nm=d.get("wavelength_nm", d.get("wl_nm")),
            collimator_focal_length_mm=d.get(
                "collimator_focal_length_mm", d.get("f_col_mm")
            ),
            objective_focal_length_mm=d.get(
                "objective_focal_length_mm", d.get("f_obj_mm")
            ),
        )


@dataclass(frozen=True, init=False)
class WindowConfig:
    """Configuración de una ventana de OPD."""
    win_id: int
    z_min:  float   # mm
    z_max:  float   # mm

    def __init__(
        self,
        win_id: Optional[int] = None,
        z_min: Optional[float] = None,
        z_max: Optional[float] = None,
        *,
        window_index: Optional[int] = None,
        depth_min_mm: Optional[float] = None,
        depth_max_mm: Optional[float] = None,
    ) -> None:
        if win_id is not None and window_index is not None and int(win_id) != int(window_index):
            raise ValueError("win_id y window_index no pueden diferir")
        if z_min is not None and depth_min_mm is not None and not np.isclose(z_min, depth_min_mm):
            raise ValueError("z_min y depth_min_mm no pueden diferir")
        if z_max is not None and depth_max_mm is not None and not np.isclose(z_max, depth_max_mm):
            raise ValueError("z_max y depth_max_mm no pueden diferir")
        resolved_window = window_index if window_index is not None else win_id
        resolved_min = depth_min_mm if depth_min_mm is not None else z_min
        resolved_max = depth_max_mm if depth_max_mm is not None else z_max
        if resolved_window is None or resolved_min is None or resolved_max is None:
            raise TypeError("WindowConfig requiere índice y límites de ventana")
        object.__setattr__(self, "win_id", int(resolved_window))
        object.__setattr__(self, "z_min", float(resolved_min))
        object.__setattr__(self, "z_max", float(resolved_max))

    @property
    def span(self) -> float:
        """Rango de la ventana [mm]."""
        return self.z_max - self.z_min

    @property
    def window_index(self) -> int:
        """Alias nominal para el índice 0-based de ventana."""
        return self.win_id

    @property
    def depth_min_mm(self) -> float:
        """Límite inferior de la ventana normalizado en mm."""
        return self.z_min

    @property
    def depth_max_mm(self) -> float:
        """Límite superior de la ventana normalizado en mm."""
        return self.z_max

    @property
    def depth_min_m(self) -> float:
        """Límite inferior expresado en metros para la capa de procesamiento."""
        return self.z_min / 1000.0

    @property
    def depth_max_m(self) -> float:
        """Límite superior expresado en metros para la capa de procesamiento."""
        return self.z_max / 1000.0


@dataclass(frozen=True)
class ScanGrid:
    """Información de la grilla del barrido."""
    n_points:  int           # Puntos totales adquiridos
    x_unique:  np.ndarray    # Valores únicos de X [mm]
    y_unique:  np.ndarray    # Valores únicos de Y [mm]
    z_unique:  np.ndarray    # Valores únicos de Z [mm]
    nx: int                  # Cantidad de posiciones en X
    ny: int                  # Cantidad de posiciones en Y
    nz: int                  # Cantidad de posiciones en Z

    @property
    def x_unique_mm(self) -> np.ndarray:
        return self.x_unique

    @property
    def y_unique_mm(self) -> np.ndarray:
        return self.y_unique

    @property
    def z_unique_mm(self) -> np.ndarray:
        return self.z_unique

    @property
    def x_range(self) -> Tuple[float, float]:
        return (float(self.x_unique.min()), float(self.x_unique.max()))

    @property
    def y_range(self) -> Tuple[float, float]:
        return (float(self.y_unique.min()), float(self.y_unique.max()))

    @property
    def z_range(self) -> Tuple[float, float]:
        return (float(self.z_unique.min()), float(self.z_unique.max()))

    @property
    def x_step(self) -> Optional[float]:
        """Paso mediano en X [mm], ignorando coordenadas no finitas."""
        return _robust_step(self.x_unique)

    @property
    def y_step(self) -> Optional[float]:
        """Paso mediano en Y [mm], ignorando coordenadas no finitas."""
        return _robust_step(self.y_unique)

    @property
    def z_step(self) -> Optional[float]:
        """Paso mediano en Z [mm], ignorando coordenadas no finitas."""
        return _robust_step(self.z_unique)

    @property
    def x_range_mm(self) -> Tuple[float, float]:
        return self.x_range

    @property
    def y_range_mm(self) -> Tuple[float, float]:
        return self.y_range

    @property
    def z_range_mm(self) -> Tuple[float, float]:
        return self.z_range

    @property
    def x_step_mm(self) -> Optional[float]:
        return self.x_step

    @property
    def y_step_mm(self) -> Optional[float]:
        return self.y_step

    @property
    def z_step_mm(self) -> Optional[float]:
        return self.z_step


# ── Dataset principal ──────────────────────────────────────────────────────

def _copy_peaks(peaks):
    if peaks is None:
        return None
    return {key: np.asarray(value).copy() for key, value in peaks.items()}


def _copy_profiles(profiles):
    if profiles is None:
        return None
    return {int(key): np.asarray(value).copy() for key, value in profiles.items()}


def _copy_profile_axes(axes):
    if axes is None:
        return None
    return {int(key): np.asarray(value, dtype=float).copy() for key, value in axes.items()}


class OCTDataset:
    """
    Representación inmutable de un archivo OCT.

    Atributos principales
    ---------------------
    filepath : str
        Ruta absoluta del archivo.
    format : str
        "npz" o "h5".
    metadata : dict
        Metadata normalizada del archivo.
    grid : ScanGrid
        Información de la grilla del barrido.
    optics : Optics
        Parámetros ópticos.
    windows : list[WindowConfig]
        Ventanas de OPD configuradas.
    dataset_type : DatasetType
        Clasificación automática de la medición.

    Datos (acceso directo, read-only via property)
    -----------------------------------------------
    X, Y, Z : ndarray — posiciones del barrido [mm]
    wavelengths : ndarray — calibración espectral [nm]
    depth_mm : ndarray o None — OPD de picos (n_pts, M, N_win)
    amplitude : ndarray o None — amplitud de picos
    spectra : ndarray o None — espectros crudos
    profiles : dict o None — perfiles axiales por ventana
    """

    def __init__(self, raw: Dict[str, Any]) -> None:
        """
        Construir desde el dict que retorna io.loader.load().

        No llamar directamente — usar OCTDataset.from_file().
        """
        self._raw = raw
        self._filepath = raw["filepath"]
        self._format = raw["format"]
        self._metadata = deepcopy(raw["metadata"])
        self._coordinate_tolerances = _metadata_coordinate_tolerances(self._metadata)
        # Compatibilidad pública histórica: conserva una tolerancia escalar.
        self._coordinate_tolerance = max(self._coordinate_tolerances.values())

        # Posiciones: copias defensivas para mantener el dataset inmutable.
        self._X = np.asarray(raw["positions"]["X"], dtype=float).copy()
        self._Y = np.asarray(raw["positions"]["Y"], dtype=float).copy()
        self._Z = np.asarray(raw["positions"]["Z"], dtype=float).copy()

        # Datos
        self._wavelengths = (
            np.asarray(raw["wavelengths"], dtype=float).copy()
            if raw["wavelengths"] is not None else None
        )
        self._peaks = _copy_peaks(raw["peaks"])
        self._spectra = (
            np.asarray(raw["spectra"]).copy()
            if raw["spectra"] is not None else None
        )
        self._profiles = _copy_profiles(raw.get("profiles"))
        self._profile_depth_axes_m = _copy_profile_axes(raw.get("profile_depth_axes_m"))

        # Ventanas
        self._windows = self._build_windows(raw["windows"])

        # Grilla
        self._grid = self._build_grid()
        self._volume_layout = VolumeLayout.from_coordinates(
            self._X,
            self._Y,
            self._Z,
            tolerance_mm=self._coordinate_tolerance,
            tolerance_x_mm=self._coordinate_tolerances["X"],
            tolerance_y_mm=self._coordinate_tolerances["Y"],
            tolerance_z_mm=self._coordinate_tolerances["Z"],
        )

        # Óptica
        self._optics = Optics.from_dict(self._metadata.get("optics"))

        # Clasificación
        self._dataset_type = self._classify()

    # ── Constructores ──────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, filepath: str) -> OCTDataset:
        """Cargar un archivo OCT y crear el dataset."""
        from work_io.loader import load
        raw = load(filepath)
        return cls(raw)

    # ── Properties (read-only) ─────────────────────────────────────────────

    @property
    def filepath(self) -> str:
        return self._filepath

    @property
    def filename(self) -> str:
        return os.path.basename(self._filepath)

    @property
    def format(self) -> str:
        return self._format

    @property
    def metadata(self) -> dict:
        """Metadata aislada; modificarla no muta el dataset."""
        return deepcopy(self._metadata)

    @property
    def grid(self) -> ScanGrid:
        return self._grid

    @property
    def volume_layout(self) -> VolumeLayout:
        """Estructura física de niveles para navegación 2D/3D."""
        return self._volume_layout

    @property
    def optics(self) -> Optics:
        return self._optics

    @property
    def windows(self) -> List[WindowConfig]:
        return list(self._windows)

    @property
    def dataset_type(self) -> DatasetType:
        return self._dataset_type

    @property
    def coordinate_tolerance_mm(self) -> float:
        """Tolerancia física usada para agrupar posiciones equivalentes."""
        return self._coordinate_tolerance

    @property
    def coordinate_tolerances_mm(self) -> Dict[str, float]:
        """Tolerancias físicas por eje, en mm."""
        return dict(self._coordinate_tolerances)

    @property
    def position_tolerance_x_mm(self) -> float:
        return float(self._coordinate_tolerances["X"])

    @property
    def position_tolerance_y_mm(self) -> float:
        return float(self._coordinate_tolerances["Y"])

    @property
    def position_tolerance_z_mm(self) -> float:
        return float(self._coordinate_tolerances["Z"])

    @property
    def X(self) -> np.ndarray:
        return self._X.copy()

    @property
    def Y(self) -> np.ndarray:
        return self._Y.copy()

    @property
    def Z(self) -> np.ndarray:
        return self._Z.copy()

    # Nombres canónicos de OCT_Static_Software para coordenadas espaciales.
    # X/Y/Z quedan como aliases públicos históricos del Workbench.
    @property
    def x_mm(self) -> np.ndarray:
        return self._X.copy()

    @property
    def y_mm(self) -> np.ndarray:
        return self._Y.copy()

    @property
    def z_mm(self) -> np.ndarray:
        return self._Z.copy()

    @property
    def wavelengths(self) -> Optional[np.ndarray]:
        return self._wavelengths.copy() if self._wavelengths is not None else None

    @property
    def depth_mm(self) -> Optional[np.ndarray]:
        return self._peaks["depth_mm"].copy() if self._peaks else None

    @property
    def amplitude(self) -> Optional[np.ndarray]:
        return self._peaks["amplitude"].copy() if self._peaks else None

    @property
    def spectra(self) -> Optional[np.ndarray]:
        return self._spectra.copy() if self._spectra is not None else None

    @property
    def profiles(self) -> Optional[Dict[int, np.ndarray]]:
        return _copy_profiles(self._profiles)

    @property
    def profile_depth_axes_m(self) -> Optional[Dict[int, np.ndarray]]:
        """Ejes axiales físicos persistidos por ventana, en metros."""
        return _copy_profile_axes(self._profile_depth_axes_m)

    @property
    def depth_axis_kind(self) -> str:
        return str(self._metadata.get("depth_axis_kind", "physical_depth_mm"))

    @property
    def is_physical_depth(self) -> bool:
        """Indicar si el eje representa profundidad física."""
        return self.depth_axis_kind in {"physical_depth", "physical_depth_mm"}

    @property
    def physical_depth_mm(self) -> Optional[np.ndarray]:
        """Profundidad física en mm."""
        return self.depth_mm

    @property
    def depth_m(self) -> Optional[np.ndarray]:
        """Profundidad física en metros, si el eje fue declarado físico."""
        depth = self.physical_depth_mm
        return None if depth is None else depth / 1000.0


    @property
    def n_points(self) -> int:
        return len(self._X)

    @property
    def measurements_per_point(self) -> int:
        """Cantidad de mediciones M por punto, con nombre canónico Static."""
        return int(
            self._metadata.get(
                "measurements_per_point", self._metadata.get("m_measurements", 1)
            )
        )

    @property
    def m_measurements(self) -> int:
        """Alias histórico de :attr:`measurements_per_point`."""
        return self.measurements_per_point

    @property
    def planned_points(self) -> Optional[int]:
        """Puntos planificados declarados por la adquisición, si existen."""
        return _optional_int(
            self._metadata.get("planned_points", self._metadata.get("n_points_total"))
        )

    @property
    def acquired_points(self) -> Optional[int]:
        """Puntos adquiridos declarados por la adquisición, si existen."""
        return _optional_int(
            self._metadata.get(
                "acquired_points", self._metadata.get("n_points_acquired")
            )
        )

    @property
    def duration_s(self) -> Optional[float]:
        """Duración del scan en segundos, con nombre canónico Static."""
        value = self._metadata.get("duration_s", self._metadata.get("duration_sec"))
        return None if value is None else float(value)

    @property
    def spectral_samples(self) -> Optional[int]:
        """Cantidad de muestras espectrales declaradas o inferidas."""
        value = self._metadata.get("k_samples")
        if value is None and self._spectra is not None and self._spectra.ndim:
            value = self._spectra.shape[-1]
        return _optional_int(value)

    @property
    def profile_samples(self) -> Optional[int]:
        """Cantidad de muestras de perfiles declarada por la adquisición."""
        return _optional_int(
            self._metadata.get("profile_samples", self._metadata.get("global_profile_samples"))
        )

    @property
    def scan_aborted(self) -> bool:
        """Estado de aborto de adquisición con nombre explícito."""
        return bool(self._metadata.get("aborted", False))

    @property
    def n_windows(self) -> int:
        return len(self._windows)

    @property
    def sample_name(self) -> str:
        return str(self._metadata.get("sample_name", ""))

    # ── Datos disponibles ──────────────────────────────────────────────────

    @property
    def has_peaks(self) -> bool:
        return self._peaks is not None

    @property
    def has_spectra(self) -> bool:
        return self._spectra is not None

    @property
    def has_profiles(self) -> bool:
        return self._profiles is not None

    @property
    def has_wavelengths(self) -> bool:
        return self._wavelengths is not None

    # ── Inspección ─────────────────────────────────────────────────────────

    def summary(self) -> str:
        """Generar un resumen legible del dataset."""
        lines = []
        lines.append(f"{'═' * 60}")
        lines.append(f"  OCT Dataset: {self.filename}")
        lines.append(f"{'═' * 60}")

        # Identificación
        lines.append(f"  Archivo   : {self._filepath}")
        lines.append(f"  Formato   : {self._format.upper()}")
        lines.append(f"  Schema    : {self._metadata.get('schema_version', '?')}")
        lines.append(f"  Software  : {self._metadata.get('software_version', '?')}")
        if self.sample_name:
            lines.append(f"  Muestra   : {self.sample_name}")

        # Tipo de medición
        lines.append(f"")
        lines.append(f"  Tipo      : {self._dataset_type.name}")

        # Temporal
        lines.append(f"")
        t_start = self._metadata.get("start_time", "")
        t_dur = self._metadata.get("duration_sec", 0)
        aborted = self._metadata.get("aborted", False)
        if t_start:
            lines.append(f"  Inicio    : {t_start}")
        if t_dur:
            mins = t_dur / 60
            lines.append(f"  Duración  : {t_dur:.1f} s ({mins:.1f} min)")
        if aborted:
            lines.append(f"  ⚠ SCAN ABORTADO")

        # Grilla
        lines.append(f"")
        g = self._grid
        lines.append(f"  Puntos    : {g.n_points}")
        lines.append(f"  Grilla    : {g.nx} × {g.ny} × {g.nz}")
        lines.append(f"  X rango   : [{g.x_range[0]:.4f}, {g.x_range[1]:.4f}] mm"
                      f"  (paso: {_fmt_step(g.x_step)})")
        lines.append(f"  Y rango   : [{g.y_range[0]:.4f}, {g.y_range[1]:.4f}] mm"
                      f"  (paso: {_fmt_step(g.y_step)})")
        lines.append(f"  Z rango   : [{g.z_range[0]:.4f}, {g.z_range[1]:.4f}] mm"
                      f"  (paso: {_fmt_step(g.z_step)})")

        # Adquisición
        lines.append(f"")
        lines.append(f"  Mediciones/punto (M) : {self.m_measurements}")
        exp = self._metadata.get("exposure_ms")
        if exp:
            lines.append(f"  Exposición           : {exp} ms")
        lines.append(f"  Dark habilitado      : "
                      f"{'Sí' if self._metadata.get('dark_enabled') else 'No'}")
        lines.append(f"  No-linealidad        : "
                      f"{'Sí' if self._metadata.get('nonlinearity_enabled') else 'No'}")
        lines.append(f"  Modo de barrido      : "
                      f"{self._metadata.get('scan_mode', '?')}")

        # Ventanas
        lines.append(f"")
        lines.append(f"  Ventanas OPD: {self.n_windows}")
        for w in self._windows:
            lines.append(f"    W{w.win_id}: [{w.z_min:.3f}, {w.z_max:.3f}] mm"
                          f"  (span: {w.span:.3f} mm)")

        # Datos disponibles
        lines.append(f"")
        lines.append(f"  Datos disponibles:")
        if self.has_peaks:
            shape = self.depth_mm.shape
            lines.append(f"    ✓ Picos OPD      : {shape}")
        else:
            lines.append(f"    ✗ Picos OPD")

        if self.has_spectra:
            shape = self.spectra.shape
            size_mb = self.spectra.nbytes / 1e6
            lines.append(f"    ✓ Espectros      : {shape}  ({size_mb:.1f} MB)")
        else:
            lines.append(f"    ✗ Espectros")

        if self.has_profiles:
            for win_id, prof in self.profiles.items():
                size_mb = prof.nbytes / 1e6
                dtype = "complex" if np.iscomplexobj(prof) else "módulo"
                lines.append(f"    ✓ Perfil W{win_id}    : {prof.shape}"
                              f"  ({dtype}, {size_mb:.1f} MB)")
        else:
            lines.append(f"    ✗ Perfiles")

        if self.has_wavelengths:
            wl = self.wavelengths
            lines.append(f"    ✓ Wavelengths    : {wl.shape[0]} px"
                          f"  [{wl.min():.1f}, {wl.max():.1f}] nm")
        else:
            lines.append(f"    ✗ Wavelengths")

        # Óptica
        if self._optics.wavelength_nm or self._optics.objective_focal_length_mm:
            lines.append(f"")
            lines.append(f"  Óptica:")
            o = self._optics
            if o.fiber_diameter_um:
                lines.append(f"    Fibra      : {o.fiber_diameter_um} µm")
            if o.wavelength_nm:
                lines.append(f"    λ central  : {o.wavelength_nm} nm")
            if o.collimator_focal_length_mm:
                lines.append(f"    f_col      : {o.collimator_focal_length_mm} mm")
            if o.objective_focal_length_mm:
                lines.append(f"    f_obj      : {o.objective_focal_length_mm} mm")
            if o.na:
                lines.append(f"    NA ≈       : {o.na:.4f}")

        # Tamaño de archivo
        lines.append(f"")
        fsize = os.path.getsize(self._filepath)
        if fsize > 1e6:
            lines.append(f"  Archivo   : {fsize / 1e6:.1f} MB")
        else:
            lines.append(f"  Archivo   : {fsize / 1e3:.1f} KB")

        lines.append(f"{'═' * 60}")
        return "\n".join(lines)

    def data_inventory(self) -> Dict[str, Any]:
        """
        Retorna un inventario estructurado de los datos disponibles.
        Útil para la GUI.
        """
        inv = {
            "n_points": self.n_points,
            "m_measurements": self.m_measurements,
            "n_windows": self.n_windows,
            "dataset_type": self._dataset_type.name,
            "grid": {
                "nx": self._grid.nx,
                "ny": self._grid.ny,
                "nz": self._grid.nz,
                "x_range": self._grid.x_range,
                "y_range": self._grid.y_range,
                "z_range": self._grid.z_range,
                "x_step": self._grid.x_step,
                "y_step": self._grid.y_step,
                "z_step": self._grid.z_step,
            },
            "has_peaks": self.has_peaks,
            "has_spectra": self.has_spectra,
            "has_profiles": self.has_profiles,
            "has_wavelengths": self.has_wavelengths,
        }

        if self.has_peaks:
            inv["peaks_shape"] = self.depth_mm.shape
        if self.has_spectra:
            inv["spectra_shape"] = self.spectra.shape
        if self.has_profiles:
            inv["profiles"] = {
                wid: {"shape": p.shape, "complex": np.iscomplexobj(p)}
                for wid, p in self.profiles.items()
            }

        return inv

    # ── Acceso a datos de topografía ───────────────────────────────────────

    def topography_grid(
        self, win_id: int = 0, measurement: int = 0
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Reconstruir grilla 2D de topografía desde los picos OPD.

        Parameters
        ----------
        win_id : int
            Índice de ventana (0-based).
        measurement : int
            Índice de medición (0-based, para M > 1).

        Returns
        -------
        x_grid, y_grid, z_grid : ndarray
            Grillas 2D (ny, nx) para pcolormesh/imshow.
        """
        if not self.has_peaks:
            raise ValueError("No hay datos de picos OPD")

        g = self._grid
        if g.nz > 1:
            raise ValueError("topography_grid requiere una única cota Z; seleccione un slice Multi-Z")
        if not 0 <= measurement < self.m_measurements:
            raise IndexError(f"Medición fuera de rango: {measurement}")
        if not 0 <= win_id < self.n_windows:
            raise IndexError(f"Ventana fuera de rango: {win_id}")
        finite_xy = np.isfinite(self._X) & np.isfinite(self._Y)
        depth_mm = self.depth_mm  # shape (n_pts, M, N_win)

        # Extraer OPD de la ventana y medición
        z_vals = depth_mm[:, measurement, win_id]

        # Reconstruir grilla
        x_sorted = np.sort(g.x_unique)
        y_sorted = np.sort(g.y_unique)
        x_grid, y_grid = np.meshgrid(x_sorted, y_sorted)
        z_grid = np.full((g.ny, g.nx), np.nan)
        x_tolerance = self._coordinate_tolerances["X"]
        y_tolerance = self._coordinate_tolerances["Y"]
        occupied = set()

        for idx in range(self.n_points):
            if not np.isfinite(self._X[idx]) or not np.isfinite(self._Y[idx]):
                continue
            xi = _nearest_index(x_sorted, self._X[idx])
            yi = _nearest_index(y_sorted, self._Y[idx])
            if (
                0 <= xi < g.nx
                and 0 <= yi < g.ny
                and abs(x_sorted[xi] - self._X[idx]) <= x_tolerance
                and abs(y_sorted[yi] - self._Y[idx]) <= y_tolerance
            ):
                if (xi, yi) in occupied:
                    raise ValueError("La grilla contiene coordenadas X/Y duplicadas; no es una topografía 2D única")
                occupied.add((xi, yi))
                z_grid[yi, xi] = z_vals[idx]

        return x_grid, y_grid, z_grid

    # ── Internos ───────────────────────────────────────────────────────────

    def _build_windows(self, win_data) -> List[WindowConfig]:
        """Construir lista de WindowConfig desde los datos crudos."""
        if win_data is None:
            return []
        z_mins = win_data["z_min"]
        z_maxs = win_data["z_max"]
        return [
            WindowConfig(win_id=i, z_min=float(z_mins[i]), z_max=float(z_maxs[i]))
            for i in range(len(z_mins))
        ]

    def _build_grid(self) -> ScanGrid:
        """Analizar posiciones y construir ScanGrid."""
        x_u = _canonical_unique(self._X, tolerance=self._coordinate_tolerances["X"])
        y_u = _canonical_unique(self._Y, tolerance=self._coordinate_tolerances["Y"])
        z_u = _canonical_unique(self._Z, tolerance=self._coordinate_tolerances["Z"])
        x_u = x_u if x_u.size else np.array([0.0])
        y_u = y_u if y_u.size else np.array([0.0])
        z_u = z_u if z_u.size else np.array([0.0])

        return ScanGrid(
            n_points=len(self._X),
            x_unique=x_u,
            y_unique=y_u,
            z_unique=z_u,
            nx=len(x_u),
            ny=len(y_u),
            nz=len(z_u),
        )

    def _classify(self) -> DatasetType:
        """
        Clasificar automáticamente el tipo de medición.

        Lógica:
        1. Si solo 1 punto → SINGLE_POINT
        2. Si 1 eje varía, el otro fijo → PROFILE_1D
        3. Si X e Y varían, Z fijo → TOPOGRAPHY
        4. Si X, Y y Z varían → MULTI_Z
        5. Else → UNKNOWN

        Los perfiles axiales son payload de cada punto y no convierten una
        topografía en volumen espacial.
        """
        g = self._grid

        # Los perfiles axiales no alteran la geometría espacial.
        # Un solo punto
        if g.n_points <= 1:
            return DatasetType.SINGLE_POINT

        # Solo un eje varía
        if g.ny == 1 and g.nx > 1 and g.nz == 1:
            return DatasetType.PROFILE_1D
        if g.nx == 1 and g.ny > 1 and g.nz == 1:
            return DatasetType.PROFILE_1D

        # Dos ejes varían, Z fijo
        if g.nx > 1 and g.ny > 1 and g.nz == 1:
            return DatasetType.TOPOGRAPHY

        # Tres ejes varían
        if g.nx > 1 and g.ny > 1 and g.nz > 1:
            return DatasetType.MULTI_Z

        # Caso borde: 1D con variación en Z
        if (g.nx > 1 or g.ny > 1) and g.nz > 1:
            return DatasetType.MULTI_Z

        return DatasetType.UNKNOWN

    def __repr__(self) -> str:
        return (
            f"OCTDataset('{self.filename}', "
            f"type={self._dataset_type.name}, "
            f"points={self.n_points}, "
            f"grid={self._grid.nx}×{self._grid.ny}×{self._grid.nz})"
        )


# ── Helpers ────────────────────────────────────────────────────────────────

_COORDINATE_TOLERANCE = 1e-9
_COORDINATE_AXES = ("X", "Y", "Z")


def _coerce_tolerance(value: Any) -> float:
    try:
        value = float(value) if value is not None else _COORDINATE_TOLERANCE
    except (TypeError, ValueError):
        value = _COORDINATE_TOLERANCE
    return max(value, _COORDINATE_TOLERANCE)


def _metadata_coordinate_tolerances(metadata: dict) -> Dict[str, float]:
    """Obtener tolerancias físicas por eje, con fallback histórico."""
    scalar = metadata.get("position_tolerance_mm")
    if scalar is None and metadata.get("position_tolerance_um") is not None:
        scalar = float(metadata["position_tolerance_um"]) * 1e-3
    scalar = _coerce_tolerance(scalar)
    result = {}
    for axis in _COORDINATE_AXES:
        value = metadata.get(f"position_tolerance_{axis.lower()}_mm")
        if value is None and metadata.get(f"position_tolerance_{axis.lower()}_um") is not None:
            value = float(metadata[f"position_tolerance_{axis.lower()}_um"]) * 1e-3
        result[axis] = _coerce_tolerance(scalar if value is None else value)
    return result


def _metadata_coordinate_tolerance(metadata: dict) -> float:
    """Obtener la tolerancia escalar histórica a partir de todos los ejes."""
    return max(_metadata_coordinate_tolerances(metadata).values())


def _canonical_unique(values: np.ndarray, tolerance: float = _COORDINATE_TOLERANCE) -> np.ndarray:
    """Agrupar coordenadas equivalentes dentro de tolerancia física."""
    finite = np.sort(np.asarray(values, dtype=float).ravel())
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return np.array([], dtype=float)
    groups = [finite[0]]
    for value in finite[1:]:
        if abs(value - groups[-1]) > tolerance:
            groups.append(value)
    return np.asarray(groups, dtype=float)


def _nearest_index(sorted_values: np.ndarray, value: float) -> int:
    """Índice de la coordenada canónica más cercana."""
    return int(np.argmin(np.abs(sorted_values - value)))


def _robust_step(values: np.ndarray) -> Optional[float]:
    """Estimar el paso mediano ignorando NaN, infinitos y duplicados."""
    finite = _canonical_unique(values)
    if finite.size < 2:
        return None
    differences = np.diff(finite)
    differences = differences[differences > 1e-12]
    return None if differences.size == 0 else float(np.median(differences))


def _optional_int(value: Any) -> Optional[int]:
    """Convertir metadata numérica opcional sin inventar un valor."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fmt_step(step: Optional[float]) -> str:
    """Formatear paso de grilla para display."""
    if step is None:
        return "N/A"
    if step < 0.001:
        return f"{step * 1000:.2f} µm"
    return f"{step:.4f} mm"
