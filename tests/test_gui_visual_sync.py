import numpy as np

from oct_workbench_gui import shared_display_scale, shared_color_limits


def test_shared_display_scale_uses_all_comparison_values():
    scale, unit = shared_display_scale(
        [np.array([0.1, 0.2]), np.array([0.4, np.nan])]
    )

    assert scale == 1000.0
    assert unit == "µm"


def test_shared_color_limits_cover_both_sources():
    minimum, maximum = shared_color_limits(
        [np.array([1.0, 2.0]), np.array([-1.0, np.nan])]
    )

    assert minimum == -1.0
    assert maximum == 2.0
