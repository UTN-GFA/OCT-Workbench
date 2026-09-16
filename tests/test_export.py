"""
test_export.py
Tests del módulo de exportación.
"""

import sys
import os
from pathlib import Path
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model.dataset import OCTDataset, DatasetType
from transforms.base import TransformedView
from tests.plugin_transforms import LevelPlane
from extract import extract_profile_x, extract_region, extract_window
from compare import ComparisonPair
from export import to_npz, to_npy, to_csv, to_h5, stats_to_csv


def make_dataset(name="Export_Test", path_suffix="exp"):
    nx, ny = 25, 20
    X, Y, Z = [], [], []
    for y in np.linspace(0.0, 0.5, ny):
        for x in np.linspace(0.0, 0.8, nx):
            X.append(x)
            Y.append(y)
            Z.append(0.0)

    X, Y, Z = np.array(X), np.array(Y), np.array(Z)
    n = len(X)
    depth_mm = np.zeros((n, 1, 1))
    amplitude = np.ones((n, 1, 1)) * 4000
    for i in range(n):
        depth_mm[i, 0, 0] = 0.5 + 0.08 * X[i] - 0.03 * Y[i]

    path = f"test_data/export_{path_suffix}.npz"
    os.makedirs("test_data", exist_ok=True)
    np.savez(path,
             wavelengths=np.linspace(740, 920, 100),
             X=X, Y=Y, Z=Z, depth_m=(depth_mm) / 1000.0, amplitude=amplitude,
             win_depth_min_m=(np.array([0.3])) / 1000.0, win_depth_max_m=(np.array([0.8])) / 1000.0,
             SCHEMA_VERSION="6.0.0", SAMPLE_NAME=name,
             EXPOSURE_MS=np.float64(4.0), M_MEASUREMENTS=np.int32(1),
             DARK_ENABLED=np.bool_(False), NONLINEARITY_ENABLED=np.bool_(False),
             SCAN_MODE="snake", K_SAMPLES=np.int32(100),
             PROFILE_SAMPLES=np.int32(50),
             N_POINTS_TOTAL=np.int32(n), N_POINTS_ACQUIRED=np.int32(n),
             ABORTED=np.bool_(False))
    return OCTDataset.from_file(path)


def test_to_npz_dataset():
    """Exportar dataset a NPZ y re-cargar."""
    ds = make_dataset("NPZ_Test", "npz")
    path = to_npz(ds, "test_data/exported_ds.npz")

    assert os.path.exists(path)
    ds2 = OCTDataset.from_file(path)
    assert ds2.n_points == ds.n_points
    assert np.allclose(ds2.depth_mm, ds.depth_mm)
    print(f"  ✓ to_npz(dataset): {ds2}")


def test_to_npz_view():
    """Exportar view transformado a NPZ."""
    ds = make_dataset("NPZ_View", "npz_v")
    view = TransformedView(ds)
    view.pipeline.add(LevelPlane())

    path = to_npz(view, "test_data/exported_view.npz")
    ds2 = OCTDataset.from_file(path)

    # OPD nivelado → media ~0
    mean = np.mean(ds2.depth_mm[:, 0, 0])
    assert abs(mean) < 0.01, f"mean={mean}, esperado ~0"
    print(f"  ✓ to_npz(view): nivelado, mean={mean:.6f}")


def test_to_npz_derived():
    """Exportar DerivedObject a NPZ."""
    ds = make_dataset("NPZ_Der", "npz_d")
    prof = extract_profile_x(ds, y_value=0.25)

    path = to_npz(prof, "test_data/exported_prof")
    assert os.path.exists(path)

    ds2 = OCTDataset.from_file(path)
    assert ds2.dataset_type == DatasetType.PROFILE_1D
    assert ds2.n_points == prof.n_points
    print(f"  ✓ to_npz(derived): {ds2}")


def test_to_csv_dataset():
    """Exportar dataset a CSV."""
    ds = make_dataset("CSV_Test", "csv")
    path = to_csv(ds, "test_data/exported.csv")

    assert os.path.exists(path)

    # Leer y verificar
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    assert data.shape[0] == ds.n_points
    assert data.shape[1] == 5  # X, Y, Z, OPD, Amplitude

    # Verificar header
    with open(path) as f:
        header = f.readline().strip()
    assert "X_mm" in header
    assert "Depth_W0_M0_mm" in header

    print(f"  ✓ to_csv: {data.shape[0]} filas × {data.shape[1]} cols")


def test_to_csv_profile():
    """Exportar perfil a CSV."""
    ds = make_dataset("CSV_Prof", "csv_p")
    prof = extract_profile_x(ds, y_value=0.25)

    path = to_csv(prof, "test_data/exported_prof.csv")
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    assert data.shape[0] == prof.n_points
    with open(path) as handle:
        contents = handle.read()
    assert "# Origen:" in contents
    assert "# Extraccion:" in contents
    assert "# Parametros:" in contents


def test_export_uses_schema6_keys_and_roundtrips_h5(tmp_path):
    ds = make_dataset("Schema6_Export", "schema6")
    npz_path = to_npz(ds, str(tmp_path / "schema6"))
    with np.load(npz_path, allow_pickle=False) as raw:
        assert {"x_mm", "y_mm", "z_mm", "depth_m", "wavelengths_nm", "schema_version"}.issubset(raw.files)
        assert raw["depth_axis_kind"].item() == ds.depth_axis_kind
        assert "depth_m" in raw.files
        assert raw["schema_version"].item() == "6.0.0"
    h5_path = to_h5(ds, str(tmp_path / "schema6"))
    loaded = OCTDataset.from_file(h5_path)
    assert loaded.n_points == ds.n_points
    assert np.allclose(loaded.depth_mm, ds.depth_mm)


def test_h5_roundtrip_preserves_derived_provenance(tmp_path):
    ds = make_dataset("H5_Derived", "h5_derived")
    prof = extract_profile_x(ds, y_value=0.25)
    path = to_h5(prof, str(tmp_path / "derived"))

    loaded = OCTDataset.from_file(path)

    assert loaded.metadata["derived_from"] == prof.provenance.source_file
    assert loaded.metadata["extraction_type"] == prof.provenance.extraction_type.name
    assert "y_value" in loaded.metadata["extraction_parameters"]
    assert loaded.metadata["transforms_applied"] == "[]"


def test_to_npy():
    """Exportar array suelto a NPY."""
    arr = np.random.rand(100, 50)
    path = to_npy(arr, "test_data/my_array")

    assert os.path.exists(path)
    loaded = np.load(path)
    assert np.allclose(loaded, arr)
    print(f"  ✓ to_npy: {arr.shape}")


def test_export_accepts_pathlike_output(tmp_path):
    """Los exportadores deben aceptar pathlib.Path además de str."""
    output = to_npy(np.array([1.0, 2.0]), Path(tmp_path) / "pathlike")
    assert output == str(tmp_path / "pathlike.npy")
    assert np.allclose(np.load(output), [1.0, 2.0])


def test_export_accepts_comparison_pair(tmp_path):
    """Exportar un ComparisonPair debe serializar el resultado A−B."""
    ds_a = make_dataset("Pair_A", "pair_a")
    ds_b = make_dataset("Pair_B", "pair_b")
    pair = ComparisonPair(ds_a, ds_b)

    path = to_npz(pair, tmp_path / "comparison")
    loaded = OCTDataset.from_file(path)

    assert loaded.n_points == ds_a.n_points
    assert loaded.depth_mm is not None
    assert np.allclose(loaded.depth_mm, 0.0)



def test_stats_to_csv():
    """Exportar estadísticas de comparación a CSV."""
    ds_a = make_dataset("Stats_A", "stats_a")
    ds_b = make_dataset("Stats_B", "stats_b")

    pair = ComparisonPair(ds_a, ds_b)
    stats = pair.statistics()

    path = stats_to_csv(stats, "test_data/comparison_stats")
    assert os.path.exists(path)

    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 8  # unidad + header + 6 filas
    assert lines[0].strip() == "# Depth unit: mm"
    assert "mean" in lines[3]

    print(f"  ✓ stats_to_csv: {len(lines)} líneas")


def test_roundtrip_full():
    """Test de ida y vuelta completo: dataset → transform → extract → export → re-load."""
    ds = make_dataset("Roundtrip", "rt")

    # Transform
    view = TransformedView(ds)
    view.pipeline.add(LevelPlane())

    # Extract
    reg = extract_region(view, x_min=0.2, x_max=0.6, y_min=0.1, y_max=0.4)

    # Export
    path = to_npz(reg, "test_data/roundtrip_result")

    # Re-load
    ds2 = OCTDataset.from_file(path)

    assert ds2.n_points == reg.n_points
    assert ds2.dataset_type == DatasetType.TOPOGRAPHY
    assert ds2.grid.nx > 1
    assert ds2.grid.ny > 1

    # Export as CSV too
    csv_path = to_csv(reg, "test_data/roundtrip_result.csv")
    csv_data = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    assert csv_data.shape[0] == reg.n_points

    print(f"  ✓ Roundtrip completo: {ds.n_points} → transform → extract({reg.n_points}) → NPZ → re-load({ds2.n_points})")


def main():
    print("=" * 60)
    print("  TEST: export")
    print("=" * 60)

    test_to_npz_dataset()
    test_to_npz_view()
    test_to_npz_derived()
    test_to_csv_dataset()
    test_to_csv_profile()
    test_to_npy()
    test_stats_to_csv()
    test_roundtrip_full()

    print("\n" + "=" * 60)
    print("  TODOS LOS TESTS PASARON ✓")
    print("=" * 60)


def test_depth_mm_semantics_survive_export_and_reload(tmp_path):
    path = tmp_path / "depth_mm_source.npz"
    np.savez(
        path,
        x_mm=np.array([0.0]),
        y_mm=np.array([0.0]),
        z_mm=np.array([0.0]),
        depth_m=np.array([[[0.05]]]) / 1000.0,
        amplitude=np.ones((1, 1, 1)),
        wavelengths_nm=np.array([800.0]),
        win_depth_min_m=np.array([1e-3]),
        win_depth_max_m=np.array([2e-3]),
        depth_axis_kind="physical_depth_mm",
        schema_version="6.0.0",
    )

    source = OCTDataset.from_file(path)
    assert source.depth_axis_kind == "physical_depth_mm"
    exported = to_npz(source, str(tmp_path / "depth_mm_export"))

    with np.load(exported, allow_pickle=False) as raw:
        assert "depth_m" in raw.files
        assert "depth_mm" not in raw.files
        assert raw["depth_axis_kind"].item() == "physical_depth_mm"

    reloaded = OCTDataset.from_file(exported)
    assert reloaded.depth_axis_kind == "physical_depth_mm"
    assert np.allclose(reloaded.depth_mm, source.depth_mm)


def test_transformed_view_roundtrip_preserves_transform_provenance(tmp_path):
    source = make_dataset(path_suffix="view_roundtrip")
    view = TransformedView(source)
    view.pipeline.add(LevelPlane())
    exported = to_npz(view, str(tmp_path / "transformed_view"))

    reloaded = OCTDataset.from_file(exported)
    assert "Nivelar plano" in reloaded.metadata["transforms_applied"]


def test_derived_window_roundtrip_preserves_window_and_provenance(tmp_path):
    source = make_dataset(path_suffix="derived_roundtrip")
    derived = extract_window(source, window_index=0)
    exported = to_npz(derived, str(tmp_path / "derived_window"))

    reloaded = OCTDataset.from_file(exported)
    assert reloaded.n_windows == 1
    assert reloaded.windows[0].z_min == source.windows[0].z_min
    assert reloaded.windows[0].z_max == source.windows[0].z_max
    assert reloaded.metadata["derived_from"] == source.filepath
    assert reloaded.metadata["extraction_type"] == "WINDOW"
    assert reloaded.metadata["extraction_parameters"]


if __name__ == "__main__":
    main()
