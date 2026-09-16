"""Diálogo para definir parches nativos de una superficie compuesta."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from model.surface_assembly import SurfacePatchSpec


class SurfaceAssemblyDialog(QDialog):
    """Editor de parches A/B con niveles y dominios XY independientes."""

    HEADERS = [
        "Usar", "Fuente", "Nivel Z (mm)", "X mínimo", "X máximo",
        "Y mínimo", "Y máximo", "ΔZ (mm)",
    ]

    def __init__(self, datasets: Dict[str, object], parent=None):
        super().__init__(parent)
        self.datasets = {key.upper(): value for key, value in datasets.items() if value is not None}
        self.setObjectName("modalDialog")
        self.setWindowTitle("Ensamblar superficies nativas")
        self.resize(1120, 560)
        self._rows: List[List[object]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        intro = QLabel(
            "Cada fila define un parche. Se conservan la grilla, el dominio XY y el paso "
            "nativos de cada fuente; no se interpola automáticamente."
        )
        intro.setObjectName("dialogIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        controls = QHBoxLayout()
        add_button = QPushButton("Agregar parche")
        add_button.clicked.connect(lambda: self._add_row())
        controls.addWidget(add_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.setObjectName("modalButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Ok).setDefault(True)
        layout.addWidget(buttons)

        source_keys = list(self.datasets)
        if source_keys:
            self._add_row(source_keys[0])
        if len(source_keys) > 1:
            self._add_row(source_keys[1])

    def _levels(self, source: str):
        dataset = self.datasets[source]
        levels = list(getattr(dataset.volume_layout, "levels", []))
        if levels:
            return [(float(level.z_mm), f"{float(level.z_mm):.9g}") for level in levels]
        return [(float(value), f"{float(value):.9g}") for value in dataset.grid.z_unique if value == value]

    def _bounds(self, source: str):
        dataset = self.datasets[source]
        return (
            float(dataset.X[np.isfinite(dataset.X)].min()),
            float(dataset.X[np.isfinite(dataset.X)].max()),
            float(dataset.Y[np.isfinite(dataset.Y)].min()),
            float(dataset.Y[np.isfinite(dataset.Y)].max()),
        )

    def _spin(self, value, lower=-1e12, upper=1e12):
        spin = QDoubleSpinBox()
        spin.setDecimals(9)
        spin.setRange(lower, upper)
        spin.setValue(float(value))
        return spin

    def _add_row(self, source=None):
        source_keys = list(self.datasets)
        if not source_keys:
            return
        source = source or source_keys[0]
        row = self.table.rowCount()
        self.table.insertRow(row)

        enabled = QCheckBox()
        enabled.setChecked(True)
        self.table.setCellWidget(row, 0, enabled)

        source_combo = QComboBox()
        source_combo.addItems(source_keys)
        source_combo.setCurrentText(source)
        self.table.setCellWidget(row, 1, source_combo)

        level_combo = QComboBox()
        self.table.setCellWidget(row, 2, level_combo)

        x_min, x_max, y_min, y_max = self._bounds(source)
        spins = [
            self._spin(x_min),
            self._spin(x_max),
            self._spin(y_min),
            self._spin(y_max),
            self._spin(0.0),
        ]
        for column, spin in zip(range(3, 8), spins):
            self.table.setCellWidget(row, column, spin)

        self._rows.append([enabled, source_combo, level_combo, *spins])
        source_combo.currentIndexChanged.connect(lambda _index, r=row: self._refresh_row(r))
        self._refresh_row(row)
        self.table.resizeColumnsToContents()

    def _refresh_row(self, row: int):
        if not (0 <= row < len(self._rows)):
            return
        widgets = self._rows[row]
        source = widgets[1].currentText()
        levels = self._levels(source)
        level_combo = widgets[2]
        current = level_combo.currentData()
        level_combo.blockSignals(True)
        level_combo.clear()
        for z_value, label in levels:
            level_combo.addItem(label, z_value)
        if current is not None:
            index = level_combo.findData(current)
            if index >= 0:
                level_combo.setCurrentIndex(index)
        level_combo.blockSignals(False)

        x_min, x_max, y_min, y_max = self._bounds(source)
        for spin, value in zip(widgets[3:7], (x_min, x_max, y_min, y_max)):
            spin.setRange(-1e12, 1e12)
            spin.setValue(value)

    def specifications(self):
        specifications = []
        for widgets in self._rows:
            enabled, source_combo, level_combo = widgets[:3]
            if not enabled.isChecked() or level_combo.currentData() is None:
                continue
            x_min, x_max, y_min, y_max, delta_z = [spin.value() for spin in widgets[3:8]]
            source = source_combo.currentText()
            specifications.append(SurfacePatchSpec(
                data=None,
                source=source,
                name=f"{source} / Nivel {level_combo.currentText()}",
                z_mm=float(level_combo.currentData()),
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
                delta_z_mm=delta_z,
                tolerance_mm=self.datasets[source].coordinate_tolerance_mm,
            ))
        return specifications
