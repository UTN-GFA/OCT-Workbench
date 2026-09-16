import sys
from pathlib import Path

import numpy as np
import pytest

STATIC_ROOT = Path("/opt/data/workspace/OCT_Static_Software")
if not STATIC_ROOT.is_dir():
    pytest.skip("OCT_Static_Software no disponible", allow_module_level=True)
sys.path.insert(0, str(STATIC_ROOT))

from storage.saver import OCTDataSaver, SaveConfig  # noqa: E402
from model.dataset import OCTDataset  # noqa: E402
from export.exporter import to_h5, to_npz  # noqa: E402


@pytest.mark.parametrize("file_format", ["npz", "h5"])
def test_real_static_saver_schema6_roundtrip(tmp_path, file_format):
    pytest.importorskip("h5py") if file_format == "h5" else None
    metadata = {
        "sample_name": "real-contract",
        "software_version": "OCT Static V6.1",
        "windows": [{"depth_min_m": 1e-3, "depth_max_m": 5e-3}],
        "dark_enabled": True,
        "nonlinearity_enabled": True,
        "optics": {
            "fiber_diameter_um": 5.0,
            "wavelength_nm": 850.0,
            "collimator_focal_length_mm": 18.0,
            "objective_focal_length_mm": 9.0,
        },
        "planned_points": 2,
    }
    save_cfg = SaveConfig(
        save_spectra=True, save_peaks=True, save_profile=True, profile_mode="complex"
    )
    saver = OCTDataSaver()
    saver.open_scan(
        str(tmp_path / f"real.{file_format}"),
        planned_points=2,
        n_pixels=3,
        metadata=metadata,
        save_cfg=save_cfg,
        file_format=file_format,
        measurements_per_point=2,
        wavelengths_nm=np.array([800.0, 850.0, 900.0]),
    )
    for idx, z_mm in enumerate((0.0, 1.0)):
        profiles = [
            {0: np.array([1 + 2j, 2 + 3j, 3 + 4j, 4 + 5j])},
            {0: np.array([5 + 6j, 6 + 7j, 7 + 8j, 8 + 9j])},
        ]
        saver.write_point(
            idx,
            float(idx),
            0.0,
            z_mm,
            spectra=np.ones((2, 3)) * (idx + 1),
            depth_m=np.array([[1e-3], [2e-3]]) + idx * 1e-4,
            amplitude=np.ones((2, 1)) * 10,
            profiles=profiles,
            profile_depth_axes_m={0: np.linspace(1e-3, 4e-3, 4)},
        )

    path = saver.close_scan()
    dataset = OCTDataset.from_file(path)

    assert dataset.m_measurements == 2
    assert np.array_equal(dataset.Z, np.array([0.0, 1.0]))
    assert dataset.optics.d_fiber_um == pytest.approx(5.0)
    assert dataset.optics.wl_nm == pytest.approx(850.0)
    assert dataset.metadata["dark_enabled"] is True
    assert dataset.metadata["nonlinearity_enabled"] is True
    assert dataset.profiles[0].shape == (2, 2, 4)
    assert np.iscomplexobj(dataset.profiles[0])
    assert dataset.profile_depth_axes_m[0].shape == (4,)

    for exporter, suffix in ((to_npz, ".npz"), (to_h5, ".h5")):
        exported = exporter(dataset, str(tmp_path / f"workbench-export{suffix}"))
        reloaded = OCTDataset.from_file(exported)

        if suffix == ".npz":
            with np.load(exported, allow_pickle=False) as payload:
                assert "depth_m" in payload.files
                assert "depth_mm" not in payload.files
                assert "opd" not in payload.files
                assert payload["schema_version"].item() == "6.0.0"

        np.testing.assert_allclose(
            reloaded.depth_mm, dataset.depth_mm, equal_nan=True
        )
        np.testing.assert_allclose(
            reloaded.amplitude, dataset.amplitude, equal_nan=True
        )
        assert reloaded.depth_mm.shape == dataset.depth_mm.shape
        assert reloaded.metadata["dark_enabled"] is True
        assert reloaded.metadata["nonlinearity_enabled"] is True
