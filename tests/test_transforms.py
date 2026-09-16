"""
test_transforms.py
Tests del pipeline de transformaciones no destructivas.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model.dataset import OCTDataset
import transforms as transforms_pkg
from transforms.base import TransformedView
from tests.plugin_transforms import (
    InvertAxis, Mirror, Offset, OffsetMinimumToZero,
    CenterOrigin, LevelPlane, FilterMedian, CropRegion,
)
from transforms.base import TransformData, TransformPipeline



def test_excluded_surface_transforms_are_not_public_api():
    """El filtro gaussiano, outliers y nivelado por media quedan fuera del producto."""
    assert not hasattr(transforms_pkg, "CropOPDRange")
    assert not hasattr(transforms_pkg, "LevelMean")
    assert not hasattr(transforms_pkg, "FilterGaussian")
    assert not hasattr(transforms_pkg, "RemoveOutliers")



def test_pipeline_preserves_units_metadata_and_records_provenance():
    data = TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 0.0]),
        Z=np.array([0.0, 0.0]),
        coordinate_tolerance_mm=0.002,
        units={"X": "mm", "Y": "mm", "Z": "mm", "depth_mm": "mm"},
        metadata={"source_id": "synthetic"},
    )
    pipeline = TransformPipeline()
    pipeline.add(InvertAxis("X"))

    result = pipeline.apply(data)

    assert result.units == data.units
    assert result.metadata == data.metadata
    assert result.coordinate_tolerance_mm == data.coordinate_tolerance_mm
    assert len(result.provenance) == 1
    assert result.provenance[0]["name"] == "Invertir X"
    assert result.provenance[0]["description"] == pipeline.steps[0].description
    assert data.provenance == []


def create_test_dataset() -> OCTDataset:
    """Crear un dataset sintético de topografía para tests."""
    nx, ny = 30, 20
    X, Y, Z = [], [], []
    for y in np.linspace(0.0, 0.6, ny):
        for x in np.linspace(0.0, 1.0, nx):
            X.append(x)
            Y.append(y)
            Z.append(0.0)

    X = np.array(X)
    Y = np.array(Y)
    Z = np.array(Z)
    n = len(X)

    # Superficie: plano inclinado + sinusoide
    depth_mm = np.zeros((n, 1, 1))
    for i in range(n):
        depth_mm[i, 0, 0] = 0.5 + 0.1 * X[i] - 0.05 * Y[i] + 0.01 * np.sin(20 * X[i])

    amplitude = np.ones((n, 1, 1)) * 5000.0

    # Guardar como NPZ temporal
    path = "test_data/transform_test.npz"
    os.makedirs("test_data", exist_ok=True)
    np.savez(path,
             wavelengths=np.linspace(740, 920, 3648),
             X=X, Y=Y, Z=Z,
             depth_m=(depth_mm) / 1000.0, amplitude=amplitude,
             win_depth_min_m=(np.array([0.3])) / 1000.0,
             win_depth_max_m=(np.array([0.8])) / 1000.0,
             SCHEMA_VERSION="6.0.0",
             SOFTWARE_VERSION="test",
             SAMPLE_NAME="Transform_Test",
             EXPOSURE_MS=np.float64(4.0),
             M_MEASUREMENTS=np.int32(1),
             DARK_ENABLED=np.bool_(False),
             NONLINEARITY_ENABLED=np.bool_(False),
             SCAN_MODE="snake",
             K_SAMPLES=np.int32(3648),
             PROFILE_SAMPLES=np.int32(2048),
             N_POINTS_TOTAL=np.int32(n),
             N_POINTS_ACQUIRED=np.int32(n),
             ABORTED=np.bool_(False))
    return OCTDataset.from_file(path)


def test_invert_axis():
    """Test inversión de ejes."""
    ds = create_test_dataset()
    view = TransformedView(ds)

    x_orig = ds.X.copy()
    depth_mm_orig = ds.depth_mm[:, 0, 0].copy()

    # Invertir X
    view.pipeline.add(InvertAxis("X"))
    td = view.transformed_data
    assert np.allclose(td.X, -x_orig), "InvertAxis X falló"

    # Los datos originales no cambian
    assert np.allclose(ds.X, x_orig), "Datos originales modificados!"

    # Invertir OPD
    view2 = TransformedView(ds)
    view2.pipeline.add(InvertAxis("DEPTH"))
    td2 = view2.transformed_data
    assert np.allclose(td2.depth_mm[:, 0, 0], -depth_mm_orig), "InvertAxis OPD falló"

    print("  ✓ InvertAxis")


def test_mirror():
    """Test espejado."""
    ds = create_test_dataset()
    view = TransformedView(ds)

    x_orig = ds.X.copy()
    view.pipeline.add(Mirror("X"))
    td = view.transformed_data

    # Espejado: max + min - valor
    expected = x_orig.max() + x_orig.min() - x_orig
    assert np.allclose(td.X, expected), "Mirror X falló"
    print("  ✓ Mirror")


def test_offset():
    """Test offset."""
    ds = create_test_dataset()
    view = TransformedView(ds)

    view.pipeline.add(Offset("X", 10.0))
    td = view.transformed_data
    assert np.allclose(td.X, ds.X + 10.0), "Offset X falló"

    view2 = TransformedView(ds)
    view2.pipeline.add(Offset("DEPTH", -0.5))
    td2 = view2.transformed_data
    assert np.allclose(td2.depth_mm, ds.depth_mm - 0.5), "Offset OPD falló"
    print("  ✓ Offset")


def test_offset_minimum_to_zero():
    ds = create_test_dataset()
    original = ds.depth_mm.copy()
    view = TransformedView(ds)
    view.pipeline.add(OffsetMinimumToZero())

    transformed = view.transformed_data
    assert np.nanmin(transformed.depth_mm) == 0.0
    assert np.array_equal(ds.depth_mm, original)


def test_center_origin():
    """Test centrar origen."""
    ds = create_test_dataset()
    view = TransformedView(ds)

    view.pipeline.add(CenterOrigin())
    td = view.transformed_data

    cx = (td.X.min() + td.X.max()) / 2
    cy = (td.Y.min() + td.Y.max()) / 2
    assert np.isclose(cx, 0.0, atol=1e-10), f"Centro X = {cx}, esperado 0"
    assert np.isclose(cy, 0.0, atol=1e-10), f"Centro Y = {cy}, esperado 0"
    print("  ✓ CenterOrigin")


def test_level_plane():
    """Test nivelación de plano."""
    ds = create_test_dataset()
    view = TransformedView(ds)

    view.pipeline.add(LevelPlane(win_id=0, measurement=0))
    td = view.transformed_data

    z = td.depth_mm[:, 0, 0]
    # Después de nivelar, la componente lineal debería ser ~0
    A = np.column_stack([td.X, td.Y, np.ones(len(td.X))])
    coeffs, _, _, _ = np.linalg.lstsq(A, z, rcond=None)
    # Los coeficientes del plano deben ser cercanos a cero
    assert abs(coeffs[0]) < 0.01, f"Coeff X = {coeffs[0]}, debería ser ~0"
    assert abs(coeffs[1]) < 0.01, f"Coeff Y = {coeffs[1]}, debería ser ~0"
    print("  ✓ LevelPlane")


def test_crop_region():
    """Test recorte de región."""
    ds = create_test_dataset()
    view = TransformedView(ds)

    view.pipeline.add(CropRegion(x_min=0.2, x_max=0.8, y_min=0.1, y_max=0.5))
    td = view.transformed_data

    assert td.X.min() >= 0.2, f"X min = {td.X.min()}"
    assert td.X.max() <= 0.8, f"X max = {td.X.max()}"
    assert td.Y.min() >= 0.1, f"Y min = {td.Y.min()}"
    assert td.Y.max() <= 0.5, f"Y max = {td.Y.max()}"
    assert td.n_points < ds.n_points, "Crop no redujo puntos"
    print(f"  ✓ CropRegion ({ds.n_points} → {td.n_points} puntos)")


def test_pipeline_cancels_consecutive_self_inverse_geometry_steps():
    ds = create_test_dataset()
    view = TransformedView(ds)

    view.pipeline.add(InvertAxis("X"))
    assert [step.name for step in view.pipeline.steps] == ["Invertir X"]
    view.pipeline.add(InvertAxis("X"))
    assert view.pipeline.is_empty
    assert np.allclose(view.transformed_data.X, ds.X)

    view.pipeline.add(Mirror("Y"))
    view.pipeline.add(Mirror("Y"))
    assert view.pipeline.is_empty


def test_pipeline_stacking():
    """Test apilado de transformaciones."""
    ds = create_test_dataset()
    view = TransformedView(ds)

    # Apilar: nivelar + recortar + centrar
    view.pipeline.add(LevelPlane())
    view.pipeline.add(CropRegion(x_min=0.2, x_max=0.8))
    view.pipeline.add(CenterOrigin())

    print(f"\n{view.pipeline.summary()}")

    td = view.transformed_data

    # Verificar que el pipeline aplica todo
    cx = (td.X.min() + td.X.max()) / 2
    assert np.isclose(cx, 0.0, atol=1e-10), "CenterOrigin no aplicó"
    assert td.n_points < ds.n_points, "CropRegion no aplicó"

    # Undo
    view.pipeline.undo()
    assert len(view.pipeline) == 2
    td2 = view.transformed_data
    cx2 = (td2.X.min() + td2.X.max()) / 2
    assert not np.isclose(cx2, 0.0, atol=0.1), "Undo no deshizo CenterOrigin"

    # Clear
    view.pipeline.clear()
    assert view.pipeline.is_empty
    td3 = view.transformed_data
    assert np.allclose(td3.X, ds.X), "Clear no restauró datos originales"

    print("  ✓ Pipeline stacking + undo + clear")


def test_immutability():
    """Test que el dataset original nunca cambia."""
    ds = create_test_dataset()
    x_orig = ds.X.copy()
    depth_mm_orig = ds.depth_mm.copy()

    view = TransformedView(ds)
    view.pipeline.add(InvertAxis("X"))
    view.pipeline.add(InvertAxis("DEPTH"))
    view.pipeline.add(Offset("X", 100.0))
    view.pipeline.add(LevelPlane())
    view.pipeline.add(CropRegion(x_min=-50))

    # Ejecutar pipeline
    _ = view.transformed_data

    # Verificar inmutabilidad
    assert np.allclose(ds.X, x_orig), "X original modificado!"
    assert np.allclose(ds.depth_mm, depth_mm_orig), "OPD original modificado!"
    print("  ✓ Inmutabilidad del dataset original")


def main():
    print("=" * 60)
    print("  TEST: transforms")
    print("=" * 60)

    test_invert_axis()
    test_mirror()
    test_offset()
    test_offset_minimum_to_zero()
    test_center_origin()
    test_level_plane()
    test_crop_region()
    test_pipeline_stacking()
    test_immutability()

    print("\n" + "=" * 60)
    print("  TODOS LOS TESTS PASARON ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
