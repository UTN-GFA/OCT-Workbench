"""Diálogo Qt para seleccionar Niveles de una Muestra/medición."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from model.level_assembly import LevelSelection


class LevelAssemblyDialog(QDialog):
    """Editor de selección por Nivel y desplazamiento físico ΔZ."""

    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self.setWindowTitle("Ensamblar Niveles → Muestra derivada")
        self.resize(980, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Seleccione los Niveles y sus Medidas/Puntos. Los límites X/Y se aplican "
            "de forma independiente a cada Nivel."
        ))
        self.table = QTableWidget(dataset.volume_layout.n_levels, 7)
        self.table.setHorizontalHeaderLabels([
            "Usar", "Nivel Z (mm)", "X mínimo", "X máximo",
            "Y mínimo", "Y máximo", "ΔZ (mm)",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self._widgets = []
        x_min, x_max = float(dataset.X.min()), float(dataset.X.max())
        y_min, y_max = float(dataset.Y.min()), float(dataset.Y.max())
        for row, level in enumerate(dataset.volume_layout.levels):
            enabled = QCheckBox()
            enabled.setChecked(True)
            self.table.setCellWidget(row, 0, enabled)
            z_item = QTableWidgetItem(f"{level.z_mm:.9g}")
            z_item.setFlags(z_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, z_item)
            row_widgets = [enabled]
            for column, value, lower, upper in (
                (2, x_min, x_min, x_max),
                (3, x_max, x_min, x_max),
                (4, y_min, y_min, y_max),
                (5, y_max, y_min, y_max),
                (6, 0.0, -1e9, 1e9),
            ):
                spin = QDoubleSpinBox()
                spin.setDecimals(6)
                spin.setRange(lower, upper)
                spin.setValue(value)
                self.table.setCellWidget(row, column, spin)
                row_widgets.append(spin)
            self._widgets.append(row_widgets)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selections(self):
        selections = []
        for row, level in enumerate(self.dataset.volume_layout.levels):
            widgets = self._widgets[row]
            selections.append(LevelSelection(
                z_mm=float(level.z_mm),
                x_min=widgets[1].value(),
                x_max=widgets[2].value(),
                y_min=widgets[3].value(),
                y_max=widgets[4].value(),
                delta_z_mm=widgets[5].value(),
                enabled=widgets[0].isChecked(),
                tolerance_mm=self.dataset.coordinate_tolerance_mm,
            ))
        return selections
