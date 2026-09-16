"""Estado de navegación y visualización compartido por las vistas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SourceDisplayState:
    """Selección visual independiente de una fuente A o B."""

    level_index: int = 0
    window_id: int = 0
    measurement: int = 0
    depth_min_mm: Optional[float] = None
    depth_max_mm: Optional[float] = None
    depth_offset_mm: float = 0.0
    invert_depth: bool = False
    cut_x_mm: Optional[float] = None
    cut_y_mm: Optional[float] = None
    excluded_levels: frozenset[int] = field(default_factory=frozenset)

    @property
    def window_index(self) -> int:
        return self.window_id

    @window_index.setter
    def window_index(self, value: int) -> None:
        self.window_id = int(value)

    @property
    def measurement_index(self) -> int:
        return self.measurement

    @measurement_index.setter
    def measurement_index(self, value: int) -> None:
        self.measurement = int(value)


@dataclass
class DisplayState:
    """Estado común de las seis pestañas y de la sincronización A/B."""

    source_a: SourceDisplayState = field(default_factory=SourceDisplayState)
    source_b: SourceDisplayState = field(default_factory=SourceDisplayState)
    shared_level: bool = False
    shared_window: bool = False
    shared_measurement: bool = False
    shared_color_range: bool = True
    histogram_bins: int = 50
    cut_axis: str = "X"
    active_source: str = "A"

    def source(self, slot: str) -> SourceDisplayState:
        normalized = str(slot).upper()
        if normalized == "A":
            return self.source_a
        if normalized == "B":
            return self.source_b
        raise ValueError(f"Fuente inválida: {slot}")

    def set_level(self, slot: str, level_index: int) -> None:
        if int(level_index) < 0:
            raise ValueError("El nivel no puede ser negativo")
        self.source(slot).level_index = int(level_index)

    def exclude_level(self, slot: str, level_index: int) -> None:
        state = self.source(slot)
        if int(level_index) < 0:
            raise ValueError("El nivel no puede ser negativo")
        state.excluded_levels = state.excluded_levels | {int(level_index)}

    def restore_level(self, slot: str, level_index: int) -> None:
        state = self.source(slot)
        state.excluded_levels = state.excluded_levels - {int(level_index)}

    def set_cut(self, slot: str, x_mm: Optional[float], y_mm: Optional[float]) -> None:
        state = self.source(slot)
        state.cut_x_mm = x_mm
        state.cut_y_mm = y_mm

    def set_filter(
        self,
        slot: str,
        minimum_mm: Optional[float],
        maximum_mm: Optional[float],
        offset_mm: float = 0.0,
        invert: bool = False,
    ) -> None:
        if minimum_mm is not None and maximum_mm is not None and minimum_mm > maximum_mm:
            raise ValueError("El mínimo OPD no puede ser mayor que el máximo")
        state = self.source(slot)
        state.depth_min_mm = minimum_mm
        state.depth_max_mm = maximum_mm
        state.depth_offset_mm = float(offset_mm)
        state.invert_depth = bool(invert)
