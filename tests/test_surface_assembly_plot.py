import json

import numpy as np
import pytest


def test_surface_assembly_parameters_are_recovered_from_export_metadata():
    from oct_workbench_gui import _surface_assembly_parameters

    metadata = {
        "extraction_parameters": json.dumps(
            {
                "operation": "ensamblado_superficies_nativas",
                "patches": [{"n_points": 4}, {"n_points": 6}],
            }
        )
    }

    params = _surface_assembly_parameters(metadata)

    assert params["operation"] == "ensamblado_superficies_nativas"
    assert [patch["n_points"] for patch in params["patches"]] == [4, 6]


def test_native_patch_grid_does_not_bridge_missing_points():
    from oct_workbench_gui import _native_patch_grid

    x = np.array([0.0, 1.0, 0.0, 1.0])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    values = np.array([10.0, 11.0, 12.0, 13.0])

    grid = _native_patch_grid(x, y, values, tolerance=1e-9)

    assert grid is not None
    x_grid, y_grid, z_grid = grid
    assert x_grid.shape == y_grid.shape == z_grid.shape == (2, 2)
    assert np.allclose(z_grid, [[10.0, 11.0], [12.0, 13.0]])


def test_native_patch_grid_clusters_acquisition_jitter_without_interpolation():
    from oct_workbench_gui import _native_patch_grid

    x = np.array([0.0, 1.0, 0.0004, 1.0003, 0.0002, 0.9998])
    y = np.array([0.0, 0.0003, 0.5, 0.5002, 1.0, 1.0004])
    values = np.arange(6, dtype=float)

    grid = _native_patch_grid(x, y, values, tolerance=0.002)

    assert grid is not None
    assert grid[2].shape == (3, 2)
    assert np.array_equal(np.sort(grid[2].ravel()), values)






def test_native_patch_grid_deduplicates_consistent_jitter_duplicates():
    from oct_workbench_gui import _native_patch_grid

    x = np.array([0.0, 1.0, 0.0003, 1.0002, 0.0001, 1.0001, 0.0002, 1.0003])
    y = np.array([0.0, 0.0002, 0.5001, 0.5000, 1.0002, 1.0001, 0.0003, 0.0004])
    values = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 10.0, 11.0])

    grid = _native_patch_grid(x, y, values, tolerance=0.002)

    assert grid is not None
    assert grid[2].shape == (3, 2)
    assert np.array_equal(np.sort(grid[2].ravel()), np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0]))


def test_native_patch_grid_rejects_conflicting_duplicate_values():
    from oct_workbench_gui import _native_patch_grid

    x = np.array([0.0, 0.0003, 1.0, 1.0002, 0.0, 1.0])
    y = np.array([0.0, 0.0002, 0.0, 0.0001, 1.0, 1.0])
    values = np.array([10.0, 99.0, 11.0, 11.0, 12.0, 13.0])

    assert _native_patch_grid(x, y, values, tolerance=0.002) is None


def test_native_patch_grid_keeps_structured_crop_holes_as_nan():
    from oct_workbench_gui import _native_patch_grid

    x_values = np.array([0.0, 1.0, 2.0])
    y_values = np.array([0.0, 1.0, 2.0, 3.0])
    x, y = np.meshgrid(x_values, y_values)
    values = np.arange(x.size, dtype=float)
    keep = np.ones(values.size, dtype=bool)
    keep[5] = False

    grid = _native_patch_grid(x.ravel()[keep], y.ravel()[keep], values[keep], tolerance=0.002)

    assert grid is not None
    assert grid[2].shape == (4, 3)
    assert np.count_nonzero(~np.isfinite(grid[2])) == 1


def test_native_3d_renderer_keeps_sparse_patches_disconnected():
    from PyQt5.QtWidgets import QApplication
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    from oct_workbench_gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    payloads = [
        ([{
            "name": "inferior",
            "x": np.array([0.0, 0.5, 0.0]),
            "y": np.array([0.0, 0.0, 0.5]),
            "values": np.array([1.0, 1.2, 1.1]),
            "tolerance": 1e-9,
        }, {
            "name": "superior",
            "x": np.array([5.0, 5.5, 5.0]),
            "y": np.array([5.0, 5.0, 5.5]),
            "values": np.array([2.0, 2.2, 2.1]),
            "tolerance": 1e-9,
        }], "A", "viridis")
    ]

    window._draw_3d_native_patches(window.canvas_3d, payloads)

    axis = window.canvas_3d.figure.axes[0]
    assert not any(isinstance(collection, Poly3DCollection) for collection in axis.collections)
    assert axis.collections
    window.close()
    app.processEvents()


def test_native_3d_surface_uses_orthographic_projection_for_zoom_and_pan():
    from PyQt5.QtWidgets import QApplication
    from oct_workbench_gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    payloads = [([
        {
            "name": "superficie",
            "x": np.array([0.0, 1.0, 0.0, 1.0]),
            "y": np.array([0.0, 0.0, 1.0, 1.0]),
            "values": np.array([10.0, 11.0, 12.0, 13.0]),
            "tolerance": 0.002,
        }
    ], "A", "viridis")]

    window._draw_3d_native_patches(window.canvas_3d, payloads)

    axis = window.canvas_3d.figure.axes[0]
    assert np.isinf(axis._focal_length)
    window.close()
    app.processEvents()


def test_native_3d_box_aspect_tracks_navigation_limits():
    from matplotlib.figure import Figure
    from oct_workbench_gui import _refresh_native_3d_box_aspect

    figure = Figure()
    axis = figure.add_subplot(111, projection="3d")
    axis.set_xlim(0.0, 7.0)
    axis.set_ylim(-10.0, -4.0)
    axis.set_zlim(150.0, 600.0)
    axis._workbench_native_surface = True

    _refresh_native_3d_box_aspect(axis)
    before = tuple(axis._workbench_visual_box_aspect)
    axis.set_xlim(-0.5, 3.5)
    axis.set_ylim(-8.7, -6.0)
    _refresh_native_3d_box_aspect(axis)
    after = tuple(axis._workbench_visual_box_aspect)

    assert before != after
    assert after[0] == 4.0
    assert after[1] == pytest.approx(2.7)
    assert after[2] == pytest.approx(0.82 * 4.0)


def test_native_3d_renderer_ignores_nan_values_for_axis_limits():
    from PyQt5.QtWidgets import QApplication
    from oct_workbench_gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    x_values = np.linspace(0.0, 1.0, 5)
    y_values = np.linspace(0.0, 1.0, 5)
    x, y = np.meshgrid(x_values, y_values)
    values = np.arange(x.size, dtype=float)
    values[[12, 18]] = np.nan
    payloads = [([
        {
            "name": "con huecos",
            "x": x.ravel(),
            "y": y.ravel(),
            "values": values,
            "tolerance": 0.002,
        }
    ], "A", "viridis")]

    window._draw_3d_native_patches(window.canvas_3d, payloads)

    axis = window.canvas_3d.figure.axes[0]
    assert np.all(np.isfinite(axis.get_zlim()))
    window.close()
    app.processEvents()


def test_native_patch_grid_preserves_nan_values_when_coordinates_cover_full_grid():
    from oct_workbench_gui import _native_patch_grid

    x_values = np.linspace(0.0, 1.0, 5)
    y_values = np.linspace(0.0, 1.0, 5)
    x, y = np.meshgrid(x_values, y_values)
    values = np.arange(x.size, dtype=float)
    values[[12, 18]] = np.nan

    grid = _native_patch_grid(x.ravel(), y.ravel(), values, tolerance=0.002)

    assert grid is not None
    assert grid[2].shape == (5, 5)
    assert np.count_nonzero(~np.isfinite(grid[2])) == 2


def test_native_patch_grid_keeps_boundary_row_from_rectangular_crop():
    from oct_workbench_gui import _native_patch_grid

    x_values = np.linspace(0.0, 1.0, 11)
    y_values = np.linspace(-8.0, -5.0, 61)
    x, y = np.meshgrid(x_values, y_values)
    values = np.arange(x.size, dtype=float)
    keep = np.ones(values.size, dtype=bool)
    keep[-11::2] = False

    grid = _native_patch_grid(x.ravel()[keep], y.ravel()[keep], values[keep], tolerance=0.002)

    assert grid is not None
    assert grid[2].shape == (61, 11)
    assert np.count_nonzero(~np.isfinite(grid[2])) == 6
