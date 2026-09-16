"""Fábricas de transformaciones para tests, usando sólo el registro de plugins."""

from pathlib import Path

from transforms.discovery import discover_plugin_tree


ROOT = Path(__file__).resolve().parents[1]
_REGISTRY = discover_plugin_tree(ROOT / "transforms")


def _plugin(plugin_id, parameters=None):
    return _REGISTRY.create(plugin_id, parameters or {})


def InvertAxis(axis):
    axis = str(axis).upper()
    if axis == "DEPTH":
        return _plugin("invert_depth")
    return _plugin("invert_axis", {"axis": axis})


def Mirror(axis):
    return _plugin("mirror", {"axis": str(axis).upper()})


def Offset(axis, value):
    axis = str(axis).upper()
    if axis == "DEPTH":
        return _plugin("offset_depth", {"offset_mm": value})
    return _plugin("offset_geometry", {"axis": axis, "value_mm": value})


def OffsetMinimumToZero():
    return _plugin("offset_minimum_to_zero")


def MaskDepthRange(minimum_mm, maximum_mm):
    return _plugin(
        "mask_depth_range",
        {"minimum_mm": minimum_mm, "maximum_mm": maximum_mm},
    )


def CenterOrigin():
    return _plugin("center_origin")


def LevelPlane(win_id=0, measurement=0):
    return _plugin("level_plane", {"win_id": win_id, "measurement": measurement})


def FilterMedian(kernel_size=3, win_id=0):
    return _plugin("filter_median", {"kernel_size": kernel_size, "win_id": win_id})


def LevelFromRegions(
    regions,
    win_id=0,
    measurement=0,
    level_z_mm=None,
    level_tolerance_mm=0.002,
):
    return _plugin(
        "level_from_regions",
        {
            "regions_json": __import__("json").dumps(regions),
            "win_id": win_id,
            "measurement": measurement,
            "level_z_mm": 0.0 if level_z_mm is None else level_z_mm,
            "level_tolerance_mm": level_tolerance_mm,
            "n_regions": len(regions),
        },
    )


def CropRegion(x_min=None, x_max=None, y_min=None, y_max=None):
    return _plugin(
        "crop_region",
        {
            "x_min": "" if x_min is None else str(x_min),
            "x_max": "" if x_max is None else str(x_max),
            "y_min": "" if y_min is None else str(y_min),
            "y_max": "" if y_max is None else str(y_max),
        },
    )
