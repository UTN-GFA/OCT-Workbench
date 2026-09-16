"""
io.loader
Carga de archivos OCT generados por el saver activo (Schema 6.0).

Formatos soportados: NPZ (.npz), HDF5 (.h5/.hdf5)
"""

from __future__ import annotations

import os
from datetime import datetime
import logging
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Mapeo de keys NPZ (UPPER_CASE) a nombres internos (snake_case) ────────

_NPZ_META_MAP = {
    # Alias de claves NPZ en mayúsculas; el contrato vigente usa snake_case.
    "SCHEMA_VERSION":       "schema_version",
    "SOFTWARE_VERSION":     "software_version",
    "SAMPLE_NAME":          "sample_name",
    "SPECTROMETER_MODEL":   "spectrometer_model",
    "SPECTROMETER_SERIAL":  "spectrometer_serial",
    "EXPOSURE_MS":          "exposure_ms",
    "M_MEASUREMENTS":       "m_measurements",
    "DARK_ENABLED":         "dark_enabled",
    "NONLINEARITY_ENABLED": "nonlinearity_enabled",
    "SCAN_MODE":            "scan_mode",
    "K_SAMPLES":            "k_samples",
    "PROFILE_SAMPLES":      "profile_samples",
    "START_TIME":           "start_time",
    "END_TIME":             "end_time",
    "DURATION_SEC":         "duration_sec",
    "N_POINTS_TOTAL":       "n_points_total",
    "N_POINTS_ACQUIRED":    "n_points_acquired",
    "ABORTED":              "aborted",
    "depth_axis_kind":      "depth_axis_kind",
    "depth_source_key":     "depth_source_key",
    # Schema 6.0 activo.
    "dark":                  "dark_enabled",
    "nonlinearity":          "nonlinearity_enabled",
    "axis_order":            "axis_order",
    "position_tolerance_x_mm": "position_tolerance_x_mm",
    "position_tolerance_y_mm": "position_tolerance_y_mm",
    "position_tolerance_z_mm": "position_tolerance_z_mm",
    "position_tolerance_mm": "position_tolerance_mm",
    "position_tolerance_um": "position_tolerance_um",
    "schema_version":       "schema_version",
    "software_version":      "software_version",
    "sample_name":           "sample_name",
    "spectrometer_model":    "spectrometer_model",
    "spectrometer_serial":  "spectrometer_serial",
    "exposure_ms":           "exposure_ms",
    "measurements_per_point":"m_measurements",
    "dark_enabled":         "dark_enabled",
    "nonlinearity_enabled":  "nonlinearity_enabled",
    "scan_mode":             "scan_mode",
    "k_samples":             "k_samples",
    "global_profile_samples":"profile_samples",
    "start_time":            "start_time",
    "end_time":              "end_time",
    "duration_s":            "duration_sec",
    "planned_points":        "n_points_total",
    "acquired_points":       "n_points_acquired",
    "aborted":               "aborted",
    "DERIVED_FROM":          "derived_from",
    "EXTRACTION_TYPE":       "extraction_type",
    "EXTRACTION_TIME":       "extraction_time",
    "EXTRACTION_PARAMETERS": "extraction_parameters",
    "TRANSFORMS_APPLIED":    "transforms_applied",
}

# Keys de óptica (prefijo OPTICS_ en NPZ, optics_ en H5)
_OPTICS_KEYS = ("d_fiber_um", "wl_nm", "f_col_mm", "f_obj_mm")

# Keys de datos (arrays principales)
_DATA_KEYS = {"wavelengths", "X", "Y", "Z", "depth_m", "amplitude", "spectra",
              "win_z_min", "win_z_max"}


# ── Funciones de carga ─────────────────────────────────────────────────────

def load(filepath: str) -> Dict[str, Any]:
    """
    Cargar un archivo OCT y retornar un dict normalizado.

    Parameters
    ----------
    filepath : str
        Ruta al archivo .npz o .h5/.hdf5.

    Returns
    -------
    dict con keys:
        "filepath"    : str — ruta absoluta del archivo
        "format"      : str — "npz" o "h5"
        "metadata"    : dict — metadata normalizada (snake_case)
        "positions"   : dict — {"X": array, "Y": array, "Z": array}
        "wavelengths" : ndarray — calibración espectral (nm)
        "windows"     : dict — {"z_min": array, "z_max": array}
        "peaks"       : dict o None — {"depth_mm": array, "amplitude": array}
        "spectra"     : ndarray o None — espectros crudos
        "profiles"    : dict o None — {win_id: array, ...}
    """
    filepath = os.path.abspath(filepath)
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".npz":
        return _load_npz(filepath)
    elif ext in (".h5", ".hdf5"):
        return _load_h5(filepath)
    else:
        raise ValueError(f"Formato no soportado: {ext!r}. Usar .npz o .h5")


def _load_npz(filepath: str) -> Dict[str, Any]:
    """Cargar archivo NPZ del contrato Schema 6."""
    raw = np.load(filepath, allow_pickle=False)
    keys = set(raw.files)

    # ── Metadata ──
    metadata = {}
    for npz_key, internal_key in _NPZ_META_MAP.items():
        if npz_key in keys:
            val = raw[npz_key]
            metadata[internal_key] = _scalar(val)

    # Óptica: aceptar aliases nominales de archivos existentes.
    optics_aliases = {
        "d_fiber_um": ("o_d_fib_um", "OPTICS_D_FIBER_UM", "optics_fiber_diameter_um"),
        "wl_nm": ("o_wl_nm", "OPTICS_WL_NM", "optics_wavelength_nm"),
        "f_col_mm": ("o_f_col_mm", "OPTICS_F_COL_MM", "optics_collimator_focal_length_mm"),
        "f_obj_mm": ("o_f_obj_mm", "OPTICS_F_OBJ_MM", "optics_objective_focal_length_mm"),
    }
    for okey, aliases in optics_aliases.items():
        for npz_key in aliases:
            if npz_key in keys:
                metadata.setdefault("optics", {})[okey] = float(raw[npz_key])
                break

    # ── Posiciones ──
    positions = {
        "X": np.asarray(
            raw["X"] if "X" in keys else raw["x_mm"] if "x_mm" in keys else [],
            dtype=np.float64,
        ),
        "Y": np.asarray(
            raw["Y"] if "Y" in keys else raw["y_mm"] if "y_mm" in keys else [],
            dtype=np.float64,
        ),
        "Z": np.asarray(
            raw["Z"] if "Z" in keys else raw["z_mm"] if "z_mm" in keys else raw["z_mechanical_mm"] if "z_mechanical_mm" in keys else [],
            dtype=np.float64,
        ),
    }

    _validate_positions(positions)

    # ── Wavelengths ──
    wavelengths_key = "wavelengths" if "wavelengths" in keys else "wavelengths_nm"
    wavelengths = (
        np.asarray(raw[wavelengths_key], dtype=np.float64)
        if wavelengths_key in keys else None
    )

    # ── Ventanas ──
    z_min_key = "win_z_min" if "win_z_min" in keys else "win_depth_min_m"
    z_max_key = "win_z_max" if "win_z_max" in keys else "win_depth_max_m"
    windows = None
    if z_min_key in keys and z_max_key in keys:
        z_min = np.asarray(raw[z_min_key], dtype=np.float64)
        z_max = np.asarray(raw[z_max_key], dtype=np.float64)
        # Schema 6 declara metros en win_depth_*_m. Normalizar internamente a
        # mm; el umbral conserva tolerancia para entradas nominales antiguas.
        if z_min_key == "win_depth_min_m" or np.nanmax(np.abs(z_max)) < 0.1:
            z_min = z_min * 1000.0
            z_max = z_max * 1000.0
        windows = {"z_min": z_min, "z_max": z_max}

    # ── Picos ──
    # Schema 6 usa depth_m en persistencia y depth_mm en memoria.
    if "opd" in keys:
        raise ValueError("Payload no válido: Schema 6 requiere depth_m; no se admite opd")
    has_peak_values = "depth_m" in keys
    has_amplitude = "amplitude" in keys
    if has_peak_values != has_amplitude:
        raise ValueError("Payload de picos incompleto: se requieren valores y amplitude")
    peaks = None
    if has_peak_values:
        peak_values = np.asarray(raw["depth_m"], dtype=np.float64)
        metadata.setdefault("units", {})["depth_mm"] = "mm"
        metadata["depth_source_key"] = "depth_m"
        declared_axis = metadata.get("depth_axis_kind")
        if declared_axis not in (None, "physical_depth_mm"):
            raise ValueError(
                "depth_m es incompatible con depth_axis_kind="
                f"{declared_axis!r}"
            )
        peak_values = peak_values * 1000.0
        metadata["depth_axis_kind"] = "physical_depth_mm"
        peaks = {
            "depth_mm": peak_values,
            "amplitude": np.asarray(raw["amplitude"], dtype=np.float64),
        }

    # ── Espectros ──
    spectra = None
    if "spectra" in keys:
        spectra = np.asarray(raw["spectra"], dtype=np.float64)

    # ── Perfiles axiales ──
    profiles = _extract_profiles(keys, raw)
    profile_depth_axes_m = _extract_profile_axes(keys, raw)
    _infer_measurements(metadata, peaks, spectra, profiles)
    _derive_duration(metadata)
    _validate_shapes(positions, wavelengths, peaks, spectra, profiles, profile_depth_axes_m)

    raw.close()

    logger.info("NPZ cargado: %s (%d puntos)", filepath, len(positions["X"]))

    return {
        "filepath":    filepath,
        "format":      "npz",
        "metadata":    metadata,
        "positions":   positions,
        "wavelengths": wavelengths,
        "windows":     windows,
        "peaks":       peaks,
        "spectra":     spectra,
        "profiles":    profiles,
        "profile_depth_axes_m": profile_depth_axes_m,
    }


def _load_h5(filepath: str) -> Dict[str, Any]:
    """Cargar archivo HDF5 del contrato Schema 6."""
    try:
        import h5py
    except ImportError:
        raise ImportError(
            "h5py no instalado. Ejecutar: pip install h5py"
        )

    with h5py.File(filepath, "r") as f:
        attrs = dict(f.attrs)

        # ── Metadata ──
        metadata = {}
        attr_aliases = {
            "schema_version": ("schema_version",),
            "software_version": ("software_version",),
            "sample_name": ("sample_name",),
            "spectrometer_model": ("spectrometer_model",),
            "spectrometer_serial": ("spectrometer_serial",),
            "exposure_ms": ("exposure_ms",),
            "m_measurements": ("m_measurements", "measurements_per_point"),
            "dark_enabled": ("dark_enabled", "dark"),
            "nonlinearity_enabled": ("nonlinearity_enabled", "nonlinearity"),
            "scan_mode": ("scan_mode",),
            "k_samples": ("k_samples",),
            "profile_samples": ("profile_samples", "global_profile_samples"),
            "start_time": ("start_time",),
            "end_time": ("end_time",),
            "duration_sec": ("duration_sec", "duration_s"),
            "n_points_total": ("n_points_total", "planned_points"),
            "n_points_acquired": ("n_points_acquired", "acquired_points"),
            "aborted": ("aborted",),
            "axis_order": ("axis_order",),
            "position_tolerance_x_mm": ("position_tolerance_x_mm",),
            "position_tolerance_y_mm": ("position_tolerance_y_mm",),
            "position_tolerance_z_mm": ("position_tolerance_z_mm",),
            "position_tolerance_mm": ("position_tolerance_mm",),
            "position_tolerance_um": ("position_tolerance_um",),
            "depth_axis_kind": ("depth_axis_kind",),
            "depth_source_key": ("depth_source_key",),
            "derived_from": ("derived_from",),
            "extraction_type": ("extraction_type",),
            "extraction_time": ("extraction_time",),
            "extraction_parameters": ("extraction_parameters",),
            "transforms_applied": ("transforms_applied",),
        }
        for internal_key, aliases in attr_aliases.items():
            for attr_key in aliases:
                if attr_key in attrs:
                    metadata[internal_key] = _scalar(attrs[attr_key])
                    break

        # Óptica: atributos actuales y aliases nominales aceptados.
        optics_aliases = {
            "d_fiber_um": ("o_d_fib_um", "d_fiber_um", "optics_fiber_diameter_um"),
            "wl_nm": ("o_wl_nm", "wl_nm", "optics_wavelength_nm"),
            "f_col_mm": ("o_f_col_mm", "f_col_mm", "optics_collimator_focal_length_mm"),
            "f_obj_mm": ("o_f_obj_mm", "f_obj_mm", "optics_objective_focal_length_mm"),
        }
        for okey, aliases in optics_aliases.items():
            for attr_key in aliases:
                if attr_key in attrs:
                    metadata.setdefault("optics", {})[okey] = float(attrs[attr_key])
                    break

        # ── Posiciones ──
        def read_dataset(*names):
            for name in names:
                if name in f:
                    return np.asarray(f[name][:], dtype=np.float64)
            return np.array([])

        positions = {
            "X": read_dataset("X", "x_mm"),
            "Y": read_dataset("Y", "y_mm"),
            "Z": read_dataset("Z", "z_mm", "z_mechanical_mm"),
        }
        _validate_positions(positions)

        # ── Wavelengths ──
        wavelengths = read_dataset("wavelengths", "wavelengths_nm")
        if wavelengths.size == 0:
            wavelengths = None

        # ── Ventanas ──
        z_min_key = "win_z_min" if "win_z_min" in f else "win_depth_min_m"
        z_max_key = "win_z_max" if "win_z_max" in f else "win_depth_max_m"
        windows = None
        if z_min_key in f and z_max_key in f:
            z_min = np.asarray(f[z_min_key][:], dtype=np.float64)
            z_max = np.asarray(f[z_max_key][:], dtype=np.float64)
            if z_min_key == "win_depth_min_m" or np.nanmax(np.abs(z_max)) < 0.1:
                z_min *= 1000.0
                z_max *= 1000.0
            windows = {"z_min": z_min, "z_max": z_max}

        # ── Picos ──
        if "opd" in f:
            raise ValueError("Payload no válido: Schema 6 requiere depth_m; no se admite opd")
        has_peak_values = "depth_m" in f
        has_amplitude = "amplitude" in f
        if has_peak_values != has_amplitude:
            raise ValueError("Payload de picos incompleto: se requieren valores y amplitude")
        peaks = None
        if has_peak_values:
            peak_values = np.asarray(f["depth_m"][:], dtype=np.float64)
            metadata.setdefault("units", {})["depth_mm"] = "mm"
            metadata["depth_source_key"] = "depth_m"
            declared_axis = metadata.get("depth_axis_kind")
            if declared_axis not in (None, "physical_depth_mm"):
                raise ValueError(
                    "depth_m es incompatible con depth_axis_kind="
                    f"{declared_axis!r}"
                )
            peak_values *= 1000.0
            metadata["depth_axis_kind"] = "physical_depth_mm"
            peaks = {
                "depth_mm": peak_values,
                "amplitude": np.asarray(f["amplitude"][:], dtype=np.float64),
            }

        # ── Espectros ──
        spectra = (
            np.asarray(f["spectra"][:], dtype=np.float64)
            if "spectra" in f else None
        )

        # ── Perfiles ──
        h5_keys = set(f.keys())
        profiles = _extract_profiles(h5_keys, f)
        profile_depth_axes_m = _extract_profile_axes(h5_keys, f)
        _infer_measurements(metadata, peaks, spectra, profiles)
        _derive_duration(metadata)
        _validate_shapes(positions, wavelengths, peaks, spectra, profiles, profile_depth_axes_m)

    logger.info("HDF5 cargado: %s (%d puntos)", filepath, len(positions["X"]))

    return {
        "filepath":    filepath,
        "format":      "h5",
        "metadata":    metadata,
        "positions":   positions,
        "wavelengths": wavelengths,
        "windows":     windows,
        "peaks":       peaks,
        "spectra":     spectra,
        "profiles":    profiles,
        "profile_depth_axes_m": profile_depth_axes_m,
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _extract_profiles(keys, source) -> Optional[Dict[int, np.ndarray]]:
    """
    Extraer perfiles axiales de NPZ o HDF5.

    Busca keys con patrón profile_mod_w{i} o profile_real_w{i}.
    Retorna dict {win_id: ndarray} o None si no hay perfiles.
    """
    profiles = {}
    representations = {}

    for key in sorted(keys):
        if key.startswith("profile_mod_w"):
            try:
                win_id = int(key.replace("profile_mod_w", ""))
                if win_id in representations:
                    raise ValueError(
                        f"Hay múltiples representaciones de perfil para W{win_id}"
                    )
                arr = np.asarray(source[key]).copy()
                profiles[win_id] = arr
                representations[win_id] = "modulus"
            except (ValueError, KeyError):
                raise

        elif key.startswith("profile_real_w"):
            try:
                win_id = int(key.replace("profile_real_w", ""))
                if win_id in representations:
                    raise ValueError(
                        f"Hay múltiples representaciones de perfil para W{win_id}"
                    )
                real = np.asarray(source[key], dtype=np.float64)
                imag_key = f"profile_imag_w{win_id}"
                if imag_key in keys:
                    imag = np.asarray(source[imag_key], dtype=np.float64)
                    profiles[win_id] = real + 1j * imag
                    representations[win_id] = "real_imag"
                else:
                    profiles[win_id] = real
                    representations[win_id] = "real"
            except (ValueError, KeyError):
                raise

    return profiles if profiles else None


def _extract_profile_axes(keys, source) -> Optional[Dict[int, np.ndarray]]:
    """Extraer ejes físicos `profile_depth_m_wN` de Schema 6.0."""
    axes = {}
    for key in sorted(keys):
        if not key.startswith("profile_depth_m_w"):
            continue
        try:
            win_id = int(key.replace("profile_depth_m_w", ""))
            axes[win_id] = np.asarray(source[key], dtype=np.float64).copy()
        except (ValueError, KeyError):
            continue
    return axes if axes else None


def _validate_positions(positions: Dict[str, np.ndarray]) -> None:
    lengths = {name: len(values) for name, values in positions.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"Longitudes X/Y/Z inconsistentes: {lengths}")


def _infer_measurements(metadata, peaks, spectra, profiles) -> None:
    """Inferir M y verificarlo contra todos los payloads disponibles."""
    candidates = []
    if peaks is not None and peaks["depth_mm"].ndim >= 2:
        candidates.append(peaks["depth_mm"].shape[1])
    if spectra is not None and spectra.ndim >= 2:
        candidates.append(spectra.shape[1])
    if profiles:
        candidates.extend(
            profile.shape[1] for profile in profiles.values() if profile.ndim >= 2
        )

    declared = metadata.get("m_measurements")
    if declared is not None:
        try:
            declared = int(declared)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"M_MEASUREMENTS inválido: {declared!r}") from exc
        if declared < 1:
            raise ValueError(f"M_MEASUREMENTS inválido: {declared!r}")
        if candidates and any(candidate != declared for candidate in candidates):
            raise ValueError(
                f"Cardinalidad M inconsistente: declarada={declared}, payloads={candidates}"
            )
        return

    if candidates and len(set(candidates)) != 1:
        raise ValueError(f"Cardinalidad M inconsistente: {candidates}")
    metadata["m_measurements"] = int(candidates[0]) if candidates else 1


def _derive_duration(metadata) -> None:
    if "duration_sec" in metadata or not metadata.get("start_time") or not metadata.get("end_time"):
        return
    try:
        start = datetime.fromisoformat(str(metadata["start_time"]))
        end = datetime.fromisoformat(str(metadata["end_time"]))
        metadata["duration_sec"] = max(0.0, (end - start).total_seconds())
    except (TypeError, ValueError):
        return


def _validate_shapes(positions, wavelengths, peaks, spectra, profiles, profile_axes) -> None:
    n_points = len(positions["X"])
    if profile_axes and not profiles:
        raise ValueError("Hay ejes de perfil sin perfiles asociados")
    if peaks is not None:
        if peaks["depth_mm"].ndim != 3:
            raise ValueError(
                "El payload de picos debe tener shape (P, M, N_win)"
            )
        if peaks["depth_mm"].shape != peaks["amplitude"].shape:
            raise ValueError("depth_m y amplitude deben tener el mismo shape")
        if peaks["depth_mm"].ndim < 1 or peaks["depth_mm"].shape[0] != n_points:
            raise ValueError("El primer eje de depth_m debe coincidir con X/Y/Z")
    if spectra is not None and spectra.ndim >= 1 and spectra.shape[0] != n_points:
        raise ValueError("El primer eje de spectra debe coincidir con X/Y/Z")
    if spectra is not None and wavelengths is not None and spectra.ndim >= 1:
        if spectra.shape[-1] != len(wavelengths):
            raise ValueError("wavelengths_nm no coincide con el eje espectral")
    if profiles:
        for win_id, profile in profiles.items():
            if profile.ndim < 1 or profile.shape[0] != n_points:
                raise ValueError(f"El perfil W{win_id} no coincide con X/Y/Z")
            if profile_axes and win_id in profile_axes:
                if profile.shape[-1] != len(profile_axes[win_id]):
                    raise ValueError(f"El eje del perfil W{win_id} no coincide con su shape")


def _scalar(val):
    """Convertir numpy scalar/array(0d) a tipo Python nativo."""
    if isinstance(val, np.ndarray):
        if val.ndim == 0:
            val = val.item()
        elif val.size == 1:
            val = val.flat[0]
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val
