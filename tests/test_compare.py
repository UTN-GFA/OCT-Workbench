"""
test_compare.py
Tests del módulo de comparación.
"""

import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model.dataset import OCTDataset
from transforms.base import TransformedView
from tests.plugin_transforms import LevelPlane, Offset
from extract import extract_profile_x, extract_region
from extract import DerivedObject, ExtractionType, Provenance
from compare import ComparisonPair
from compare.compatibility import assess_comparison



def test_derived_object_exposes_coordinate_tolerance_from_metadata():
    derived = DerivedObject(
        name="derived",
        X=np.array([0.0]),
        Y=np.array([0.0]),
        Z=np.array([0.0]),
        provenance=Provenance("source", ExtractionType.CUSTOM, {}, []),
        metadata={"position_tolerance_mm": 0.002},
    )

    assert derived.coordinate_tolerance_mm == pytest.approx(0.002)




def test_comparison_rejects_incompatible_depth_mm_units():
    provenance = Provenance("source", ExtractionType.CUSTOM, {}, [])
    common = {
        "X": np.array([0.0]),
        "Y": np.array([0.0]),
        "Z": np.array([0.0]),
        "depth_mm": np.ones((1, 1, 1)),
        "provenance": provenance,
    }
    source_a = DerivedObject(
        name="A", metadata={"units": {"depth_mm": "mm"}}, **common
    )
    source_b = DerivedObject(
        name="B", metadata={"units": {"depth_mm": "cm"}}, **common
    )

    with pytest.raises(ValueError, match="unidades OPD incompatibles"):
        ComparisonPair(source_a, source_b)


def test_alignment_uses_persisted_coordinate_tolerance(tmp_path):
    x = np.array([0.0, 1.0, 0.0, 1.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    z = np.zeros(4)
    depth_mm_a = np.full((4, 1, 1), 0.5)
    depth_mm_b = np.full((4, 1, 1), 0.6)

    common = {
        "wavelengths_nm": np.array([800.0]),
        "win_depth_min_m": np.array([1e-3]),
        "win_depth_max_m": np.array([2e-3]),
        "position_tolerance_mm": np.array(0.002),
        "schema_version": "6.0.0",
        "amplitude": np.ones((4, 1, 1)),
    }
    path_a = tmp_path / "a.npz"
    path_b = tmp_path / "b.npz"
    np.savez(path_a, x_mm=x, y_mm=y, z_mm=z, depth_m=depth_mm_a / 1000.0, **common)
    np.savez(
        path_b,
        x_mm=x + 0.0008,
        y_mm=y - 0.0008,
        z_mm=z,
        depth_m=depth_mm_b / 1000.0,
        **common,
    )

    pair = ComparisonPair(OCTDataset.from_file(path_a), OCTDataset.from_file(path_b))
    stats = pair.statistics()

    assert stats.n_points_common == 4
    assert stats.mean_diff == pytest.approx(-0.1)


def make_topo(sample_name, offset=0.0, noise_std=0.001, path_suffix="a"):
    """Crear topografía sintética con offset y ruido controlados."""
    nx, ny = 30, 20
    X, Y, Z = [], [], []
    for y in np.linspace(0.0, 0.6, ny):
        for x in np.linspace(0.0, 1.0, nx):
            X.append(x)
            Y.append(y)
            Z.append(0.0)

    X, Y, Z = np.array(X), np.array(Y), np.array(Z)
    n = len(X)

    depth_mm = np.zeros((n, 1, 1))
    amplitude = np.ones((n, 1, 1)) * 5000
    for i in range(n):
        surface = 0.5 + 0.1 * X[i] - 0.05 * Y[i]
        depth_mm[i, 0, 0] = surface + offset + np.random.normal(0, noise_std)

    path = f"test_data/compare_{path_suffix}.npz"
    os.makedirs("test_data", exist_ok=True)
    np.savez(path,
             wavelengths=np.linspace(740, 920, 100),
             X=X, Y=Y, Z=Z, depth_m=(depth_mm) / 1000.0, amplitude=amplitude,
             win_depth_min_m=(np.array([0.3])) / 1000.0, win_depth_max_m=(np.array([0.8])) / 1000.0,
             SCHEMA_VERSION="6.0.0", SAMPLE_NAME=sample_name,
             EXPOSURE_MS=np.float64(4.0), M_MEASUREMENTS=np.int32(1),
             DARK_ENABLED=np.bool_(False), NONLINEARITY_ENABLED=np.bool_(False),
             SCAN_MODE="snake", K_SAMPLES=np.int32(100),
             PROFILE_SAMPLES=np.int32(50),
             N_POINTS_TOTAL=np.int32(n), N_POINTS_ACQUIRED=np.int32(n),
             ABORTED=np.bool_(False))
    return OCTDataset.from_file(path)


def test_dataset_vs_dataset():
    """Comparar dos datasets directamente."""
    ds_a = make_topo("Muestra_A", offset=0.0, path_suffix="ds_a")
    ds_b = make_topo("Muestra_B", offset=0.01, path_suffix="ds_b")

    pair = ComparisonPair(ds_a, ds_b)
    stats = pair.statistics()

    # La diferencia media debería ser ~0.01 (el offset)
    assert abs(stats.mean_diff - (-0.01)) < 0.005, \
        f"mean_diff={stats.mean_diff}, esperado ~-0.01"
    assert stats.n_points_common == ds_a.n_points
    assert stats.n_points_common == ds_b.n_points

    canonical_stats = pair.statistics(window_index=0, measurement_index=0)
    canonical_diff = pair.difference(window_index=0, measurement_index=0)
    assert canonical_stats.n_points_common == stats.n_points_common
    assert canonical_diff.n_points == ds_a.n_points

    print(f"  ✓ Dataset vs Dataset")
    print(f"    mean_diff = {stats.mean_diff:.6f} (esperado ~-0.01)")


def test_view_vs_view():
    """Comparar dos views con transformaciones."""
    ds_a = make_topo("View_A", offset=0.0, path_suffix="vw_a")
    ds_b = make_topo("View_B", offset=0.0, path_suffix="vw_b")

    view_a = TransformedView(ds_a)
    view_a.pipeline.add(LevelPlane())

    view_b = TransformedView(ds_b)
    view_b.pipeline.add(LevelPlane())
    view_b.pipeline.add(Offset("DEPTH", 0.05))  # Offset artificial

    pair = ComparisonPair(view_a, view_b)
    stats = pair.statistics()

    # Después de nivelar ambas, la diferencia viene del offset de 0.05
    assert abs(stats.mean_diff - (-0.05)) < 0.005, \
        f"mean_diff={stats.mean_diff}, esperado ~-0.05"

    print(f"  ✓ View vs View (con transforms)")
    print(f"    mean_diff = {stats.mean_diff:.6f} (esperado ~-0.05)")


def test_difference_object():
    """La diferencia retorna un DerivedObject válido."""
    ds_a = make_topo("Diff_A", offset=0.0, noise_std=0.0, path_suffix="diff_a")
    ds_b = make_topo("Diff_B", offset=0.02, noise_std=0.0, path_suffix="diff_b")

    pair = ComparisonPair(ds_a, ds_b)
    diff = pair.difference()

    assert diff.n_points == ds_a.n_points
    assert diff.depth_mm is not None

    # Toda la diferencia debería ser ~-0.02
    z = diff.depth_mm[:, 0, 0]
    assert np.allclose(z, -0.02, atol=0.001), \
        f"diff range: [{z.min():.4f}, {z.max():.4f}]"

    # El DerivedObject debería poder exportarse
    d = diff.to_export_dict()
    assert "DERIVED_FROM" in d
    assert "EXTRACTION_PARAMETERS" in d
    assert "TRANSFORMS_APPLIED" in d
    assert d["schema_version"] == "6.0.0"
    assert "SCHEMA_VERSION" not in d

    print(f"  ✓ difference() → {diff}")


def test_profile_comparison():
    """Comparar perfiles extraídos de dos datasets."""
    ds_a = make_topo("Prof_A", offset=0.0, path_suffix="prof_a")
    ds_b = make_topo("Prof_B", offset=0.03, path_suffix="prof_b")

    pair = ComparisonPair(ds_a, ds_b)
    result = pair.profile_comparison(axis="X", position=0.3)

    assert "pos_a" in result
    assert "z_a" in result
    assert "pos_b" in result
    assert "z_b" in result
    assert len(result["pos_a"]) > 0
    assert len(result["pos_b"]) > 0

    # La diferencia media debería ser ~0.03
    mean_a = np.mean(result["z_a"])
    mean_b = np.mean(result["z_b"])
    assert abs((mean_a - mean_b) - (-0.03)) < 0.01

    print(f"  ✓ profile_comparison: {len(result['pos_a'])} pts A, {len(result['pos_b'])} pts B")


def test_profile_comparison_rejects_invalid_axis_and_indices():
    dataset = make_topo("Invalid_Profile", noise_std=0.0, path_suffix="invalid_profile")
    pair = ComparisonPair(dataset, dataset)

    with pytest.raises(ValueError, match="Eje debe ser"):
        pair.profile_comparison(axis="Z")
    with pytest.raises(IndexError, match="Ventana fuera de rango"):
        pair.profile_comparison(axis="X", win_id=-1)
    with pytest.raises(IndexError, match="Medición fuera de rango"):
        pair.profile_comparison(axis="X", measurement=-1)


def test_assessment_rejects_invalid_selection_like_comparison_pair():
    dataset = make_topo("Assessment_Invalid", noise_std=0.0, path_suffix="assessment_invalid")

    assessment = assess_comparison(
        dataset,
        dataset,
        window_a=-1,
        measurement_a=0,
        window_b=0,
        measurement_b=0,
    )

    assert assessment.status == "not_comparable"
    assert any("ventana" in warning.lower() for warning in assessment.warnings)



def test_derived_vs_derived():
    """Comparar dos DerivedObjects."""
    ds = make_topo("Derived_Src", offset=0.0, path_suffix="der_src")

    reg_a = extract_region(ds, x_min=0.0, x_max=0.5, name="Región izq")
    reg_b = extract_region(ds, x_min=0.0, x_max=0.5, name="Región izq copia")

    pair = ComparisonPair(reg_a, reg_b)
    stats = pair.statistics()

    # Misma región → diferencia ~0
    assert abs(stats.mean_diff) < 0.001
    assert stats.rms_diff < 0.001

    print(f"  ✓ DerivedObject vs DerivedObject: rms_diff={stats.rms_diff:.6f}")


def test_stats_summary():
    """Verificar el summary de estadísticas."""
    ds_a = make_topo("Sum_A", offset=0.0, path_suffix="sum_a")
    ds_b = make_topo("Sum_B", offset=0.005, path_suffix="sum_b")

    pair = ComparisonPair(ds_a, ds_b)
    stats = pair.statistics()
    s = stats.summary()

    assert "Comparación de superficies" in s
    assert "Media" in s
    assert "RMS diff" in s

    print(f"  ✓ stats.summary():\n{s}")


def test_comparison_preserves_depth_axis_kind_and_rejects_mixed_axes(tmp_path):
    common = {
        "x_mm": np.array([0.0, 1.0]),
        "y_mm": np.array([0.0, 0.0]),
        "z_mm": np.array([0.0, 0.0]),
        "amplitude": np.ones((2, 1, 1)),
        "wavelengths_nm": np.array([800.0]),
        "win_depth_min_m": np.array([1e-3]),
        "win_depth_max_m": np.array([2e-3]),
        "schema_version": "6.0.0",
    }
    physical_path = tmp_path / "physical.npz"
    np.savez(
        physical_path,
        **common,
        depth_m=np.full((2, 1, 1), 1e-3),
        depth_axis_kind="physical_depth_mm",
    )
    depth_mm_path = tmp_path / "depth_mm.npz"
    np.savez(
        depth_mm_path,
        **common,
        depth_m=(np.full((2, 1, 1), 1.0)) / 1000.0,
        depth_axis_kind="depth_mm_mm",
    )

    physical_a = OCTDataset.from_file(physical_path)
    physical_b = OCTDataset.from_file(physical_path)
    stats = ComparisonPair(physical_a, physical_b).statistics()

    assert stats.depth_axis_kind == "physical_depth_mm"
    with pytest.raises(ValueError, match="depth_m es incompatible"):
        ComparisonPair(physical_a, OCTDataset.from_file(depth_mm_path))


def test_comparison_rejects_zero_alias_conflict():
    dataset = make_topo("Alias_Zero", noise_std=0.0, path_suffix="alias_zero")
    pair = ComparisonPair(dataset, dataset)

    with pytest.raises(ValueError, match="win_id y window_index no pueden diferir"):
        pair.statistics(win_id=0, window_index=1)


def main():
    print("=" * 60)
    print("  TEST: compare")
    print("=" * 60)

    test_dataset_vs_dataset()
    test_view_vs_view()
    test_difference_object()
    test_profile_comparison()
    test_derived_vs_derived()
    test_stats_summary()

    print("\n" + "=" * 60)
    print("  TODOS LOS TESTS PASARON ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
