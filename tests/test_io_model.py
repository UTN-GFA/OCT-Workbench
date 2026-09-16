"""
test_io_model.py
Genera un archivo NPZ sintético con Schema 6 y lo carga
con oct_workbench para verificar loader + OCTDataset.
"""

import sys
import os
import numpy as np
from datetime import datetime

# Agregar el directorio padre al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def create_synthetic_topography(filepath: str) -> str:
    """
    Crear un NPZ sintético que simula una topografía 2D.
    Emula exactamente lo que produciría saver.py (Schema 6).
    """
    # Parámetros del barrido
    nx, ny = 50, 40
    m = 1        # mediciones por punto
    n_win = 1    # ventanas
    n_pixels = 3648

    # Posiciones del barrido [mm]
    x_vals = np.linspace(0.0, 1.0, nx)
    y_vals = np.linspace(0.0, 0.8, ny)

    X_list = []
    Y_list = []
    Z_list = []

    for y in y_vals:
        for x in x_vals:
            X_list.append(x)
            Y_list.append(y)
            Z_list.append(0.0)   # Z fijo → topografía

    X = np.array(X_list, dtype=np.float64)
    Y = np.array(Y_list, dtype=np.float64)
    Z = np.array(Z_list, dtype=np.float64)
    n_points = len(X)

    # Wavelengths — calibración espectral
    wavelengths = np.linspace(740.0, 920.0, n_pixels)

    # OPD — superficie simulada: plano inclinado + ruido
    depth_mm = np.zeros((n_points, m, n_win), dtype=np.float64)
    for i in range(n_points):
        surface = 0.5 + 0.1 * X[i] - 0.05 * Y[i]
        noise = np.random.normal(0, 0.002)
        depth_mm[i, 0, 0] = surface + noise

    # Amplitud
    amplitude = np.ones((n_points, m, n_win), dtype=np.float64) * 5000.0
    amplitude += np.random.normal(0, 200, amplitude.shape)

    # Ventanas
    win_z_min = np.array([0.3], dtype=np.float64)
    win_z_max = np.array([0.8], dtype=np.float64)

    # Metadata (como la genera saver.py)
    save_dict = {
        "wavelengths": wavelengths,
        "X": X,
        "Y": Y,
        "Z": Z,
        "depth_m": depth_mm / 1000.0,
        "amplitude": amplitude,
        "win_depth_min_m": win_z_min / 1000.0,
        "win_depth_max_m": win_z_max / 1000.0,
        # Metadata
        "SCHEMA_VERSION": "6.0.0",
        "SOFTWARE_VERSION": "OCT_V4.4_test",
        "SAMPLE_NAME": "Superficie_Sintetica_Test",
        "SPECTROMETER_MODEL": "HR4000",
        "SPECTROMETER_SERIAL": "SN-TEST-001",
        "EXPOSURE_MS": np.float64(4.0),
        "M_MEASUREMENTS": np.int32(1),
        "DARK_ENABLED": np.bool_(True),
        "NONLINEARITY_ENABLED": np.bool_(False),
        "SCAN_MODE": "snake",
        "K_SAMPLES": np.int32(3648),
        "PROFILE_SAMPLES": np.int32(2048),
        "START_TIME": "2026-06-21T10:00:00",
        "END_TIME": "2026-06-21T10:05:30",
        "DURATION_SEC": np.float64(330.0),
        "N_POINTS_TOTAL": np.int32(n_points),
        "N_POINTS_ACQUIRED": np.int32(n_points),
        "ABORTED": np.bool_(False),
        # Óptica
        "OPTICS_D_FIBER_UM": np.float64(5.0),
        "OPTICS_WL_NM": np.float64(850.0),
        "OPTICS_F_COL_MM": np.float64(18.0),
        "OPTICS_F_OBJ_MM": np.float64(9.0),
    }

    np.savez(filepath, **save_dict)
    print(f"Archivo sintético creado: {filepath}")
    print(f"  {n_points} puntos, grilla {nx}x{ny}, {n_pixels} pixels")
    return filepath


def create_synthetic_profile(filepath: str) -> str:
    """Crear un NPZ sintético de perfil 1D."""
    nx = 200
    m = 1
    n_win = 1

    X = np.linspace(0.0, 2.0, nx)
    Y = np.zeros(nx)
    Z = np.zeros(nx)

    wavelengths = np.linspace(740.0, 920.0, 3648)

    depth_mm = np.zeros((nx, m, n_win), dtype=np.float64)
    for i in range(nx):
        depth_mm[i, 0, 0] = 0.5 + 0.02 * np.sin(2 * np.pi * X[i] / 0.5)

    amplitude = np.ones((nx, m, n_win)) * 3000.0

    save_dict = {
        "wavelengths": wavelengths,
        "X": X, "Y": Y, "Z": Z,
        "depth_m": depth_mm / 1000.0, "amplitude": amplitude,
        "win_depth_min_m": np.array([0.3]) / 1000.0,
        "win_depth_max_m": np.array([0.8]) / 1000.0,
        "SCHEMA_VERSION": "6.0.0",
        "SOFTWARE_VERSION": "OCT_V4.4_test",
        "SAMPLE_NAME": "Perfil_Sinusoidal_Test",
        "EXPOSURE_MS": np.float64(4.0),
        "M_MEASUREMENTS": np.int32(1),
        "DARK_ENABLED": np.bool_(True),
        "NONLINEARITY_ENABLED": np.bool_(False),
        "SCAN_MODE": "snake",
        "K_SAMPLES": np.int32(3648),
        "PROFILE_SAMPLES": np.int32(2048),
        "START_TIME": "2026-06-21T11:00:00",
        "END_TIME": "2026-06-21T11:01:00",
        "DURATION_SEC": np.float64(60.0),
        "N_POINTS_TOTAL": np.int32(nx),
        "N_POINTS_ACQUIRED": np.int32(nx),
        "ABORTED": np.bool_(False),
    }

    np.savez(filepath, **save_dict)
    print(f"Archivo sintético creado: {filepath}")
    return filepath


# ── Test principal ─────────────────────────────────────────────────────────

def main():
    from model.dataset import OCTDataset, DatasetType

    print("=" * 60)
    print("  TEST: io.loader + model.OCTDataset")
    print("=" * 60)

    os.makedirs("test_data", exist_ok=True)
    errors = 0

    # ── Test 1: Topografía 2D ──────────────────────────────────────────
    print("\n▶ Test 1: Topografía 2D")
    topo_path = create_synthetic_topography("test_data/topo_test.npz")
    ds = OCTDataset.from_file(topo_path)

    print(f"\n{ds!r}")
    print(ds.summary())

    # Verificaciones
    assert ds.dataset_type == DatasetType.TOPOGRAPHY, \
        f"Esperado TOPOGRAPHY, got {ds.dataset_type}"
    assert ds.n_points == 2000, f"Esperado 2000 puntos, got {ds.n_points}"
    assert ds.grid.nx == 50, f"Esperado nx=50, got {ds.grid.nx}"
    assert ds.grid.ny == 40, f"Esperado ny=40, got {ds.grid.ny}"
    assert ds.has_peaks, "Debería tener picos"
    assert not ds.has_spectra, "No debería tener espectros"
    assert not ds.has_profiles, "No debería tener perfiles"
    assert ds.has_wavelengths, "Debería tener wavelengths"
    assert ds.n_windows == 1, f"Esperado 1 ventana, got {ds.n_windows}"
    assert ds.optics.wl_nm == 850.0
    assert ds.sample_name == "Superficie_Sintetica_Test"
    print("  ✓ Todas las verificaciones pasaron")

    # Test topography_grid
    xg, yg, zg = ds.topography_grid(win_id=0, measurement=0)
    assert xg.shape == (40, 50), f"Grilla shape: {xg.shape}"
    assert not np.all(np.isnan(zg)), "Grilla no debería ser todo NaN"
    print(f"  ✓ topography_grid: shape {zg.shape}, "
          f"Z range [{np.nanmin(zg):.3f}, {np.nanmax(zg):.3f}]")

    # ── Test 2: Perfil 1D ──────────────────────────────────────────────
    print("\n▶ Test 2: Perfil 1D")
    prof_path = create_synthetic_profile("test_data/profile_test.npz")
    ds2 = OCTDataset.from_file(prof_path)

    print(f"\n{ds2!r}")
    print(ds2.summary())

    assert ds2.dataset_type == DatasetType.PROFILE_1D, \
        f"Esperado PROFILE_1D, got {ds2.dataset_type}"
    assert ds2.n_points == 200
    assert ds2.grid.nx == 200
    assert ds2.grid.ny == 1
    print("  ✓ Todas las verificaciones pasaron")

    # ── Test 3: data_inventory ─────────────────────────────────────────
    print("\n▶ Test 3: data_inventory()")
    inv = ds.data_inventory()
    assert inv["dataset_type"] == "TOPOGRAPHY"
    assert inv["has_peaks"] is True
    assert inv["grid"]["nx"] == 50
    print(f"  ✓ Inventario correcto: {inv['dataset_type']}, "
          f"grid {inv['grid']['nx']}x{inv['grid']['ny']}")

    # ── Resumen ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  TODOS LOS TESTS PASARON ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
