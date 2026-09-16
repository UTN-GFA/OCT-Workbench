"""Compatibilidad entre dos selecciones A/B."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from model.dataset import OCTDataset


@dataclass(frozen=True)
class ComparisonAssessment:
    """Estado explícito de compatibilidad para comparación visual/perfil."""

    status: str
    warnings: tuple[str, ...]


def assess_comparison(
    dataset_a: OCTDataset,
    dataset_b: OCTDataset,
    *,
    window_a: int,
    measurement_a: int,
    window_b: int,
    measurement_b: int,
    offset_a: float = 0.0,
    offset_b: float = 0.0,
) -> ComparisonAssessment:
    """Evaluar compatibilidad sin asumir igualdad de índices físicos."""
    warnings: list[str] = []
    invalid_selection = False
    if not 0 <= window_a < dataset_a.n_windows or not 0 <= window_b < dataset_b.n_windows:
        warnings.append("La ventana seleccionada no existe en uno de los datasets")
        invalid_selection = True
    if not 0 <= measurement_a < dataset_a.m_measurements or not 0 <= measurement_b < dataset_b.m_measurements:
        warnings.append("La medición seleccionada no existe en uno de los datasets")
        invalid_selection = True
    if invalid_selection:
        return ComparisonAssessment("not_comparable", tuple(warnings))
    if not np.isclose(float(offset_a), float(offset_b)):
        warnings.append("A y B tienen distinto offset; la comparación no es válida")
        return ComparisonAssessment("not_comparable", tuple(warnings))
    if (window_a, measurement_a) != (window_b, measurement_b):
        warnings.append(
            "A y B usan índices de ventana/medición distintos; "
            "verificar equivalencia física"
        )
    if dataset_a.dataset_type != dataset_b.dataset_type:
        warnings.append("A y B no son del mismo tipo de barrido")
    if dataset_a.grid.nx != dataset_b.grid.nx or dataset_a.grid.ny != dataset_b.grid.ny:
        warnings.append("Las dimensiones de la grilla no coinciden")
    tolerance = max(dataset_a.coordinate_tolerance_mm, dataset_b.coordinate_tolerance_mm)
    if not _range_close(dataset_a.grid.x_range, dataset_b.grid.x_range, tolerance):
        warnings.append("El rango X de A y B no coincide")
    if not _range_close(dataset_a.grid.y_range, dataset_b.grid.y_range, tolerance):
        warnings.append("El rango Y de A y B no coincide")
    if not _range_close(dataset_a.grid.z_range, dataset_b.grid.z_range, tolerance):
        warnings.append("El rango Z de A y B no coincide")
    if not _same_coordinates(dataset_a, dataset_b, tolerance):
        warnings.append("Las coordenadas no coinciden punto a punto")
    status = "compatible_with_warning" if warnings else "compatible"
    return ComparisonAssessment(status, tuple(dict.fromkeys(warnings)))


def _same_coordinates(dataset_a: OCTDataset, dataset_b: OCTDataset, tolerance: float) -> bool:
    return (
        dataset_a.X.shape == dataset_b.X.shape
        and dataset_a.Y.shape == dataset_b.Y.shape
        and dataset_a.Z.shape == dataset_b.Z.shape
        and np.allclose(dataset_a.X, dataset_b.X, rtol=0.0, atol=tolerance, equal_nan=True)
        and np.allclose(dataset_a.Y, dataset_b.Y, rtol=0.0, atol=tolerance, equal_nan=True)
        and np.allclose(dataset_a.Z, dataset_b.Z, rtol=0.0, atol=tolerance, equal_nan=True)
    )


def _range_close(a: tuple[float, float], b: tuple[float, float], tolerance: float) -> bool:
    return bool(np.allclose(a, b, rtol=0.0, atol=tolerance))
