"""Proporción XY y escala vertical independiente en superficies 3D."""

import numpy as np


def refresh_surface_box_aspect(axis):
    """Mantener X:Y a escala real y mostrar Z con su propia escala visual."""
    x_span = max(abs(np.diff(axis.get_xlim())[0]), 1e-9)
    y_span = max(abs(np.diff(axis.get_ylim())[0]), 1e-9)
    spans = np.array([x_span, y_span, 0.82 * max(x_span, y_span)])
    previous = getattr(axis, "_workbench_visual_box_aspect", None)
    if previous is None or not np.allclose(previous, spans, rtol=1e-9, atol=1e-12):
        axis.set_box_aspect(tuple(spans))
        axis._workbench_visual_box_aspect = spans
    return spans
