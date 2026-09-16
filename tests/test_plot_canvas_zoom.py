from types import SimpleNamespace

import pytest


def test_plot_canvas_has_navigation_toolbar_and_scroll_zoom(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from oct_workbench_gui import PlotCanvas

    app = QApplication.instance() or QApplication([])
    canvas = PlotCanvas()
    assert canvas.toolbar.objectName() == "plotNavigationToolbar"

    axis = canvas.figure.add_subplot(111)
    axis.set_xlim(0.0, 10.0)
    axis.set_ylim(-5.0, 5.0)
    before = axis.get_xlim()
    canvas._on_scroll(SimpleNamespace(inaxes=axis, button="up", xdata=5.0, ydata=0.0))
    after = axis.get_xlim()

    assert (after[1] - after[0]) < (before[1] - before[0])
    canvas.close()
    app.processEvents()


def test_plot_canvas_scroll_zoom_changes_3d_camera_distance(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    from oct_workbench_gui import PlotCanvas

    app = QApplication.instance() or QApplication([])
    canvas = PlotCanvas()
    axis = canvas.figure.add_subplot(111, projection="3d")
    before = float(axis._dist)
    canvas._on_scroll(SimpleNamespace(inaxes=axis, button="up", xdata=0.0, ydata=0.0))

    assert float(axis._dist) < before
    canvas.close()
    app.processEvents()


def test_plot_canvas_toolbar_zoom_preserves_native_3d_z_range_and_view(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from matplotlib.backend_bases import MouseEvent
    from PyQt5.QtWidgets import QApplication
    from oct_workbench_gui import PlotCanvas

    app = QApplication.instance() or QApplication([])
    canvas = PlotCanvas()
    axis = canvas.figure.add_subplot(111, projection="3d")
    axis._workbench_native_surface = True
    axis.set_xlim(0.0, 7.0)
    axis.set_ylim(-10.0, -4.0)
    axis.set_zlim(150.0, 600.0)
    canvas.canvas.draw()
    z_before = axis.get_zlim()
    view_before = (axis.elev, axis.azim, getattr(axis, "roll", 0.0))
    x0, y0, width, height = axis.bbox.bounds

    canvas.toolbar.zoom()
    press = MouseEvent("button_press_event", canvas.canvas, x0 + width * 0.25, y0 + height * 0.25, button=1)
    press.inaxes = axis
    canvas.toolbar.press_zoom(press)
    release = MouseEvent("button_release_event", canvas.canvas, x0 + width * 0.75, y0 + height * 0.75, button=1)
    release.inaxes = axis
    canvas.toolbar.release_zoom(release)

    assert axis.get_zlim() == z_before
    assert (axis.elev, axis.azim, getattr(axis, "roll", 0.0)) == view_before
    assert (axis.get_xlim()[1] - axis.get_xlim()[0]) < 7.0
    canvas.close()
    app.processEvents()
