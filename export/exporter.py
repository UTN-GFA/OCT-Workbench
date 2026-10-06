"""
export.exporter
Exportación de datos a múltiples formatos.

Acepta OCTDataset, TransformedView, DerivedObject o
ComparisonPair como fuente, y exporta a:
- CSV (perfiles, tablas)
- NPY (arrays sueltos)
- NPZ (dataset completo)
- HDF5 (dataset completo)
- Imagen PNG (gráfico matplotlib)
"""

from __future__ import annotations

import os
import logging
import json
from typing import Any, Dict, Optional, Union

import numpy as np

from model.dataset import OCTDataset
from transforms.base import TransformedView, TransformData
from extract.derived import DerivedObject
from compare.pair import ComparisonPair, ComparisonStats

logger = logging.getLogger(__name__)

Source = Union[OCTDataset, TransformedView, DerivedObject, ComparisonPair]


# ── Helpers de resolución ──────────────────────────────────────────────────

def _resolve_to_data(source: Source) -> Dict[str, Any]:
    """Resolver una fuente al contrato persistente Schema 6.0."""
    if isinstance(source, ComparisonPair):
        # Un par no es un payload persistible: se exporta su resultado A−B.
        return _resolve_to_data(source.difference())
    if isinstance(source, DerivedObject):
        X, Y, Z = source.X, source.Y, source.Z
        depth_mm = source.depth_mm
        amplitude = source.amplitude
        metadata = dict(source.metadata)
        ds = None
        profiles = None
        profile_axes = None
        wavelengths = None
        windows = None
    elif isinstance(source, TransformedView):
        td = source.transformed_data.apply_mask()
        ds = source.dataset
        X, Y, Z = td.X, td.Y, td.Z
        depth_mm, amplitude = td.depth_mm, td.amplitude
        metadata = dict(ds.metadata)
        metadata["transforms_applied"] = [
            step.name for step in source.pipeline.steps
        ]
        profiles = td.profiles
        profile_axes = td.profile_depth_axes_m
        wavelengths = ds.wavelengths
        windows = ds.windows
    elif isinstance(source, OCTDataset):
        ds = source
        X, Y, Z = source.X, source.Y, source.Z
        depth_mm, amplitude = source.depth_mm, source.amplitude
        metadata = source.metadata
        profiles = source.profiles
        profile_axes = source.profile_depth_axes_m
        wavelengths = source.wavelengths
        windows = source.windows
    else:
        raise TypeError(f"Fuente no soportada: {type(source)}")

    if depth_mm is not None and amplitude is None:
        # Un resultado derivado puede tener profundidad sin amplitud propia
        # (por ejemplo, una diferencia A−B). Mantener la shape con NaN hace
        # que el payload siga siendo reabrible sin inventar una medición.
        amplitude = np.full_like(np.asarray(depth_mm), np.nan, dtype=np.float64)

    data: Dict[str, Any] = {"x_mm": np.asarray(X), "y_mm": np.asarray(Y), "z_mm": np.asarray(Z)}
    if wavelengths is not None:
        data["wavelengths_nm"] = np.asarray(wavelengths)
    if depth_mm is not None:
        data["depth_m"] = np.asarray(depth_mm) / 1000.0
        data["depth_axis_kind"] = "physical_depth_mm"
        data["depth_source_key"] = "depth_m"
    if amplitude is not None:
        data["amplitude"] = np.asarray(amplitude)
    if isinstance(source, TransformedView):
        if td.spectra is not None:
            data["spectra"] = td.spectra
    elif ds is not None and ds.spectra is not None:
        data["spectra"] = ds.spectra
    if windows:
        data["win_depth_min_m"] = np.asarray([window.z_min for window in windows]) / 1000.0
        data["win_depth_max_m"] = np.asarray([window.z_max for window in windows]) / 1000.0
    elif isinstance(source, DerivedObject):
        z_min = metadata.get("window_z_min_mm")
        z_max = metadata.get("window_z_max_mm")
        if z_min is not None and z_max is not None:
            data["win_depth_min_m"] = np.asarray(z_min, dtype=float) / 1000.0
            data["win_depth_max_m"] = np.asarray(z_max, dtype=float) / 1000.0
    if profiles:
        for win_id, profile in profiles.items():
            if np.iscomplexobj(profile):
                data[f"profile_real_w{win_id}"] = np.real(profile)
                data[f"profile_imag_w{win_id}"] = np.imag(profile)
            else:
                data[f"profile_mod_w{win_id}"] = np.asarray(profile)
    if profile_axes:
        for win_id, axis in profile_axes.items():
            data[f"profile_depth_m_w{win_id}"] = np.asarray(axis)

    scalar_names = {
        "schema_version": "schema_version", "software_version": "software_version",
        "sample_name": "sample_name", "spectrometer_model": "spectrometer_model",
        "spectrometer_serial": "spectrometer_serial", "exposure_ms": "exposure_ms",
        "m_measurements": "measurements_per_point", "dark_enabled": "dark",
        "nonlinearity_enabled": "nonlinearity", "scan_mode": "scan_mode",
        "k_samples": "k_samples", "profile_samples": "global_profile_samples",
        "start_time": "start_time", "end_time": "end_time",
        "duration_sec": "duration_s", "n_points_total": "planned_points",
        "n_points_acquired": "acquired_points", "aborted": "aborted",
        "axis_order": "axis_order", "position_tolerance_x_mm": "position_tolerance_x_mm",
        "position_tolerance_y_mm": "position_tolerance_y_mm", "position_tolerance_z_mm": "position_tolerance_z_mm",
        "position_tolerance_mm": "position_tolerance_mm", "position_tolerance_um": "position_tolerance_um",
        "depth_axis_kind": "depth_axis_kind", "depth_source_key": "depth_source_key",
    }
    for key, value in metadata.items():
        if key == "optics" and isinstance(value, dict):
            for optics_key, optics_value in value.items():
                if optics_value is not None:
                    data[{"d_fiber_um": "o_d_fib_um", "wl_nm": "o_wl_nm", "f_col_mm": "o_f_col_mm", "f_obj_mm": "o_f_obj_mm"}.get(optics_key, f"o_{optics_key}")] = optics_value
        elif key in scalar_names and isinstance(value, (str, int, float, bool, np.generic)):
            data[scalar_names[key]] = value.item() if isinstance(value, np.generic) else value
    if isinstance(source, TransformedView):
        data["TRANSFORMS_APPLIED"] = json.dumps(
            metadata["transforms_applied"], sort_keys=True, default=str
        )
    if isinstance(source, DerivedObject):
        data["DERIVED_FROM"] = source.provenance.source_file
        data["EXTRACTION_TYPE"] = source.provenance.extraction_type.name
        data["EXTRACTION_TIME"] = source.provenance.timestamp
        data["EXTRACTION_PARAMETERS"] = json.dumps(
            source.provenance.parameters, sort_keys=True, default=str
        )
        data["TRANSFORMS_APPLIED"] = json.dumps(
            source.provenance.transforms_applied, sort_keys=True, default=str
        )
    data["schema_version"] = "6.0.0"
    return data


# ── Exportadores ───────────────────────────────────────────────────────────

def to_npz(source: Source, filepath: str) -> str:
    """
    Exportar a NPZ (formato compatible con saver.py / loader.py).

    El archivo resultante puede re-cargarse con OCTDataset.from_file().
    """
    filepath = _ensure_ext(filepath, ".npz")
    data = _resolve_to_data(source)
    np.savez(filepath, **data)
    logger.info("Exportado NPZ: %s", filepath)
    return filepath


def to_npy(array: np.ndarray, filepath: str) -> str:
    """Exportar un array suelto a NPY."""
    filepath = _ensure_ext(filepath, ".npy")
    np.save(filepath, array)
    logger.info("Exportado NPY: %s (%s)", filepath, array.shape)
    return filepath


def to_csv(
    source: Source,
    filepath: str,
    win_id: int = 0,
    measurement: int = 0,
    delimiter: str = ",",
    header: bool = True,
) -> str:
    """
    Exportar a CSV.

    Genera una tabla con columnas X, Y, Z, OPD, Amplitude.
    Para topografías: una fila por punto.
    Para perfiles: una fila por punto del perfil.
    """
    filepath = _ensure_ext(filepath, ".csv")
    data = _resolve_to_data(source)

    X = data.get("x_mm", data.get("X"))
    Y = data.get("y_mm", data.get("Y"))
    Z = data.get("z_mm", data.get("Z"))

    columns = [X, Y, Z]
    col_names = ["X_mm", "Y_mm", "Z_mm"]

    if "depth_m" in data:
        depth_mm = np.asarray(data["depth_m"]) * 1000.0
        if depth_mm.ndim == 3:
            m = min(measurement, depth_mm.shape[1] - 1)
            w = min(win_id, depth_mm.shape[2] - 1)
            columns.append(depth_mm[:, m, w])
            col_names.append(f"Depth_W{w}_M{m}_mm")
        elif depth_mm.ndim == 1:
            columns.append(depth_mm)
            col_names.append("Depth_mm")

    if "amplitude" in data:
        amp = data["amplitude"]
        if amp.ndim == 3:
            m = min(measurement, amp.shape[1] - 1)
            w = min(win_id, amp.shape[2] - 1)
            columns.append(amp[:, m, w])
            col_names.append(f"Amplitude_W{w}_M{m}")
        elif amp.ndim == 1:
            columns.append(amp)
            col_names.append("Amplitude")

    table = np.column_stack(columns)

    # Build provenance header
    prov_lines = []
    if "SAMPLE_NAME" in data:
        prov_lines.append(f"# Muestra: {data['SAMPLE_NAME']}")
    if "DERIVED_FROM" in data:
        prov_lines.append(f"# Origen: {data['DERIVED_FROM']}")
    if "EXTRACTION_TYPE" in data:
        prov_lines.append(f"# Extraccion: {data['EXTRACTION_TYPE']}")
    if "EXTRACTION_TIME" in data:
        prov_lines.append(f"# Fecha extraccion: {data['EXTRACTION_TIME']}")
    if "EXTRACTION_PARAMETERS" in data:
        prov_lines.append(f"# Parametros: {data['EXTRACTION_PARAMETERS']}")
    if "TRANSFORMS_APPLIED" in data:
        prov_lines.append(f"# Transforms: {data['TRANSFORMS_APPLIED']}")
    prov_lines.append(f"# Puntos: {len(X)}")
    prov_lines.append(f"# Unidades: mm")

    header_line = delimiter.join(col_names) if header else ""
    prov_block = "\n".join(prov_lines) + "\n" if prov_lines else ""

    with open(filepath, "w") as f:
        # El encabezado de columnas va primero para que lectores numéricos
        # convencionales puedan usar skiprows=1. La proveniencia sigue siendo
        # comentario y no contamina la tabla.
        if header_line:
            f.write(header_line + "\n")
        if prov_block:
            f.write(prov_block)
        for row in table:
            f.write(delimiter.join(f"{v:.8f}" for v in row) + "\n")
    logger.info("Exportado CSV: %s (%d filas, %d cols)", filepath, len(X), len(col_names))
    return filepath


def to_h5(source: Source, filepath: str) -> str:
    """
    Exportar a HDF5 (formato compatible con loader.py).
    """
    try:
        import h5py
    except ImportError:
        raise ImportError("h5py no instalado. Ejecutar: pip install h5py")

    filepath = _ensure_ext(filepath, ".h5")
    data = _resolve_to_data(source)

    with h5py.File(filepath, "w") as f:
        # Arrays como datasets
        array_keys = {
            "x_mm", "y_mm", "z_mm", "depth_m", "amplitude", "spectra",
            "wavelengths_nm", "win_depth_min_m", "win_depth_max_m",
            *[key for key in data if key.startswith("profile_")],
        }
        for key in array_keys:
            if key in data and isinstance(data[key], np.ndarray):
                f.create_dataset(key, data=data[key])

        # Scalars como atributos
        for key, val in data.items():
            if key not in array_keys and not isinstance(val, np.ndarray):
                try:
                    f.attrs[key.lower()] = val
                except TypeError:
                    f.attrs[key.lower()] = str(val)

    logger.info("Exportado HDF5: %s", filepath)
    return filepath


def to_png(
    fig,
    filepath: str,
    dpi: int = 300,
) -> str:
    """
    Exportar una figura matplotlib a PNG.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        Figura a exportar.
    filepath : str
        Ruta de salida.
    dpi : int
        Resolución (default 300).
    """
    filepath = _ensure_ext(filepath, ".png")
    fig.savefig(filepath, dpi=dpi, bbox_inches="tight", facecolor="white")
    logger.info("Exportado PNG: %s (%d dpi)", filepath, dpi)
    return filepath


def stats_to_csv(
    stats: ComparisonStats,
    filepath: str,
    delimiter: str = ",",
) -> str:
    """Exportar estadísticas de comparación a CSV."""
    filepath = _ensure_ext(filepath, ".csv")

    lines = [
        f"# Depth unit: {stats.depth_mm_unit}",
        delimiter.join(["Metric", "A", "B", "A-B"]),
        delimiter.join(["n_points", str(stats.n_points_a), str(stats.n_points_b), str(stats.n_points_common)]),
        delimiter.join(["mean", f"{stats.mean_a:.8f}", f"{stats.mean_b:.8f}", f"{stats.mean_diff:.8f}"]),
        delimiter.join(["std", f"{stats.std_a:.8f}", f"{stats.std_b:.8f}", f"{stats.std_diff:.8f}"]),
        delimiter.join(["pv", f"{stats.pv_a:.8f}", f"{stats.pv_b:.8f}", f"{stats.pv_diff:.8f}"]),
        delimiter.join(["rms_diff", "", "", f"{stats.rms_diff:.8f}"]),
        delimiter.join(["max_abs_diff", "", "", f"{stats.max_abs_diff:.8f}"]),
    ]

    with open(filepath, "w") as f:
        f.write("\n".join(lines) + "\n")

    logger.info("Exportado stats CSV: %s", filepath)
    return filepath


# ── Helpers ────────────────────────────────────────────────────────────────

def _ensure_ext(filepath: str, ext: str) -> str:
    """Asegurar que el filepath tiene la extensión correcta."""
    filepath = os.fspath(filepath)
    if not filepath.lower().endswith(ext):
        filepath += ext
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    return filepath
