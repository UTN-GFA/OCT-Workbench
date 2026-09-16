import numpy as np
import pytest

from work_io.loader import load


def test_loader_rejects_declared_measurement_count_mismatch(tmp_path):
    path = tmp_path / "mismatch.npz"
    np.savez(
        path,
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 0.0]),
        Z=np.array([0.0, 0.0]),
        depth_m=(np.zeros((2, 1, 1))) / 1000.0,
        amplitude=np.ones((2, 1, 1)),
        win_depth_min_m=(np.array([0.3])) / 1000.0,
        win_depth_max_m=(np.array([0.8])) / 1000.0,
        M_MEASUREMENTS=np.int32(2),
    )

    with pytest.raises(ValueError, match="Cardinalidad M inconsistente"):
        load(str(path))


def test_loader_rejects_orphan_profile_axis(tmp_path):
    path = tmp_path / "orphan_profile_axis.npz"
    np.savez(
        path,
        X=np.array([0.0]),
        Y=np.array([0.0]),
        Z=np.array([0.0]),
        profile_depth_m_w0=np.linspace(0.0, 1.0, 4),
    )

    with pytest.raises(ValueError, match="ejes de perfil sin perfiles"):
        load(str(path))


def test_loader_rejects_partial_peak_payload(tmp_path):
    path = tmp_path / "partial_peaks.npz"
    np.savez(
        path,
        X=np.array([0.0]),
        Y=np.array([0.0]),
        Z=np.array([0.0]),
        depth_m=(np.zeros((1, 1, 1))) / 1000.0,
        win_depth_min_m=(np.array([0.3])) / 1000.0,
        win_depth_max_m=(np.array([0.8])) / 1000.0,
    )

    with pytest.raises(ValueError, match="Payload de picos incompleto"):
        load(str(path))


def test_loader_rejects_rank_two_peak_payload(tmp_path):
    path = tmp_path / "rank_two_peaks.npz"
    np.savez(
        path,
        X=np.array([0.0, 1.0]),
        Y=np.array([0.0, 0.0]),
        Z=np.array([0.0, 0.0]),
        depth_m=(np.zeros((2, 1))) / 1000.0,
        amplitude=np.ones((2, 1)),
        win_depth_min_m=(np.array([0.3])) / 1000.0,
        win_depth_max_m=(np.array([0.8])) / 1000.0,
    )

    with pytest.raises(ValueError, match=r"shape \(P, M, N_win\)"):
        load(str(path))


def test_loader_rejects_duplicate_profile_representations(tmp_path):
    path = tmp_path / "duplicate_profile.npz"
    np.savez(
        path,
        X=np.array([0.0]),
        Y=np.array([0.0]),
        Z=np.array([0.0]),
        profile_mod_w0=np.ones((1, 1, 4)),
        profile_real_w0=np.ones((1, 1, 4)),
    )

    with pytest.raises(ValueError, match="representaciones de perfil"):
        load(str(path))
