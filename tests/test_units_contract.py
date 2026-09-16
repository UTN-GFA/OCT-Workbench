import numpy as np
import pytest

from model.surface_assembly import SurfacePatchSpec, assemble_surface_patches
from transforms.base import TransformData


def _unit_data(unit: str) -> TransformData:
    return TransformData(
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 0.0]),
        Z=np.zeros(2),
        depth_mm=np.ones((2, 1, 1)),
        units={"X": unit, "Y": unit, "Z": unit, "depth_mm": unit},
    )


def test_surface_assembly_rejects_incompatible_physical_units():
    with pytest.raises(ValueError, match="Unidades incompatibles"):
        assemble_surface_patches([
            SurfacePatchSpec(data=_unit_data("mm"), source="A"),
            SurfacePatchSpec(data=_unit_data("cm"), source="B"),
        ])
