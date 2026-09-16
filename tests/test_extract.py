"""
test_extract.py
Tests del módulo de extracción de datos.
"""

import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model.dataset import OCTDataset, DatasetType
from transforms.base import TransformedView
from tests.plugin_transforms import LevelPlane, CenterOrigin
from extract import (
    DerivedObject, ExtractionType,
    extract_profile_x, extract_profile_y,
    extract_region, extract_z_slice, extract_window, extract_cuts,
)


def create_topography_dataset() -> OCTDataset:
    """Topografía 2D sintética."""
    nx, ny = 40, 30
    X, Y, Z = [], [], []
    for y in np.linspace(0.0, 0.6, ny):
        for x in np.linspace(0.0, 1.0, nx):
            X.append(x)
            Y.append(y)
            Z.append(0.0)

    X, Y, Z = np.array(X), np.array(Y), np.array(Z)
    n = len(X)

    depth_mm = np.zeros((n, 1, 2))  # 2 ventanas
    amplitude = np.zeros((n, 1, 2))
    for i in range(n):
        depth_mm[i, 0, 0] = 0.5 + 0.1 * X[i] + 0.01 * np.sin(20 * X[i])
        depth_mm[i, 0, 1] = 0.3 + 0.05 * Y[i]
        amplitude[i, 0, 0] = 5000 + np.random.normal(0, 100)
        amplitude[i, 0, 1] = 3000 + np.random.normal(0, 100)

    path = "test_data/extract_topo.npz"
    os.makedirs("test_data", exist_ok=True)
    np.savez(path,
             wavelengths=np.linspace(740, 920, 100),
             X=X, Y=Y, Z=Z, depth_m=(depth_mm) / 1000.0, amplitude=amplitude,
             win_depth_min_m=(np.array([0.3, 0.1])) / 1000.0,
             win_depth_max_m=(np.array([0.8, 0.5])) / 1000.0,
             SCHEMA_VERSION="6.0.0",
             SAMPLE_NAME="Extract_Topo_Test",
             EXPOSURE_MS=np.float64(4.0),
             M_MEASUREMENTS=np.int32(1),
             DARK_ENABLED=np.bool_(True),
             NONLINEARITY_ENABLED=np.bool_(False),
             SCAN_MODE="snake",
             K_SAMPLES=np.int32(100),
             PROFILE_SAMPLES=np.int32(50),
             N_POINTS_TOTAL=np.int32(n),
             N_POINTS_ACQUIRED=np.int32(n),
             ABORTED=np.bool_(False))
    return OCTDataset.from_file(path)


def create_multiz_dataset() -> OCTDataset:
    """Dataset Multi-Z sintético."""
    nx, ny, nz = 20, 15, 5
    X, Y, Z = [], [], []
    for z in np.linspace(0.0, 1.0, nz):
        for y in np.linspace(0.0, 0.5, ny):
            for x in np.linspace(0.0, 0.8, nx):
                X.append(x)
                Y.append(y)
                Z.append(z)

    X, Y, Z = np.array(X), np.array(Y), np.array(Z)
    n = len(X)

    depth_mm = np.zeros((n, 1, 1))
    amplitude = np.ones((n, 1, 1)) * 4000
    for i in range(n):
        depth_mm[i, 0, 0] = 0.5 + 0.1 * X[i] + 0.02 * Z[i]

    path = "test_data/extract_multiz.npz"
    np.savez(path,
             wavelengths=np.linspace(740, 920, 100),
             X=X, Y=Y, Z=Z, depth_m=(depth_mm) / 1000.0, amplitude=amplitude,
             win_depth_min_m=(np.array([0.3])) / 1000.0,
             win_depth_max_m=(np.array([0.8])) / 1000.0,
             SCHEMA_VERSION="6.0.0",
             SAMPLE_NAME="Extract_MultiZ_Test",
             EXPOSURE_MS=np.float64(4.0),
             M_MEASUREMENTS=np.int32(1),
             DARK_ENABLED=np.bool_(True),
             NONLINEARITY_ENABLED=np.bool_(False),
             SCAN_MODE="snake",
             K_SAMPLES=np.int32(100),
             PROFILE_SAMPLES=np.int32(50),
             N_POINTS_TOTAL=np.int32(n),
             N_POINTS_ACQUIRED=np.int32(n),
             ABORTED=np.bool_(False))
    return OCTDataset.from_file(path)


def test_extract_profile_x():
    """Extraer perfil en X a Y fijo."""
    ds = create_topography_dataset()
    view = TransformedView(ds)

    prof = extract_profile_x(view, y_value=0.3)

    assert prof.is_1d, "Debería ser 1D"
    assert not prof.is_2d, "No debería ser 2D"
    assert prof.n_points == ds.grid.nx, f"Esperado {ds.grid.nx} puntos, got {prof.n_points}"
    assert prof.provenance.extraction_type == ExtractionType.PROFILE_X
    assert len(np.unique(np.round(prof.Y, 6))) == 1, "Y debería ser constante"

    # Verificar que los datos son correctos
    pos, vals = prof.profile_data()
    assert len(pos) == prof.n_points
    assert np.all(np.diff(pos) >= 0), "Posiciones deberían estar ordenadas"

    print(f"  ✓ extract_profile_x: {prof}")


def test_extract_profile_y():
    """Extraer perfil en Y a X fijo."""
    ds = create_topography_dataset()
    prof = extract_profile_y(ds, x_value=0.5)  # Directo desde dataset

    assert prof.is_1d
    assert prof.n_points == ds.grid.ny
    assert prof.provenance.extraction_type == ExtractionType.PROFILE_Y
    assert len(np.unique(np.round(prof.X, 6))) == 1

    pos, vals = prof.profile_data()
    assert np.all(np.diff(pos) >= 0)

    print(f"  ✓ extract_profile_y: {prof}")


def test_extraction_accepts_requested_mm_aliases():
    ds = create_topography_dataset()

    profile_x = extract_profile_x(ds, requested_y_mm=0.3)
    profile_y = extract_profile_y(ds, requested_x_mm=0.5)
    region = extract_region(
        ds,
        requested_x_min_mm=0.2,
        requested_x_max_mm=0.8,
        requested_y_min_mm=0.1,
        requested_y_max_mm=0.5,
    )

    assert profile_x.n_points == ds.grid.nx
    assert profile_y.n_points == ds.grid.ny
    assert region.n_points < ds.n_points


def test_extraction_rejects_conflicting_legacy_and_mm_aliases():
    ds = create_topography_dataset()

    with pytest.raises(ValueError, match="requested_y_mm"):
        extract_profile_x(ds, y_value=0.1, requested_y_mm=0.2)


def test_cut_and_window_apis_accept_canonical_indices_and_coordinates():
    ds = create_topography_dataset()

    window = extract_window(ds, window_index=1)
    cuts = extract_cuts(
        ds,
        requested_x_mm=0.5,
        requested_y_mm=0.3,
        window_index=1,
        measurement_index=0,
    )

    assert window.depth_mm.shape[2] == 1
    assert cuts.requested_x_mm == pytest.approx(0.5)
    assert cuts.requested_y_mm == pytest.approx(0.3)


def test_extraction_rejects_conflicting_zero_aliases():
    ds = create_topography_dataset()

    with pytest.raises(ValueError, match="win_id y window_index no pueden diferir"):
        extract_window(ds, win_id=0, window_index=1)

    with pytest.raises(ValueError, match="win_id y window_index no pueden diferir"):
        extract_profile_x(ds, y_value=0.3, win_id=0, window_index=1)

    with pytest.raises(ValueError, match="win_id y window_index no pueden diferir"):
        extract_cuts(
            ds,
            requested_x_mm=0.5,
            requested_y_mm=0.3,
            win_id=0,
            window_index=1,
        )


def test_extract_window_rejects_negative_index():
    ds = create_topography_dataset()

    with pytest.raises(IndexError, match="Ventana fuera de rango"):
        extract_window(ds, window_index=-1)


def test_extract_profile_with_transforms():
    ds = create_topography_dataset()
    view = TransformedView(ds)
    view.pipeline.add(LevelPlane())
    view.pipeline.add(CenterOrigin())

    prof = extract_profile_x(view, y_value=0.0)

    # Verificar proveniencia incluye transforms
    assert len(prof.provenance.transforms_applied) == 2
    assert "Nivelar plano" in prof.provenance.transforms_applied
    assert "Centrar origen" in prof.provenance.transforms_applied

    print(f"  ✓ extract_profile con transforms: {prof.provenance.transforms_applied}")


def test_extract_region():
    """Extraer sub-región rectangular."""
    ds = create_topography_dataset()
    view = TransformedView(ds)

    reg = extract_region(view, x_min=0.2, x_max=0.8, y_min=0.1, y_max=0.5)

    assert reg.is_2d, "Debería ser 2D"
    assert reg.n_points < ds.n_points, "Debería tener menos puntos"
    assert reg.X.min() >= 0.2
    assert reg.X.max() <= 0.8
    assert reg.Y.min() >= 0.1
    assert reg.Y.max() <= 0.5
    assert reg.provenance.extraction_type == ExtractionType.REGION

    print(f"  ✓ extract_region: {reg} ({ds.n_points} → {reg.n_points} pts)")


def test_extract_z_slice():
    """Extraer un nivel Z de Multi-Z."""
    ds = create_multiz_dataset()

    sl = extract_z_slice(ds, z_value=0.5)

    assert sl.provenance.extraction_type == ExtractionType.Z_SLICE
    assert len(np.unique(np.round(sl.Z, 6))) == 1, "Z debería ser constante"
    # Cada slice tiene nx * ny puntos
    expected = 20 * 15
    assert sl.n_points == expected, f"Esperado {expected}, got {sl.n_points}"

    print(f"  ✓ extract_z_slice: {sl}")


def test_extract_z_slice_fails_on_single_z():
    """Verificar que falla en dataset sin múltiples Z."""
    ds = create_topography_dataset()
    try:
        extract_z_slice(ds, z_value=0.0)
        assert False, "Debería haber lanzado ValueError"
    except ValueError:
        pass
    print("  ✓ extract_z_slice rechaza dataset sin Multi-Z")


def test_extract_window():
    """Extraer una ventana específica."""
    ds = create_topography_dataset()

    w0 = extract_window(ds, win_id=0)
    w1 = extract_window(ds, win_id=1)

    assert w0.depth_mm.shape[2] == 1, "Debería tener 1 ventana"
    assert w1.depth_mm.shape[2] == 1
    assert w0.n_points == ds.n_points, "Misma cantidad de puntos"

    # Verificar que los datos son de ventanas diferentes
    assert not np.allclose(w0.depth_mm, w1.depth_mm), "Las ventanas deberían ser diferentes"

    print(f"  ✓ extract_window: W0={w0}, W1={w1}")


def test_to_export_dict():
    """Verificar que to_export_dict genera formato compatible."""
    ds = create_topography_dataset()
    prof = extract_profile_x(ds, y_value=0.3)

    d = prof.to_export_dict()

    assert {"x_mm", "y_mm", "z_mm", "schema_version"}.issubset(d)
    assert "depth_m" in d
    assert "depth_mm" not in d
    assert d["schema_version"] == "6.0.0"
    assert d["DERIVED_FROM"] == ds.filepath
    assert d["EXTRACTION_TYPE"] == "PROFILE_X"

    # Verificar que se puede guardar como NPZ
    path = "test_data/derived_export.npz"
    np.savez(path, **d)

    # Verificar que se puede re-cargar
    ds2 = OCTDataset.from_file(path)
    assert ds2.n_points == prof.n_points
    assert ds2.dataset_type == DatasetType.PROFILE_1D

    print(f"  ✓ to_export_dict + re-carga: {ds2}")


def test_derived_summary():
    """Verificar que el summary funciona."""
    ds = create_topography_dataset()
    view = TransformedView(ds)
    view.pipeline.add(LevelPlane())

    prof = extract_profile_x(view, y_value=0.3, name="Mi perfil custom")
    s = prof.summary()
    assert "Mi perfil custom" in s
    assert "PROFILE_X" in s
    assert "Nivelar plano" in s

    print(f"  ✓ summary:\n{s}")


def main():
    print("=" * 60)
    print("  TEST: extract")
    print("=" * 60)

    test_extract_profile_x()
    test_extract_profile_y()
    test_extract_profile_with_transforms()
    test_extract_region()
    test_extract_z_slice()
    test_extract_z_slice_fails_on_single_z()
    test_extract_window()
    test_to_export_dict()
    test_derived_summary()

    print("\n" + "=" * 60)
    print("  TODOS LOS TESTS PASARON ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
