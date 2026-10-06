"""GUI principal del OCT Workbench.

Roadmap documentado:
- Etapa 1: visualización y comparación de mediciones 1D/2D/3D.
- Etapa 2: correcciones y preparación reversibles.
- Fuera de alcance: análisis científicos específicos de muestra, instrumento o aplicación.
- Etapa 4: exportación y persistencia reproducible.

Alcance actual: Etapa 1 — visualización y comparación 1D/2D/3D, y
correcciones reversibles básicas de Etapa 2. Las etapas se documentan aquí,
no en el nombre del archivo, para mantener una entrada estable del programa.
"""

from __future__ import annotations

import os
import json
from dataclasses import replace
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt, QRect, QSize, QLocale, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import matplotlib
matplotlib.use("Qt5Agg")
matplotlib.rcParams["axes.formatter.use_locale"] = False
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from compare import ComparisonAssessment
from gui.display_state import DisplayState
from gui.aspect import refresh_surface_box_aspect
from extract.operations import extract_profile_x, extract_profile_y
from export.exporter import to_csv, to_h5, to_npz, to_png
from gui.metadata import MetadataComparison, build_metadata_comparison, quality_summary
from compare import ComparisonPair
from model.dataset import OCTDataset
from model.level_assembly import assemble_levels, derived_from_assembly
from model.surface_assembly import (
    SurfacePatchSpec,
    assemble_surface_patches,
    derived_from_surface_assembly,
)
from model.volume import VolumeLayout, _cluster_axis, select_volume_slice
from gui.level_assembly_dialog import LevelAssemblyDialog
from gui.surface_assembly_dialog import SurfaceAssemblyDialog
from transforms.base import TransformedView
from transforms.discovery import discover_plugin_tree
from transforms.plugin_api import PluginTransform, PluginValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]



class FlowLayout(QLayout):
    """Layout que reacomoda widgets en filas según el ancho disponible."""

    def __init__(self, parent=None, horizontal_spacing=6, vertical_spacing=6, alignment=Qt.AlignLeft):
        super().__init__(parent)
        self._items = []
        self._horizontal_spacing = horizontal_spacing
        self._vertical_spacing = vertical_spacing
        self._alignment = alignment

    def addItem(self, item: QLayoutItem):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, max(0, width), 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        visible = self._visible_items()
        if not visible:
            return self.minimumSize()
        margins = self.contentsMargins()
        width = sum(item.sizeHint().width() for item in visible)
        width += self._horizontal_spacing * max(0, len(visible) - 1)
        height = max(item.sizeHint().height() for item in visible)
        return QSize(
            width + margins.left() + margins.right(),
            height + margins.top() + margins.bottom(),
        )

    def minimumSize(self):
        size = QSize(0, 0)
        for item in self._visible_items():
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _visible_items(self):
        return [
            item
            for item in self._items
            if item.widget() is None or not item.widget().isHidden()
        ]

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        if effective.width() <= 0:
            return margins.top() + margins.bottom()

        lines = []
        current = []
        current_width = 0
        current_height = 0
        for item in self._visible_items():
            hint = item.sizeHint()
            proposed_width = hint.width() if not current else current_width + self._horizontal_spacing + hint.width()
            if current and proposed_width > effective.width():
                lines.append((current, current_width, current_height))
                current = []
                current_width = 0
                current_height = 0
            current.append(item)
            current_width = hint.width() if current_width == 0 else current_width + self._horizontal_spacing + hint.width()
            current_height = max(current_height, hint.height())
        if current:
            lines.append((current, current_width, current_height))

        y = effective.y()
        for items, line_width, line_height in lines:
            extra = max(0, effective.width() - line_width)
            if self._alignment & Qt.AlignRight:
                offset = extra
            elif self._alignment & Qt.AlignHCenter:
                offset = extra // 2
            else:
                offset = 0
            x = effective.x() + offset
            for item in items:
                hint = item.sizeHint()
                if not test_only:
                    item.setGeometry(QRect(x, y, hint.width(), hint.height()))
                x += hint.width() + self._horizontal_spacing
            y += line_height + self._vertical_spacing

        if not lines:
            return margins.top() + margins.bottom()
        return y - effective.y() - self._vertical_spacing + margins.top() + margins.bottom()


def _surface_assembly_parameters(metadata):
    """Recuperar parámetros serializados de una superficie compuesta."""
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("extraction_parameters", {})
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    if not isinstance(raw, dict):
        return None
    if raw.get("operation") != "ensamblado_superficies_nativas":
        return None
    patches = raw.get("patches")
    if not isinstance(patches, list):
        return None
    return raw


def _native_patch_grid(x, y, values, tolerance=1e-9):
    """Construir una grilla nativa tolerante a jitter y duplicados consistentes."""
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    values = np.asarray(values, dtype=float).ravel()
    finite_coordinates = np.isfinite(x) & np.isfinite(y)
    x, y, values = x[finite_coordinates], y[finite_coordinates], values[finite_coordinates]
    if not x.size:
        return None
    tolerance = max(float(tolerance), 1e-9)
    x_unique, _ = _cluster_axis(x, tolerance)
    y_unique, _ = _cluster_axis(y, tolerance)
    if x_unique.size < 2 or y_unique.size < 2:
        return None
    expected = int(x_unique.size * y_unique.size)
    grid = np.full((y_unique.size, x_unique.size), np.nan, dtype=float)
    coordinate_present = np.zeros_like(grid, dtype=bool)
    for x_value, y_value, value in zip(x, y, values):
        xi = int(np.argmin(np.abs(x_unique - x_value)))
        yi = int(np.argmin(np.abs(y_unique - y_value)))
        if abs(x_unique[xi] - x_value) > tolerance or abs(y_unique[yi] - y_value) > tolerance:
            return None
        coordinate_present[yi, xi] = True
        if not np.isfinite(value):
            continue
        if np.isfinite(grid[yi, xi]):
            # Una muestra derivada antigua puede haber repetido el mismo
            # nodo al reconstruir ejes con jitter. Sólo se deduplica si el
            # valor físico coincide; conflictos reales siguen rechazados.
            if not np.isclose(grid[yi, xi], value, rtol=1e-9, atol=1e-12):
                return None
            continue
        grid[yi, xi] = value
    missing_coordinates = ~coordinate_present
    if missing_coordinates.any():
        # Un recorte puede quitar algunos nodos de una grilla regular. Se
        # conserva el hueco como NaN sólo si todavía hay evidencia de una
        # malla estructurada; nubes pequeñas/triángulos siguen como puntos.
        if x_unique.size < 3 or y_unique.size < 3:
            return None
        occupancy = float(np.count_nonzero(coordinate_present)) / float(expected)
        if occupancy < 0.90:
            return None
        missing_indices = np.argwhere(missing_coordinates)
        boundary_missing = (
            (missing_indices[:, 0] == 0)
            | (missing_indices[:, 0] == y_unique.size - 1)
            | (missing_indices[:, 1] == 0)
            | (missing_indices[:, 1] == x_unique.size - 1)
        )
        if not np.all(boundary_missing):
            return None
    return np.meshgrid(x_unique, y_unique)[0], np.meshgrid(x_unique, y_unique)[1], grid


def _refresh_native_3d_box_aspect(axis):
    """Mantener X:Y a escala y Z independiente tras zoom o redibujado."""
    if not getattr(axis, "_workbench_surface_aspect", False):
        return None
    return refresh_surface_box_aspect(axis)


class WorkbenchNavigationToolbar(NavigationToolbar2QT):
    """Toolbar Matplotlib con zoom 3D no destructivo para superficies nativas."""

    def release_zoom(self, event):
        if self._zoom_info is None:
            return
        protected = {
            axis: (axis.get_zlim(), axis.elev, axis.azim, getattr(axis, "roll", 0.0))
            for axis in self._zoom_info.axes
            if getattr(axis, "_workbench_native_surface", False)
        }
        super().release_zoom(event)
        for axis, (zlim, elev, azim, roll) in protected.items():
            axis.set_zlim(*zlim)
            axis.elev = elev
            axis.azim = azim
            axis.roll = roll
        if protected:
            self.canvas.draw_idle()


class PlotCanvas(QWidget):
    """Canvas reutilizable para las vistas del Workbench, con navegación."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(8, 5))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.toolbar = WorkbenchNavigationToolbar(self.canvas, self)
        self.toolbar.setObjectName("plotNavigationToolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("draw_event", self._on_draw)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)

    def _on_draw(self, _event):
        for axis in self.figure.axes:
            _refresh_native_3d_box_aspect(axis)

    def _on_scroll(self, event):
        """Zoom con rueda, centrado en el cursor y compatible con 2D/3D."""
        axis = getattr(event, "inaxes", None)
        button = getattr(event, "button", None)
        if axis is None or button not in {"up", "down"}:
            return
        factor = 0.80 if button == "up" else 1.25
        if hasattr(axis, "get_zlim"):
            # Matplotlib actual mantiene la distancia de cámara en _dist;
            # no existe una API pública equivalente para el zoom de Axes3D.
            current = float(getattr(axis, "_dist", 10.0))
            axis._dist = float(np.clip(current * factor, 2.0, 40.0))
            self.canvas.draw_idle()
            return
        if getattr(event, "xdata", None) is None or getattr(event, "ydata", None) is None:
            return
        x_center = float(event.xdata)
        y_center = float(event.ydata)
        x_min, x_max = axis.get_xlim()
        y_min, y_max = axis.get_ylim()
        x_half = 0.5 * (x_max - x_min) * factor
        y_half = 0.5 * (y_max - y_min) * factor
        axis.set_xlim(x_center - x_half, x_center + x_half)
        axis.set_ylim(y_center - y_half, y_center + y_half)
        self.canvas.draw_idle()


class MetadataDialog(QDialog):
    """Ventana de metadata A o comparación A/B."""

    def __init__(self, dataset_a: OCTDataset, dataset_b: Optional[OCTDataset], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadata de las mediciones")
        self.resize(980, 600)
        comparison = build_metadata_comparison(dataset_a, dataset_b)

        layout = QVBoxLayout(self)
        title = QLabel("Comparación de metadata" if dataset_b else "Metadata de la muestra A")
        title.setStyleSheet("color: #263342; font-size: 16px; font-weight: bold; padding: 2px 0 6px 0;")
        layout.addWidget(title)

        status = QLabel(self._compatibility_text(comparison))
        status.setWordWrap(True)
        status.setStyleSheet(self._compatibility_style(comparison))
        layout.addWidget(status)

        quality_layout = QHBoxLayout()
        quality_layout.addWidget(self._quality_label("A", dataset_a))
        if dataset_b is not None:
            quality_layout.addWidget(self._quality_label("B", dataset_b))
        layout.addLayout(quality_layout)

        columns = 4 if dataset_b else 2
        headers = ["Campo", "A", "B", "Estado"] if dataset_b else ["Campo", "Valor"]
        table = QTableWidget(len(comparison.rows), columns)
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(False)
        table.setWordWrap(False)
        table.setShowGrid(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setStyleSheet("""
            QTableWidget {
                background: #252b34;
                color: #f2f4f7;
                gridline-color: #596574;
                selection-background-color: #466b8d;
                selection-color: #ffffff;
            }
            QTableWidget::item {
                background: #252b34;
                color: #f2f4f7;
                padding: 7px;
            }
            QTableWidget::viewport {
                background: #252b34;
            }
            QHeaderView {
                background: #3c4b5b;
            }
            QHeaderView::section {
                background: #3c4b5b;
                color: #ffffff;
                padding: 8px;
                font-weight: bold;
                border: 1px solid #596574;
            }
            QTableCornerButton::section {
                background: #3c4b5b;
                border: 1px solid #596574;
            }
        """)
        table.verticalHeader().setDefaultSectionSize(34)

        for row_index, row in enumerate(comparison.rows):
            table.setItem(row_index, 0, QTableWidgetItem(row.label))
            table.setItem(row_index, 1, QTableWidgetItem(_display(row.value_a)))
            if dataset_b:
                table.setItem(row_index, 2, QTableWidgetItem(_display(row.value_b)))
                state = "Igual" if row.same else "Diferente"
                table.setItem(row_index, 3, QTableWidgetItem(state))
                if not row.same:
                    for col in range(columns):
                        table.item(row_index, col).setBackground(Qt.yellow)
                        table.item(row_index, col).setForeground(Qt.black)
        if dataset_b:
            table.setColumnWidth(0, 220)
            table.setColumnWidth(1, 220)
            table.setColumnWidth(2, 220)
            table.setColumnWidth(3, 120)
            table.horizontalHeader().setStretchLastSection(True)
        else:
            table.setColumnWidth(0, 220)
            table.horizontalHeader().setStretchLastSection(True)
        table.resizeRowsToContents()
        layout.addWidget(table, 1)

        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, 0, Qt.AlignRight)

    @staticmethod
    def _quality_label(label: str, dataset: OCTDataset) -> QLabel:
        quality = quality_summary(dataset)
        acquired = "—" if quality.acquired_points is None else str(quality.acquired_points)
        expected = "—" if quality.expected_points is None else str(quality.expected_points)
        aborted = "Sí" if quality.scan_aborted else "No"
        text = (
            f"<b>Calidad {label}</b><br>"
            f"Puntos: {quality.total_points} · coordenadas válidas: {quality.finite_coordinate_points}<br>"
            f"OPD válidos: {quality.valid_depth_mm_points}/{quality.total_depth_mm_points} "
            f"({quality.depth_mm_valid_percent:.1f} %) · NaN: {quality.nan_depth_mm_points}<br>"
            f"Amplitud válida: {quality.valid_amplitude_points}/{quality.total_amplitude_points} "
            f"({quality.amplitude_valid_percent:.1f} %) · adquiridos/esperados: {acquired}/{expected}<br>"
            f"Barrido abortado: {aborted}"
        )
        result = QLabel(text)
        result.setWordWrap(True)
        result.setStyleSheet("background: #e8edf2; color: #263342; padding: 8px; border-radius: 4px;")
        return result

    @staticmethod
    def _compatibility_text(comparison: MetadataComparison) -> str:
        if not comparison.has_b:
            return "Información completa disponible para la muestra A."
        if comparison.compatible_for_pointwise:
            return "✓ A y B son compatibles para comparación visual y punto a punto."
        warnings = "\n".join(f"• {warning}" for warning in comparison.warnings)
        return "⚠ Comparación visual disponible; la comparación punto a punto requiere revisar:\n" + warnings

    @staticmethod
    def _compatibility_style(comparison: MetadataComparison) -> str:
        if comparison.compatible_for_pointwise or not comparison.has_b:
            return "color: #207a3c; padding: 8px;"
        return "color: #8a5a00; padding: 8px;"


class ComparisonDialog(QDialog):
    """Resultado compacto de comparación: sólo métricas de A − B."""

    def __init__(self, stats, on_create_difference, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comparación A − B")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        title = QLabel("Métricas de la diferencia punto a punto A − B")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        text = (
            f"Puntos comunes: {stats.n_points_common}\n"
            f"Unidad OPD: {stats.depth_mm_unit}\n\n"
            f"Media (A − B): {stats.mean_diff:.9g}\n"
            f"STD (A − B): {stats.std_diff:.9g}\n"
            f"Pico-Valle (A − B): {stats.pv_diff:.9g}\n"
            f"RMS (A − B): {stats.rms_diff:.9g}\n"
            f"Máx |A − B|: {stats.max_abs_diff:.9g}"
        )
        value = QLabel(text)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value.setStyleSheet("font-family: monospace; padding: 8px;")
        layout.addWidget(value)
        create_button = QPushButton("Crear objeto derivado A − B")
        create_button.clicked.connect(on_create_difference)
        layout.addWidget(create_button)
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, 0, Qt.AlignRight)


class ExportDialog(QDialog):
    """Selector contextual de formato y fuente para exportación."""

    def __init__(self, tab_name: str, formats, sources, parent=None):
        super().__init__(parent)
        self.setObjectName("modalDialog")
        self.setWindowTitle(f"Exportar — {tab_name}")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        intro = QLabel(
            f"Exportación contextual de {tab_name}. "
            "La vista activa se exporta como imagen; los datos se exportan desde la fuente seleccionada."
        )
        intro.setObjectName("dialogIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.format_combo = QComboBox()
        self.format_combo.addItems(formats)
        self.source_combo = QComboBox()
        for label, source in sources:
            self.source_combo.addItem(label, source)
        form.addRow("Formato:", self.format_combo)
        form.addRow("Fuente:", self.source_combo)
        layout.addLayout(form)

        self.source_combo.setEnabled(bool(sources))
        if not sources:
            self.source_combo.addItem("Sin datos cargados")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.setObjectName("modalButtons")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Ok).setDefault(True)
        layout.addWidget(buttons)

    @property
    def selected_format(self) -> str:
        return self.format_combo.currentText()

    @property
    def selected_source(self):
        return self.source_combo.currentData()


class PipelineHistoryDialog(QDialog):
    """Historial seleccionable de procesos de una muestra."""

    rewind_requested = pyqtSignal(int)
    restore_requested = pyqtSignal()

    def __init__(self, slot: str, view: Optional[TransformedView], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Historial de procesos — Muestra {slot.upper()}")
        self.resize(720, 440)

        layout = QVBoxLayout(self)
        self.history_list = QListWidget()
        self.history_list.setStyleSheet(
            "QListWidget { background: #f5f6f8; color: #20242a; "
            "border: 1px solid #9aa6b2; padding: 6px; }"
            "QListWidget::item:selected { background: #2f80d0; color: #ffffff; }"
        )
        if view is None or view.pipeline.is_empty:
            self.history_list.addItem("No hay procesos aplicados. La muestra conserva sus datos originales.")
        else:
            for index, step in enumerate(view.pipeline.steps, start=1):
                self.history_list.addItem(f"{index}. {step.name}: {step.description}")
        layout.addWidget(self.history_list)

        actions = QHBoxLayout()
        self.rewind_button = QPushButton("Volver a este punto")
        self.rewind_button.setEnabled(False)
        self.rewind_button.clicked.connect(self._request_rewind)
        self.restore_button = QPushButton("Restaurar original")
        self.restore_button.setEnabled(view is not None and not view.pipeline.is_empty)
        self.restore_button.clicked.connect(self._request_restore)
        actions.addWidget(self.rewind_button)
        actions.addWidget(self.restore_button)
        layout.addLayout(actions)

        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, 0, Qt.AlignRight)
        self.history_list.currentRowChanged.connect(
            lambda row: self.rewind_button.setEnabled(row >= 0 and view is not None and not view.pipeline.is_empty)
        )

    def _request_rewind(self):
        row = self.history_list.currentRow()
        if row < 0:
            return
        self.rewind_requested.emit(row)
        self.accept()

    def _request_restore(self):
        self.restore_requested.emit()
        self.accept()


class MainWindow(QMainWindow):
    """Ventana principal: cargar, mirar, cortar y comparar."""

    def __init__(self):
        configure_numeric_locale()
        super().__init__()
        self.setWindowTitle("OCT Workbench 3.1")
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(max(640, available.width() - 32), max(480, available.height() - 72))
        else:
            self.resize(1200, 700)
        self.dataset_a: Optional[OCTDataset] = None
        self.dataset_b: Optional[OCTDataset] = None
        self.view_a: Optional[TransformedView] = None
        self.view_b: Optional[TransformedView] = None
        self.derived_objects = []
        self.display_state = DisplayState()
        self.plugin_registry = discover_plugin_tree(PROJECT_ROOT / "transforms")
        self._build_ui()
        self._fit_to_available_screen()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 8)

        toolbar_container = QWidget()
        toolbar = QVBoxLayout(toolbar_container)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(6)
        self.btn_open_a = QPushButton("Abrir A…")
        self.btn_open_b = QPushButton("Abrir B…")
        self.btn_open_b.setEnabled(False)
        self.btn_metadata = QPushButton("Metadata")
        self.btn_compare_ab = QPushButton("Comparar A − B")
        self.btn_compare_ab.setEnabled(False)
        self.btn_export = QPushButton("Exportar…")
        self.btn_assemble_levels = QPushButton("Crear derivada")
        self.btn_assemble_levels.setToolTip("Crear una muestra derivada desde niveles seleccionados")
        self.btn_assemble_levels.setEnabled(False)
        self.btn_assemble_surface = QPushButton("Ensamblar")
        self.btn_assemble_surface.setToolTip("Ensamblar superficies nativas de A y B")
        self.btn_assemble_surface.setEnabled(False)
        self.btn_close_b = QPushButton("Cerrar B")
        self.btn_close_b.setEnabled(False)
        self.btn_open_a.clicked.connect(lambda: self._open_file("a"))
        self.btn_open_b.clicked.connect(lambda: self._open_file("b"))
        self.btn_metadata.clicked.connect(self._show_metadata)
        self.btn_compare_ab.clicked.connect(self._show_comparison)
        self.btn_export.clicked.connect(self._show_export_dialog)
        self.btn_assemble_levels.clicked.connect(self._create_level_assembly)
        self.btn_assemble_surface.clicked.connect(self._create_surface_assembly)
        self.btn_close_b.clicked.connect(self._close_b)
        sidebar_widget = self._build_sidebar()

        header = QWidget()
        header.setObjectName("appHeader")
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 4, 0)
        header_layout.setSpacing(12)
        self.header_title = QLabel("OCT Workbench")
        self.header_title.setObjectName("headerTitle")
        self.lbl_status = QLabel("Sin medición cargada")
        self.lbl_status.setObjectName("headerStatus")
        self.lbl_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.header_title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.lbl_status)
        self.top_controls = header
        self.pipeline_header = header
        self._pipeline_header_separate_row = False
        toolbar.addWidget(header)
        self.toolbar_container = toolbar_container
        outer.addWidget(toolbar_container)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        sidebar_scroll = QScrollArea()
        sidebar_scroll.setObjectName("sidebarScroll")
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        sidebar_scroll.setMinimumWidth(260)
        sidebar_scroll.setMaximumWidth(420)
        sidebar_scroll.setWidget(sidebar_widget)
        self.sidebar_scroll = sidebar_scroll
        self.tabs = QTabWidget()
        self.canvas_levels = PlotCanvas()
        self.canvas_depth_mm = PlotCanvas()
        self.canvas_amp = PlotCanvas()
        self.canvas_3d = PlotCanvas()
        self.canvas_hist = PlotCanvas()
        self.canvas_cuts = PlotCanvas()
        self.tabs.addTab(self.canvas_levels, "Niveles")
        self.tabs.addTab(self.canvas_3d, "Superficie")
        self.tabs.addTab(self.canvas_depth_mm, "Topografía")
        self.tabs.addTab(self.canvas_amp, "Reflectividad")
        self.tabs.addTab(self.canvas_cuts, "Cortes")
        self.tabs.addTab(self.canvas_hist, "Histograma")
        self.tabs.currentChanged.connect(self._redraw)
        self.canvas_depth_mm.canvas.mpl_connect("button_press_event", self._map_clicked)
        self.canvas_amp.canvas.mpl_connect("button_press_event", self._map_clicked)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setObjectName("mainSplitter")
        main_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(sidebar_scroll)
        main_splitter.addWidget(self.tabs)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([320, 960])
        self.main_splitter = main_splitter
        body.addWidget(main_splitter, 1)
        outer.addLayout(body, 1)

        self._apply_style()
        self._update_sidebar_for_tab(self.tabs.currentIndex())
        self._refresh_comparison_controls()

    def _fit_to_available_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.resize(
            min(1380, max(640, available.width() - 32)),
            min(840, max(480, available.height() - 72)),
        )

    def _cut_pair(self, layout, label):
        group = QGroupBox("Corte")
        form = QFormLayout(group)
        x_spin = QDoubleSpinBox()
        y_spin = QDoubleSpinBox()
        for spin in (x_spin, y_spin):
            spin.setDecimals(6)
            spin.setRange(-1e9, 1e9)
        orientation = QComboBox()
        orientation.addItems(["XY", "XZ", "YZ"])
        coordinate = QDoubleSpinBox()
        coordinate.setDecimals(6)
        coordinate.setRange(-1e9, 1e9)
        mode = QComboBox()
        mode.addItems(["Cortes X/Y", "B-scan espectral"])
        mode.currentTextChanged.connect(lambda _value: self._redraw())
        x_spin.valueChanged.connect(lambda _value: self._redraw())
        y_spin.valueChanged.connect(lambda _value: self._redraw())
        x_spin.valueChanged.connect(lambda value, source=label: self._cut_changed(source, "x", value))
        y_spin.valueChanged.connect(lambda value, source=label: self._cut_changed(source, "y", value))
        orientation.currentTextChanged.connect(
            lambda value, source=label: self._volume_orientation_changed(source, value)
        )
        orientation.currentTextChanged.connect(
            lambda value, source=label: self._cut_changed(source, "orientation", value)
        )
        coordinate.valueChanged.connect(lambda _value: self._redraw())
        coordinate.valueChanged.connect(lambda value, source=label: self._cut_changed(source, "coordinate", value))
        form.addRow("X (mm):", x_spin)
        form.addRow("Y (mm):", y_spin)
        form.addRow("Plano:", orientation)
        form.addRow("Coordenada (mm):", coordinate)
        form.addRow("Vista:", mode)
        layout.addWidget(group)
        suffix = label.lower()
        setattr(self, f"combo_volume_orientation_{suffix}", orientation)
        setattr(self, f"volume_coordinate_{suffix}", coordinate)
        setattr(self, f"combo_cut_mode_{suffix}", mode)
        setattr(self, f"volume_group_{suffix}", group)
        return x_spin, y_spin, group

    @staticmethod
    def _selector_pair(layout):
        group = QWidget()
        group.setObjectName("selectionControls")
        form = QFormLayout(group)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(6)
        form.setVerticalSpacing(3)
        window = QSpinBox()
        measurement = QSpinBox()
        window.setRange(0, 0)
        measurement.setRange(0, 0)
        window.valueChanged.connect(lambda _value: layout.parentWidget().window()._redraw())
        measurement.valueChanged.connect(lambda _value: layout.parentWidget().window()._redraw())
        form.addRow("Ventana:", window)
        form.addRow("Medición:", measurement)
        layout.addWidget(group)
        return window, measurement, group

    def _add_level_controls(self, layout, slot: str):
        container = QWidget()
        controls_layout = QHBoxLayout(container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        spin = QSpinBox()
        spin.setRange(0, 0)
        spin.setMinimumWidth(48)
        spin.valueChanged.connect(lambda value, source=slot: self._level_changed(source, value))
        exclude = QPushButton("Excluir")
        exclude.setToolTip("Excluir el nivel seleccionado de la vista")
        restore = QPushButton("Restaurar")
        restore.setToolTip("Restaurar todos los niveles excluidos")
        for button in (exclude, restore):
            button.setMinimumHeight(30)
        exclude.clicked.connect(lambda _checked=False, source=slot: self._exclude_level(source))
        restore.clicked.connect(lambda _checked=False, source=slot: self._restore_levels(source))
        controls_layout.addWidget(QLabel("Nivel Z:"))
        controls_layout.addWidget(spin)
        controls_layout.addWidget(exclude, 1)
        controls_layout.addWidget(restore, 1)
        layout.addWidget(container)
        if slot == "A":
            self.spin_level_a = spin
            self.btn_exclude_level_a = exclude
            self.btn_restore_levels_a = restore
            self.level_controls_a = container
        else:
            self.spin_level_b = spin
            self.btn_exclude_level_b = exclude
            self.btn_restore_levels_b = restore
            self.level_controls_b = container

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_pipeline_button_widths()
        self._refresh_sample_card_heights()
        # Al abrir por primera vez, Qt todavía puede no haber resuelto los
        # sizeHint de los controles ocultados durante la construcción.
        QTimer.singleShot(0, self._refresh_sample_card_heights)
        self._update_pipeline_header_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pipeline_header_layout()

    def _update_pipeline_header_layout(self):
        """Forzar el recálculo del layout adaptativo tras redimensionar."""
        if not hasattr(self, "toolbar_container"):
            return
        toolbar = self.toolbar_container.layout()
        if toolbar is None:
            return
        toolbar.invalidate()
        toolbar.activate()
        layout = self.pipeline_header.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self.toolbar_container.updateGeometry()

    def _sync_pipeline_button_widths(self):
        width = self.btn_metadata.sizeHint().width()
        for slot in ("a", "b"):
            for name in ("btn_undo_pipeline", "btn_history_pipeline", "btn_restore_pipeline"):
                button = getattr(self, f"{name}_{slot}", None)
                if button is not None:
                    button.setFixedWidth(width)

    def _build_sidebar(self):
        panel = QWidget()
        panel.setObjectName("sidebar")
        panel.setMinimumWidth(0)
        panel.setMaximumWidth(16777215)
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)

        self.group_a = QGroupBox("Muestra A")
        self.group_a.setObjectName("sampleCard")
        self.lbl_a = QLabel("Sin archivo")
        self.lbl_a.setObjectName("sampleDataset")
        self.lbl_a.setWordWrap(True)
        self.lbl_a.setMinimumWidth(0)
        self.lbl_a.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.group_a.setMinimumWidth(0)
        self.group_a.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._build_sample_card(self.group_a, self.lbl_a, "A")

        self.group_b = QGroupBox("Muestra B")
        self.group_b.setObjectName("sampleCard")
        self.lbl_b = QLabel("No cargada")
        self.lbl_b.setObjectName("sampleDataset")
        self.lbl_b.setWordWrap(True)
        self.lbl_b.setMinimumWidth(0)
        self.lbl_b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.group_b.setMinimumWidth(0)
        self.group_b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._build_sample_card(self.group_b, self.lbl_b, "B")
        self.group_b.setVisible(False)

        self.sample_mode_bar = QTabBar()
        self.sample_mode_bar.setObjectName("sampleModeBar")
        self.sample_mode_bar.setExpanding(False)
        self.sample_mode_bar.setDrawBase(False)
        self.sample_mode_bar.addTab("Selección")
        self.sample_mode_bar.addTab("Filtros")
        self.sample_mode_bar.addTab("Geometría")
        self.sample_mode_bar.currentChanged.connect(self._set_sample_mode)
        layout.addWidget(self.sample_mode_bar, 0, Qt.AlignLeft)

        self.selection_actions_group = QGroupBox("Acciones")
        actions_layout = QGridLayout(self.selection_actions_group)
        actions_layout.setContentsMargins(8, 8, 8, 8)
        actions_layout.setHorizontalSpacing(8)
        actions_layout.setVerticalSpacing(6)
        action_buttons = (
            self.btn_open_a,
            self.btn_open_b,
            self.btn_metadata,
            self.btn_close_b,
            self.btn_export,
            self.btn_compare_ab,
            self.btn_assemble_levels,
            self.btn_assemble_surface,
        )
        for button in action_buttons:
            button.setMinimumHeight(30)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for index, button in enumerate(action_buttons):
            actions_layout.addWidget(button, index // 2, index % 2)
        layout.addWidget(self.selection_actions_group)

        source_columns = QVBoxLayout()
        source_columns.setContentsMargins(0, 0, 0, 0)
        source_columns.setSpacing(12)
        source_columns.setAlignment(Qt.AlignTop)
        source_columns.addWidget(self.group_a)
        source_columns.addWidget(self.group_b)
        self.source_columns = source_columns
        layout.addLayout(source_columns)

        self.preparation_group = QGroupBox("Preparación")
        preparation_layout = QVBoxLayout(self.preparation_group)
        preparation_layout.setContentsMargins(8, 8, 8, 8)
        preparation_layout.setSpacing(8)
        preparation_layout.addWidget(self.pipeline_group_a)
        preparation_layout.addWidget(self.pipeline_group_b)
        layout.addWidget(self.preparation_group)

        coordination_group = QGroupBox("Coordinación A/B")
        coordination_layout = QVBoxLayout(coordination_group)
        coordination_hint = QLabel("A/B independientes. Activá sólo lo que quieras compartir.")
        coordination_hint.setWordWrap(True)
        coordination_layout.addWidget(coordination_hint)
        self.chk_shared_level = QCheckBox("Sincronizar nivel Z")
        self.chk_shared_window = QCheckBox("Sincronizar ventana")
        self.chk_shared_measurement = QCheckBox("Sincronizar medición")
        self.lbl_coordination_status = QLabel("Sin sincronización activa")
        self.lbl_coordination_status.setWordWrap(True)
        self.lbl_coordination_status.setStyleSheet("color: #8a5a00;")
        coordination_layout.addWidget(self.lbl_coordination_status)
        for checkbox, attr in (
            (self.chk_shared_level, "shared_level"),
            (self.chk_shared_window, "shared_window"),
            (self.chk_shared_measurement, "shared_measurement"),
        ):
            checkbox.setChecked(bool(getattr(self.display_state, attr)))
            checkbox.toggled.connect(lambda checked, name=attr: self._coordination_toggled(name, checked))
            coordination_layout.addWidget(checkbox)
        coordination_group.setVisible(False)
        layout.addWidget(coordination_group)
        self.coordination_group = coordination_group

        self.extraction_group = QGroupBox("Extracción de perfiles")
        extraction_form = QFormLayout(self.extraction_group)
        self.combo_extract_source = QComboBox()
        self.combo_extract_source.addItem("A")
        self.btn_extract_x = QPushButton("Crear perfil X")
        self.btn_extract_y = QPushButton("Crear perfil Y")
        self.btn_extract_x.clicked.connect(lambda: self._extract_profile("x"))
        self.btn_extract_y.clicked.connect(lambda: self._extract_profile("y"))
        self.btn_extract_x.setEnabled(False)
        self.btn_extract_y.setEnabled(False)
        extraction_form.addRow("Fuente:", self.combo_extract_source)
        extraction_form.addRow(self.btn_extract_x)
        extraction_form.addRow(self.btn_extract_y)
        self.lbl_derived_status = QLabel("Sin objeto derivado")
        self.lbl_derived_status.setWordWrap(True)
        extraction_form.addRow(self.lbl_derived_status)
        layout.addWidget(self.extraction_group)

        layout.addStretch(1)
        self.sidebar = panel
        return panel

    def _build_sample_card(self, group: QGroupBox, label: QLabel, slot: str):
        """Construir una tarjeta A/B con una navegación común de etapa."""
        suffix = slot.lower()
        card_layout = QVBoxLayout(group)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(3)
        card_layout.addWidget(label)

        pages = QStackedWidget()
        pages.setObjectName("sampleStages")
        selection_page = QWidget()
        selection_layout = QVBoxLayout(selection_page)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        selection_layout.setSpacing(3)
        filters_page = QWidget()
        filters_layout = QVBoxLayout(filters_page)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(3)
        geometry_page = QWidget()
        geometry_layout = QVBoxLayout(geometry_page)
        geometry_layout.setContentsMargins(0, 0, 0, 0)
        geometry_layout.setSpacing(3)

        self._add_level_controls(selection_layout, slot)
        spin_window, spin_measurement, selector_group = self._selector_pair(selection_layout)
        spin_window.valueChanged.connect(lambda value, source=slot: self._selector_changed(source, "window", value))
        spin_measurement.valueChanged.connect(lambda value, source=slot: self._selector_changed(source, "measurement", value))
        spin_x, spin_y, cut_group = self._cut_pair(selection_layout, slot)
        filters_group = self._add_filter_controls(filters_layout, slot)
        pipeline_group = self._add_pipeline_controls(None, slot)
        setattr(self, f"pipeline_group_{suffix}", pipeline_group)

        pages.addWidget(selection_page)
        pages.addWidget(filters_page)
        geometry_group = self._add_geometry_controls(geometry_layout, slot)
        pages.addWidget(geometry_page)
        card_layout.addWidget(pages, 1)

        setattr(self, f"sample_pages_{suffix}", pages)
        setattr(self, f"spin_window_{suffix}", spin_window)
        setattr(self, f"spin_measurement_{suffix}", spin_measurement)
        setattr(self, f"selector_group_{suffix}", selector_group)
        setattr(self, f"spin_x_{suffix}", spin_x)
        setattr(self, f"spin_y_{suffix}", spin_y)
        setattr(self, f"cut_group_{suffix}", cut_group)
        setattr(self, f"filters_group_{suffix}", filters_group)
        setattr(self, f"geometry_group_{suffix}", geometry_group)
        self._set_sample_mode(0)

    def _set_sample_mode(self, index: int):
        """Cambiar A y B simultáneamente entre selección, filtros y geometría."""
        index = max(0, min(index, 2))
        for suffix in ("a", "b"):
            pages = getattr(self, f"sample_pages_{suffix}", None)
            if pages is not None:
                pages.setCurrentIndex(index)
                self._fit_sample_page_height(pages)
        if hasattr(self, "source_columns"):
            self.source_columns.invalidate()
            self.source_columns.activate()
        if hasattr(self, "sidebar") and self.sidebar.layout() is not None:
            self.sidebar.layout().invalidate()
            self.sidebar.layout().activate()
        if hasattr(self, "selection_actions_group"):
            self.selection_actions_group.setVisible(index == 0)
        if hasattr(self, "preparation_group"):
            self.preparation_group.setVisible(index == 0 and (
                self.dataset_a is not None or self.dataset_b is not None
            ))
        self._update_coordination_visibility()

    @staticmethod
    def _fit_sample_page_height(pages):
        """Evitar que una página grande deje huecos en las demás vistas."""
        current = pages.currentWidget()
        if current is None:
            return
        if current.layout() is not None:
            current.layout().invalidate()
            current.layout().activate()
        pages.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        pages.setFixedHeight(max(1, current.sizeHint().height()))
        card = pages.parentWidget()
        if card is not None:
            card.updateGeometry()
            if card.layout() is not None:
                card.layout().invalidate()

    def _refresh_sample_card_heights(self):
        """Medir las páginas visibles y actualizar la geometría del sidebar."""
        for suffix in ("a", "b"):
            pages = getattr(self, f"sample_pages_{suffix}", None)
            if pages is not None:
                self._fit_sample_page_height(pages)
        if hasattr(self, "source_columns"):
            self.source_columns.invalidate()
            self.source_columns.activate()
        if hasattr(self, "sidebar") and self.sidebar.layout() is not None:
            self.sidebar.layout().invalidate()
            self.sidebar.layout().activate()
            self.sidebar.updateGeometry()

    def _update_coordination_visibility(self):
        if not hasattr(self, "coordination_group"):
            return
        stage_is_selection = not hasattr(self, "sample_mode_bar") or self.sample_mode_bar.currentIndex() == 0
        self.coordination_group.setVisible(self.dataset_b is not None and stage_is_selection)

    def _add_filter_controls(self, layout, slot: str):
        suffix = slot.lower()
        group = QWidget()
        group.setObjectName("filtersGroup")
        inner = QVBoxLayout(group)
        inner.setContentsMargins(4, 5, 4, 6)
        inner.setSpacing(8)
        setattr(self, f"filter_group_{suffix}", self._add_depth_mm_filter_controls(inner, slot))
        setattr(self, f"level_plane_group_{suffix}", self._add_level_plane_controls(inner, slot))
        setattr(self, f"region_level_group_{suffix}", self._add_region_level_controls(inner, slot))
        setattr(self, f"median_group_{suffix}", self._add_median_controls(inner, slot))
        self._add_plugin_controls(inner, slot, "filter")
        layout.addWidget(group)
        return group

    def _add_region_level_controls(self, layout, slot: str):
        suffix = slot.lower()
        group = QWidget()
        group.setObjectName("filterSubsection")
        section = QVBoxLayout(group)
        section.setContentsMargins(0, 2, 0, 4)
        section.setSpacing(6)
        title = QLabel("Nivelado por regiones")
        title.setObjectName("subsectionTitle")
        section.addWidget(title)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        section.addLayout(form)
        controls = {}
        for key, title in (
            ("x_min", "Inicio X (mm):"),
            ("x_max", "Final X (mm):"),
            ("y_min", "Inicio Y (mm):"),
            ("y_max", "Final Y (mm):"),
        ):
            spin = QDoubleSpinBox()
            spin.setDecimals(6)
            spin.setRange(-1e9, 1e9)
            controls[key] = spin
            form.addRow(title, spin)
        apply_button = QPushButton("Aplicar nivelado")
        restore_button = QPushButton("Restaurar")
        restore_button.setToolTip("Quitar el nivelado por regiones y conservar el resto del pipeline")
        status = QLabel("Sin nivelado aplicado")
        status.setWordWrap(True)
        apply_button.clicked.connect(lambda _checked=False, source=slot: self._apply_region_leveling(source))
        restore_button.clicked.connect(lambda _checked=False, source=slot: self._restore_region_leveling(source))
        form.addRow(apply_button)
        form.addRow(restore_button)
        form.addRow(status)
        layout.addWidget(group)
        for key, widget in controls.items():
            setattr(self, f"spin_region_{key}_{suffix}", widget)
        setattr(self, f"btn_apply_region_level_{suffix}", apply_button)
        setattr(self, f"btn_restore_region_level_{suffix}", restore_button)
        setattr(self, f"lbl_region_level_status_{suffix}", status)
        return group

    def _add_level_plane_controls(self, layout, slot: str):
        suffix = slot.lower()
        group = QWidget()
        group.setObjectName("filterSubsection")
        section = QVBoxLayout(group)
        section.setContentsMargins(0, 2, 0, 4)
        section.setSpacing(6)
        title = QLabel("Nivelado por plano")
        title.setObjectName("subsectionTitle")
        section.addWidget(title)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        section.addLayout(form)
        window = QSpinBox()
        measurement = QSpinBox()
        for spin in (window, measurement):
            spin.setRange(0, 0)
        apply_button = QPushButton("Aplicar nivelado por plano")
        restore_button = QPushButton("Restaurar nivelado")
        restore_button.setToolTip("Quitar sólo el nivelado por plano y conservar otros pasos")
        status = QLabel("Sin nivelado por plano aplicado")
        status.setWordWrap(True)
        apply_button.setEnabled(False)
        restore_button.setEnabled(False)
        apply_button.clicked.connect(lambda _checked=False, source=slot: self._apply_level_plane(source))
        restore_button.clicked.connect(lambda _checked=False, source=slot: self._restore_level_plane(source))
        form.addRow("Ventana:", window)
        form.addRow("Medición:", measurement)
        form.addRow(apply_button)
        form.addRow(restore_button)
        form.addRow(status)
        layout.addWidget(group)
        for name, value in {
            f"spin_level_plane_window_{suffix}": window,
            f"spin_level_plane_measurement_{suffix}": measurement,
            f"btn_apply_level_plane_{suffix}": apply_button,
            f"btn_restore_level_plane_{suffix}": restore_button,
            f"lbl_level_plane_status_{suffix}": status,
        }.items():
            setattr(self, name, value)
        return group

    def _apply_level_plane(self, slot: str = "A"):
        suffix = slot.lower()
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if dataset is None or dataset.depth_mm is None:
            return
        parameters = {
            "win_id": getattr(self, f"spin_level_plane_window_{suffix}").value(),
            "measurement": getattr(self, f"spin_level_plane_measurement_{suffix}").value(),
        }
        try:
            transform = self.plugin_registry.create("level_plane", parameters)
            current_view = getattr(self, "view_a" if suffix == "a" else "view_b")
            view = TransformedView(dataset)
            if current_view is not None:
                for existing in current_view.pipeline.steps:
                    if not (isinstance(existing, PluginTransform) and existing.spec.id == "level_plane"):
                        view.pipeline.add(existing)
            view.pipeline.add(transform)
            view.transformed_data
            if suffix == "a":
                self.view_a = view
            else:
                self.view_b = view
            getattr(self, f"lbl_level_plane_status_{suffix}").setText(
                f"{slot.upper()}: plano ajustado y aplicado como plano menos OPD "
                f"[W{parameters['win_id']}, M{parameters['measurement']}]"
            )
            getattr(self, f"btn_restore_level_plane_{suffix}").setEnabled(True)
            self._refresh_pipeline_status(slot)
            self._redraw()
        except (Exception, SystemExit) as exc:
            QMessageBox.warning(self, "Nivelado por plano no disponible", str(exc))

    def _restore_level_plane(self, slot: str = "A"):
        suffix = slot.lower()
        view = self.view_a if suffix == "a" else self.view_b
        if view is None:
            return
        remaining = [
            step for step in view.pipeline.steps
            if not (isinstance(step, PluginTransform) and step.spec.id == "level_plane")
        ]
        if remaining:
            rebuilt = TransformedView(self.dataset_a if suffix == "a" else self.dataset_b)
            for step in remaining:
                rebuilt.pipeline.add(step)
            view = rebuilt
        else:
            view = None
        if suffix == "a":
            self.view_a = view
        else:
            self.view_b = view
        getattr(self, f"lbl_level_plane_status_{suffix}").setText("Sin nivelado por plano aplicado")
        getattr(self, f"btn_restore_level_plane_{suffix}").setEnabled(False)
        self._refresh_pipeline_status(slot)
        self._redraw()

    def _add_median_controls(self, layout, slot: str):
        suffix = slot.lower()
        group = QWidget()
        group.setObjectName("filterSubsection")
        section = QVBoxLayout(group)
        section.setContentsMargins(0, 2, 0, 4)
        section.setSpacing(6)
        title = QLabel("Mediana 2D")
        title.setObjectName("subsectionTitle")
        section.addWidget(title)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        section.addLayout(form)
        kernel = QSpinBox()
        kernel.setRange(3, 15)
        kernel.setSingleStep(2)
        kernel.setValue(3)
        apply_button = QPushButton("Aplicar mediana 2D")
        restore_button = QPushButton("Restaurar")
        restore_button.setToolTip("Quitar la mediana 2D y conservar el resto del pipeline")
        status = QLabel("Sin mediana aplicada")
        status.setWordWrap(True)
        apply_button.clicked.connect(lambda _checked=False, source=slot: self._apply_median_filter(source))
        restore_button.clicked.connect(lambda _checked=False, source=slot: self._restore_median_filter(source))
        form.addRow("Matriz cuadrada:", kernel)
        form.addRow(apply_button)
        form.addRow(restore_button)
        form.addRow(status)
        layout.addWidget(group)
        setattr(self, f"spin_median_kernel_{suffix}", kernel)
        setattr(self, f"btn_apply_median_{suffix}", apply_button)
        setattr(self, f"btn_restore_median_{suffix}", restore_button)
        setattr(self, f"lbl_median_status_{suffix}", status)
        return group

    def _configure_median(self, dataset: OCTDataset, slot: str = "a"):
        suffix = slot.lower()
        enabled = dataset.depth_mm is not None and len(dataset.X) > 0
        getattr(self, f"btn_apply_median_{suffix}").setEnabled(enabled)
        getattr(self, f"btn_restore_median_{suffix}").setEnabled(False)
        getattr(self, f"lbl_median_status_{suffix}").setText("Sin mediana aplicada" if enabled else "Sin OPD disponible")

    def _apply_median_filter(self, slot: str = "A"):
        suffix = slot.lower()
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if dataset is None or dataset.depth_mm is None:
            return
        try:
            view = getattr(self, "view_a" if suffix == "a" else "view_b") or TransformedView(dataset)
            view.pipeline.add(self.plugin_registry.create("filter_median", {
                "kernel_size": getattr(self, f"spin_median_kernel_{suffix}").value(),
                "win_id": getattr(self, f"spin_window_{suffix}").value(),
            }))
            if suffix == "a":
                self.view_a = view
            else:
                self.view_b = view
            kernel = getattr(self, f"spin_median_kernel_{suffix}").value()
            getattr(self, f"lbl_median_status_{suffix}").setText(
                f"{suffix.upper()}: mediana {kernel}×{kernel} aplicada sobre OPD"
            )
            getattr(self, f"btn_restore_median_{suffix}").setEnabled(True)
            self._refresh_pipeline_status(slot)
            self._redraw()
        except (IndexError, TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Mediana no disponible", str(exc))

    def _add_plugin_controls(self, layout, slot: str, kind: str):
        specs = self.plugin_registry.list(kind)
        if not specs:
            return None
        suffix = slot.lower()
        section = QWidget()
        section.setObjectName(f"local{kind.title()}Plugins")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 4, 0, 4)
        section_layout.setSpacing(5)
        title = QLabel("Plugins locales")
        title.setObjectName("subsectionTitle")
        section_layout.addWidget(title)
        buttons = []
        for plugin in specs:
            card = QWidget()
            card.setObjectName(f"plugin_{plugin.id}")
            form = QFormLayout(card)
            form.setContentsMargins(0, 0, 0, 0)
            form.setHorizontalSpacing(8)
            form.setVerticalSpacing(4)
            description = QLabel(plugin.description)
            description.setWordWrap(True)
            form.addRow(QLabel(plugin.name), description)
            controls = {}
            for parameter in plugin.parameters:
                widget = self._plugin_parameter_widget(parameter)
                controls[parameter.id] = widget
                label = parameter.label
                if parameter.unit:
                    label += f" ({parameter.unit})"
                form.addRow(label + ":", widget)
            button = QPushButton(f"Aplicar {plugin.name}")
            button.setToolTip(f"Aplicar plugin local {plugin.id} ({plugin.source})")
            button.setEnabled(False)
            button.clicked.connect(
                lambda _checked=False, source=slot, plugin_id=plugin.id,
                plugin_controls=controls, plugin_kind=kind:
                self._apply_plugin(source, plugin_kind, plugin_id, plugin_controls)
            )
            form.addRow(button)
            section_layout.addWidget(card)
            buttons.append(button)
        setattr(self, f"plugin_buttons_{kind}_{suffix}", buttons)
        layout.addWidget(section)
        return section

    @staticmethod
    def _plugin_parameter_widget(parameter):
        if parameter.type == "float":
            widget = QDoubleSpinBox()
            widget.setRange(
                float(parameter.minimum) if parameter.minimum is not None else -1e12,
                float(parameter.maximum) if parameter.maximum is not None else 1e12,
            )
            widget.setDecimals(6)
            widget.setValue(float(parameter.default or 0.0))
            if parameter.unit:
                widget.setSuffix(f" {parameter.unit}")
            return widget
        if parameter.type == "int":
            widget = QSpinBox()
            widget.setRange(
                int(parameter.minimum) if parameter.minimum is not None else -2147483647,
                int(parameter.maximum) if parameter.maximum is not None else 2147483647,
            )
            widget.setValue(int(parameter.default or 0))
            return widget
        if parameter.type == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(parameter.default))
            return widget
        if parameter.type == "choice":
            widget = QComboBox()
            widget.addItems([str(option) for option in parameter.options])
            if parameter.default in parameter.options:
                widget.setCurrentIndex(parameter.options.index(parameter.default))
            return widget
        widget = QLineEdit(str(parameter.default or ""))
        return widget

    @staticmethod
    def _plugin_parameter_value(widget):
        if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
            return widget.value()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QComboBox):
            return widget.currentText()
        return widget.text()

    def _set_plugin_buttons_enabled(self, kind: str, slot: str, enabled: bool):
        for button in getattr(self, f"plugin_buttons_{kind}_{slot.lower()}", []):
            button.setEnabled(enabled)

    def _apply_plugin(self, slot: str, kind: str, plugin_id: str, controls: dict):
        suffix = slot.lower()
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if dataset is None:
            return
        parameters = {
            key: self._plugin_parameter_value(widget)
            for key, widget in controls.items()
        }
        try:
            transform = self.plugin_registry.create(plugin_id, parameters)
            current_view = getattr(self, "view_a" if suffix == "a" else "view_b")
            view = TransformedView(dataset)
            if current_view is not None:
                for existing in current_view.pipeline.steps:
                    view.pipeline.add(existing)
            view.pipeline.add(transform)
            # Validar inmediatamente: un plugin roto no debe quedar publicado
            # en el estado de la GUI para fallar más tarde durante el redraw.
            view.transformed_data
            if suffix == "a":
                self.view_a = None if view.pipeline.is_empty else view
            else:
                self.view_b = None if view.pipeline.is_empty else view
            self._refresh_pipeline_status(slot)
            self._redraw()
        except (Exception, SystemExit) as exc:
            QMessageBox.warning(self, "Plugin no disponible", str(exc))

    def _add_geometry_controls(self, layout, slot: str):
        suffix = slot.lower()
        group = QWidget()
        group.setObjectName("geometryGroup")
        group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(3)

        actions = (
            "Invertir X", "Invertir Y", "Invertir Z",
            "Espejar X", "Espejar Y", "Centrar origen",
        )
        operations_label = QLabel("Operaciones")
        operations_label.setObjectName("geometrySubheading")
        group_layout.addWidget(operations_label)
        action_grid = QGridLayout()
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(4)
        action_grid.setVerticalSpacing(3)
        action_buttons = []
        for index, action in enumerate(actions):
            button = QPushButton(action)
            button.setObjectName("geometryAction")
            button.clicked.connect(
                lambda _checked=False, source=slot, selected=action: self._apply_geometry(source, selected)
            )
            action_grid.addWidget(button, index // 2, index % 2)
            action_buttons.append(button)
            setattr(self, f"btn_geometry_{action.lower().replace(' ', '_')}_{suffix}", button)
        group_layout.addLayout(action_grid)

        offset_spins = {}
        offset_buttons = {}
        for axis in ("X", "Y", "Z"):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            label = QLabel(f"Offset {axis} (mm):")
            label.setMinimumWidth(88)
            spin = QDoubleSpinBox()
            spin.setRange(-1e9, 1e9)
            spin.setDecimals(6)
            spin.setSingleStep(1.0)
            spin.setToolTip("Desplazamiento físico en milímetros.")
            apply_button = QPushButton("Aplicar")
            apply_button.setObjectName("geometryOffsetAction")
            apply_button.clicked.connect(
                lambda _checked=False, source=slot, selected_axis=axis, control=spin:
                self._apply_geometry(source, f"Offset {selected_axis}", control.value())
            )
            row_layout.addWidget(label)
            row_layout.addWidget(spin, 1)
            row_layout.addWidget(apply_button)
            group_layout.addWidget(row_widget)
            offset_spins[axis] = spin
            offset_buttons[axis] = apply_button
        self._add_plugin_controls(group_layout, slot, "geometry")

        layout.addWidget(group, 0, Qt.AlignTop)
        setattr(self, f"geometry_action_buttons_{suffix}", action_buttons)
        setattr(self, f"geometry_offset_spins_{suffix}", offset_spins)
        setattr(self, f"geometry_offset_buttons_{suffix}", offset_buttons)
        return group

    def _add_pipeline_controls(self, layout, slot: str):
        suffix = slot.lower()
        container = QWidget()
        container.setObjectName(f"pipelineRow{slot}")
        container.setMinimumWidth(0)
        container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        form = FlowLayout(container, horizontal_spacing=8, vertical_spacing=6, alignment=Qt.AlignLeft)
        form.setContentsMargins(0, 0, 0, 0)
        source_label = QLabel(slot)
        source_label.setObjectName("pipelineSlot")
        source_label.setMinimumWidth(18)
        source_label.setAlignment(Qt.AlignCenter)
        last_step = QLabel("Último paso: —")
        last_step.setMinimumWidth(135)
        last_step.setMaximumWidth(180)
        last_step.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        last_step.setWordWrap(False)
        self.btn_metadata.ensurePolished()
        pipeline_button_width = self.btn_metadata.sizeHint().width()
        undo_button = QPushButton("Deshacer")
        undo_button.setFixedWidth(pipeline_button_width)
        undo_button.setToolTip("Deshacer último paso")
        undo_button.setEnabled(False)
        undo_button.clicked.connect(lambda _checked=False, source=slot: self._undo_preparation(source))
        history_button = QPushButton("Historial")
        history_button.setFixedWidth(pipeline_button_width)
        history_button.setToolTip("Ver historial de procesos…")
        history_button.setEnabled(False)
        history_button.clicked.connect(lambda _checked=False, source=slot: self._show_pipeline_history(source))
        restore_button = QPushButton("Restaurar")
        restore_button.setFixedWidth(pipeline_button_width)
        restore_button.setToolTip("Restaurar la muestra original y limpiar toda la preparación")
        restore_button.setEnabled(False)
        restore_button.clicked.connect(lambda _checked=False, source=slot: self._restore_original(source))
        for widget in (source_label, undo_button, history_button, restore_button, last_step):
            form.addWidget(widget)
        if layout is not None:
            layout.addWidget(container)
        setattr(self, f"lbl_pipeline_{suffix}", last_step)
        setattr(self, f"btn_undo_pipeline_{suffix}", undo_button)
        setattr(self, f"btn_history_pipeline_{suffix}", history_button)
        setattr(self, f"btn_restore_pipeline_{suffix}", restore_button)
        return container

    def _configure_geometry(self, dataset: OCTDataset, slot: str = "a"):
        suffix = slot.lower()
        enabled = len(dataset.X) > 0
        for button in getattr(self, f"geometry_action_buttons_{suffix}"):
            button.setEnabled(enabled)
        for button in getattr(self, f"geometry_offset_buttons_{suffix}").values():
            button.setEnabled(enabled)
        self._set_plugin_buttons_enabled("geometry", slot, enabled)
        getattr(self, f"lbl_pipeline_{suffix}").setText("Último paso: —")
        getattr(self, f"lbl_pipeline_{suffix}").setToolTip("")
        getattr(self, f"btn_undo_pipeline_{suffix}").setEnabled(False)
        getattr(self, f"btn_history_pipeline_{suffix}").setEnabled(False)
        getattr(self, f"btn_restore_pipeline_{suffix}").setEnabled(False)

    def _refresh_pipeline_status(self, slot: str):
        suffix = slot.lower()
        view = self.view_a if suffix == "a" else self.view_b
        label = getattr(self, f"lbl_pipeline_{suffix}")
        undo = getattr(self, f"btn_undo_pipeline_{suffix}")
        history = getattr(self, f"btn_history_pipeline_{suffix}")
        restore = getattr(self, f"btn_restore_pipeline_{suffix}")
        if view is None or view.pipeline.is_empty:
            label.setText("Último paso: —")
            label.setToolTip("")
            undo.setEnabled(False)
            history.setEnabled(False)
            restore.setEnabled(False)
            return
        last_step = view.pipeline.steps[-1]
        label.setText(f"Último paso: {last_step.name}")
        label.setToolTip(last_step.description)
        undo.setEnabled(True)
        history.setEnabled(True)
        restore.setEnabled(True)

    def _show_pipeline_history(self, slot: str = "A"):
        suffix = slot.lower()
        view = self.view_a if suffix == "a" else self.view_b
        if view is None or view.pipeline.is_empty:
            return
        dialog = PipelineHistoryDialog(slot, view, self)
        dialog.rewind_requested.connect(lambda index: self._rewind_preparation(slot, index))
        dialog.restore_requested.connect(lambda: self._restore_original(slot))
        dialog.exec_()

    def _rewind_preparation(self, slot: str = "A", index: int = 0):
        suffix = slot.lower()
        view = self.view_a if suffix == "a" else self.view_b
        if view is None:
            return
        try:
            view.pipeline.rewind_to(index)
        except IndexError:
            return
        self._refresh_pipeline_status(slot)
        self._redraw()

    def _restore_original(self, slot: str = "A"):
        suffix = slot.lower()
        if suffix == "a":
            self.view_a = None
        else:
            self.view_b = None
        self.display_state.set_filter(slot, None, None, offset_mm=0.0, invert=False)
        getattr(self, f"spin_depth_mm_offset_{suffix}").setValue(0.0)
        getattr(self, f"chk_invert_depth_{suffix}").setChecked(False)
        getattr(self, f"chk_offset_zero_{suffix}").setChecked(False)
        getattr(self, f"lbl_mask_status_{suffix}").setText("Sin máscara aplicada")
        getattr(self, f"btn_restore_mask_{suffix}").setEnabled(False)
        getattr(self, f"lbl_region_level_status_{suffix}").setText("Sin nivelado aplicado")
        getattr(self, f"btn_restore_region_level_{suffix}").setEnabled(False)
        getattr(self, f"lbl_median_status_{suffix}").setText("Sin mediana aplicada")
        getattr(self, f"btn_restore_median_{suffix}").setEnabled(False)
        getattr(self, f"lbl_level_plane_status_{suffix}").setText("Sin nivelado por plano aplicado")
        getattr(self, f"btn_restore_level_plane_{suffix}").setEnabled(False)
        self._refresh_pipeline_status(slot)
        self._redraw()

    def _apply_geometry(self, slot: str = "A", action: str = "", value: Optional[float] = None):
        suffix = slot.lower()
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if dataset is None or not action:
            return
        if value is None:
            value = 0.0
        plugin_parameters = {
            "Invertir X": ("invert_axis", {"axis": "X"}),
            "Invertir Y": ("invert_axis", {"axis": "Y"}),
            "Invertir Z": ("invert_axis", {"axis": "Z"}),
            "Espejar X": ("mirror", {"axis": "X"}),
            "Espejar Y": ("mirror", {"axis": "Y"}),
            "Centrar origen": ("center_origin", {}),
            "Offset X": ("offset_geometry", {"axis": "X", "value_mm": value}),
            "Offset Y": ("offset_geometry", {"axis": "Y", "value_mm": value}),
            "Offset Z": ("offset_geometry", {"axis": "Z", "value_mm": value}),
        }
        selected = plugin_parameters.get(action)
        if selected is None:
            return
        plugin_id, parameters = selected
        transform = self.plugin_registry.create(plugin_id, parameters)
        view = getattr(self, "view_a" if suffix == "a" else "view_b") or TransformedView(dataset)
        view.pipeline.add(transform)
        if suffix == "a":
            self.view_a = view
        else:
            self.view_b = view
        self._refresh_pipeline_status(slot)
        self._redraw()

    def _undo_preparation(self, slot: str = "A"):
        suffix = slot.lower()
        view = self.view_a if suffix == "a" else self.view_b
        if view is None:
            return
        view.pipeline.undo()
        if view.pipeline.is_empty:
            if suffix == "a":
                self.view_a = None
            else:
                self.view_b = None
        self._refresh_pipeline_status(slot)
        self._redraw()

    def _add_depth_mm_filter_controls(self, layout, slot: str):
        suffix = slot.lower()
        group = QWidget()
        group.setObjectName("filterSubsection")
        section = QVBoxLayout(group)
        section.setContentsMargins(0, 2, 0, 4)
        section.setSpacing(6)
        title = QLabel("Filtro OPD")
        title.setObjectName("subsectionTitle")
        section.addWidget(title)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        section.addLayout(form)
        setattr(self, f"_depth_mm_filter_scale_{suffix}", 1.0)
        setattr(self, f"_depth_mm_filter_unit_{suffix}", "mm")
        spin_min = QDoubleSpinBox()
        spin_max = QDoubleSpinBox()
        for spin in (spin_min, spin_max):
            spin.setDecimals(6)
            spin.setRange(-1e9, 1e9)
            spin.setSingleStep(0.000001)
        spin_offset = QDoubleSpinBox()
        spin_offset.setRange(-1e9, 1e9)
        spin_offset.setDecimals(6)
        spin_offset.setSingleStep(0.000001)
        lbl_min = QLabel("Mínimo (mm):")
        lbl_max = QLabel("Máximo (mm):")
        lbl_offset = QLabel("Offset (mm):")
        check_offset_zero = QCheckBox("Auto offset")
        check_offset_zero.setToolTip("Llevar automáticamente el mínimo OPD finito válido a 0")
        check_invert = QCheckBox("Invertir OPD")
        btn_apply = QPushButton("Aplicar cambios")
        btn_restore = QPushButton("Restaurar original")
        status = QLabel("Sin máscara aplicada")
        status.setWordWrap(True)
        btn_apply.clicked.connect(lambda _checked=False, source=slot: self._apply_depth_mm_mask(source))
        btn_restore.clicked.connect(lambda _checked=False, source=slot: self._restore_depth_mm_mask(source))
        btn_apply.setEnabled(False)
        btn_restore.setEnabled(False)
        form.addRow(lbl_min, spin_min)
        form.addRow(lbl_max, spin_max)
        form.addRow(lbl_offset, spin_offset)
        form.addRow(check_offset_zero)
        form.addRow(check_invert)
        form.addRow(btn_apply)
        form.addRow(btn_restore)
        form.addRow(status)
        for name, value in {
            f"spin_depth_mm_min_{suffix}": spin_min,
            f"spin_depth_mm_max_{suffix}": spin_max,
            f"spin_depth_mm_offset_{suffix}": spin_offset,
            f"lbl_depth_mm_min_{suffix}": lbl_min,
            f"lbl_depth_mm_max_{suffix}": lbl_max,
            f"lbl_depth_mm_offset_{suffix}": lbl_offset,
            f"chk_offset_zero_{suffix}": check_offset_zero,
            f"chk_invert_depth_{suffix}": check_invert,
            f"btn_apply_mask_{suffix}": btn_apply,
            f"btn_restore_mask_{suffix}": btn_restore,
            f"lbl_mask_status_{suffix}": status,
        }.items():
            setattr(self, name, value)
        if suffix == "a":
            for legacy_name, value in {
                "spin_depth_mm_min": spin_min,
                "spin_depth_mm_max": spin_max,
                "spin_depth_mm_offset": spin_offset,
                "lbl_depth_mm_min": lbl_min,
                "lbl_depth_mm_max": lbl_max,
                "lbl_depth_mm_offset": lbl_offset,
                "chk_offset_zero": check_offset_zero,
                "chk_invert_depth": check_invert,
                "btn_apply_mask": btn_apply,
                "btn_restore_mask": btn_restore,
                "lbl_mask_status": status,
            }.items():
                setattr(self, legacy_name, value)
        layout.addWidget(group)
        return group

    def _create_level_assembly(self):
        dataset = self.dataset_a
        if dataset is None:
            return
        dialog = LevelAssemblyDialog(dataset, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        selections = dialog.selections()
        source_data = TransformedView(dataset).transformed_data
        result = assemble_levels(source_data, selections)
        if result.data.n_points == 0:
            QMessageBox.warning(self, "Muestra derivada", "No se seleccionaron Medidas/Puntos.")
            return
        if result.warnings:
            message = "\\n".join(result.warnings)
            warning = QMessageBox(self)
            warning.setIcon(QMessageBox.Warning)
            warning.setWindowTitle("Advertencias del ensamblado")
            warning.setText("Hay Niveles con cobertura incompleta o duplicados.")
            warning.setInformativeText("Los huecos se conservarán como NaN. ¿Guardar Muestra 1* igualmente?")
            warning.setDetailedText(message)
            warning.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)
            if warning.exec_() != QMessageBox.Save:
                return
        base_name = str(dataset.metadata.get("sample_name") or os.path.splitext(dataset.filename)[0])
        derived_name = f"{base_name}*"
        default_path = os.path.join(os.path.dirname(dataset.filepath), f"{base_name}_star.npz")
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Guardar {derived_name}",
            default_path,
            "NPZ compatible con OCT Workbench (*.npz)",
        )
        if not path:
            return
        try:
            derived = derived_from_assembly(result, dataset.filepath, derived_name)
            to_npz(derived, path)
            self.derived_objects.append(derived)
            self.lbl_status.setText(
                f"Guardada {derived_name}: {os.path.basename(path)}. "
                "Podés cargarla con Abrir B… para compararla."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar Muestra derivada", str(exc))

    def _create_surface_assembly(self):
        if self.dataset_a is None or self.dataset_b is None:
            return
        datasets = {"A": self.dataset_a, "B": self.dataset_b}
        dialog = SurfaceAssemblyDialog(datasets, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        selected = dialog.specifications()
        if not selected:
            QMessageBox.warning(self, "Superficie compuesta", "No se seleccionaron parches.")
            return

        transformed = {}
        for slot, dataset in datasets.items():
            shown = self._shown_a() if slot == "A" else self._shown_b()
            transformed[slot] = (
                shown.transformed_data if hasattr(shown, "transformed_data")
                else TransformedView(dataset).transformed_data
            )
        specs = [replace(spec, data=transformed[spec.source]) for spec in selected]
        try:
            result = assemble_surface_patches(specs)
        except (TypeError, ValueError) as exc:
            QMessageBox.critical(self, "Error al ensamblar superficies", str(exc))
            return
        if result.data.n_points == 0:
            QMessageBox.warning(self, "Superficie compuesta", "Los parches no contienen puntos válidos.")
            return
        if result.warnings:
            warning = QMessageBox(self)
            warning.setIcon(QMessageBox.Warning)
            warning.setWindowTitle("Advertencias del ensamblado")
            warning.setText("El resultado conservará las mallas nativas y sus advertencias.")
            warning.setInformativeText("No se realizó interpolación ni remuestreo. ¿Guardar igualmente?")
            warning.setDetailedText("\\n".join(result.warnings))
            warning.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)
            if warning.exec_() != QMessageBox.Save:
                return

        name_a = str(self.dataset_a.metadata.get("sample_name") or os.path.splitext(self.dataset_a.filename)[0])
        name_b = str(self.dataset_b.metadata.get("sample_name") or os.path.splitext(self.dataset_b.filename)[0])
        derived_name = f"{name_a} + {name_b}*"
        default_path = os.path.join(
            os.path.dirname(self.dataset_a.filepath),
            f"{name_a}_{name_b}_compuesta.npz",
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Guardar {derived_name}",
            default_path,
            "NPZ compatible con OCT Workbench (*.npz)",
        )
        if not path:
            return
        try:
            derived = derived_from_surface_assembly(
                result,
                {"A": self.dataset_a.filepath, "B": self.dataset_b.filepath},
                derived_name,
            )
            to_npz(derived, path)
            self.derived_objects.append(derived)
            self.lbl_status.setText(
                f"Guardada superficie compuesta: {os.path.basename(path)}. "
                "Mallas nativas conservadas; sin interpolación."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar superficie compuesta", str(exc))

    def _open_file(self, slot: str):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Abrir muestra {slot.upper()}",
            "",
            "Archivos OCT (*.npz *.h5 *.hdf5);;Todos los archivos (*)",
        )
        if not path:
            return
        try:
            dataset = OCTDataset.from_file(path)
            if slot == "a":
                self.dataset_a = dataset
                self.view_a = None
                self.btn_open_b.setEnabled(True)
                self.btn_assemble_levels.setEnabled(dataset.volume_layout.n_levels > 0)
                self.lbl_a.setText(self._dataset_card(dataset))
                self._configure_levels(dataset, "a")
                self._configure_selectors(dataset)
                self._configure_cuts(dataset)
                self._configure_filter(dataset, "a")
                self._configure_region_level(dataset, "a")
                self._configure_median(dataset, "a")
                self._configure_geometry(dataset, "a")
                self.btn_extract_x.setEnabled(True)
                self.btn_extract_y.setEnabled(True)
            else:
                self.dataset_b = dataset
                self.view_b = None
                self.group_b.setVisible(True)
                self.btn_close_b.setEnabled(True)
                self._refresh_comparison_controls()
                self.lbl_b.setText(self._dataset_card(dataset))
                self._configure_levels(dataset, "b")
                if self.combo_extract_source.findText("B") < 0:
                    self.combo_extract_source.addItem("B")
                self._configure_selectors(dataset, "b")
                self._configure_cuts(dataset, "b")
                self._configure_filter(dataset, "b")
                self._configure_region_level(dataset, "b")
                self._configure_median(dataset, "b")
                self._configure_geometry(dataset, "b")
            self._refresh_comparison_controls()
            self._redraw()
            self.lbl_status.setText(f"Cargada muestra {slot.upper()}: {dataset.filename}")
        except Exception as exc:
            QMessageBox.critical(self, "Error al cargar", str(exc))

    def _configure_levels(self, dataset: OCTDataset, slot: str = "a"):
        spin = self.spin_level_a if slot.lower() == "a" else self.spin_level_b
        layout = dataset.volume_layout
        spin.blockSignals(True)
        spin.setRange(0, max(0, layout.n_levels - 1))
        spin.setValue(0)
        spin.blockSignals(False)
        self.display_state.set_level(slot, 0)
        self.display_state.source(slot).excluded_levels = frozenset()
        self._redraw()

    def _level_changed(self, slot: str, level_index: int):
        dataset = self.dataset_a if slot.upper() == "A" else self.dataset_b
        if dataset is None:
            return
        self.display_state.set_level(slot, level_index)
        if self.display_state.shared_level:
            source = dataset.volume_layout.levels[int(level_index)]
            other_slot = "B" if slot.upper() == "A" else "A"
            other_dataset = self.dataset_b if other_slot == "B" else self.dataset_a
            if other_dataset is not None:
                target = other_dataset.volume_layout.level_for_z(source.z_mm)
                other_spin = self.spin_level_b if other_slot == "B" else self.spin_level_a
                other_spin.blockSignals(True)
                other_spin.setValue(target.index)
                other_spin.blockSignals(False)
                self.display_state.set_level(other_slot, target.index)
        self._redraw()

    def _exclude_level(self, slot: str):
        dataset = self.dataset_a if slot.upper() == "A" else self.dataset_b
        if dataset is None:
            return
        level_index = self.display_state.source(slot).level_index
        self.display_state.exclude_level(slot, level_index)
        self._redraw()
        self.lbl_status.setText(f"Nivel {level_index} excluido de la vista {slot.upper()} (reversible)")

    def _restore_levels(self, slot: str):
        source = self.display_state.source(slot)
        source.excluded_levels = frozenset()
        self._redraw()
        self.lbl_status.setText(f"Niveles restaurados en la vista {slot.upper()}")

    def _configure_selectors(self, dataset: OCTDataset, slot: str = "a"):
        if dataset.depth_mm is None:
            return
        spin_window = self.spin_window_a if slot == "a" else self.spin_window_b
        spin_measurement = self.spin_measurement_a if slot == "a" else self.spin_measurement_b
        spin_window.setRange(0, max(0, dataset.depth_mm.shape[2] - 1))
        spin_measurement.setRange(0, max(0, dataset.depth_mm.shape[1] - 1))
        spin_window.setValue(0)
        spin_measurement.setValue(0)

    def _coordination_toggled(self, attribute: str, checked: bool):
        setattr(self.display_state, attribute, bool(checked))
        if not checked:
            self.lbl_coordination_status.setText("Sin sincronización activa")
            return
        if self.dataset_b is None:
            self.lbl_coordination_status.setText("B aún no está cargada")
            return
        messages = []
        if attribute in {"shared_window", "shared_measurement", "shared_level"}:
            if attribute == "shared_window":
                source, target = self.spin_window_a, self.spin_window_b
                field = "window_id"
            elif attribute == "shared_measurement":
                source, target = self.spin_measurement_a, self.spin_measurement_b
                field = "measurement"
            else:
                source, target = self.spin_level_a, self.spin_level_b
                field = "level_index"
            requested = source.value()
            applied = min(requested, target.maximum())
            target.blockSignals(True)
            target.setValue(applied)
            target.blockSignals(False)
            self.display_state.source("B").__setattr__(field, int(applied))
            if applied != requested:
                messages.append(f"{attribute.replace('shared_', '').capitalize()}: B limitado a {applied}")
        self.lbl_coordination_status.setText("; ".join(messages) if messages else "Coordinación aplicada a los valores actuales")
        self._redraw()

    def _selector_changed(self, slot: str, field: str, value: int):
        slot = slot.upper()
        other_slot = "B" if slot == "A" else "A"
        state = self.display_state.source(slot)
        if field == "window":
            state.window_id = int(value)
            shared = self.display_state.shared_window
            other_spin = self.spin_window_b if other_slot == "B" else self.spin_window_a
        else:
            state.measurement = int(value)
            shared = self.display_state.shared_measurement
            other_spin = self.spin_measurement_b if other_slot == "B" else self.spin_measurement_a
        if shared and (self.dataset_b is not None if other_slot == "B" else self.dataset_a is not None):
            requested = int(value)
            applied = min(requested, other_spin.maximum())
            other_spin.blockSignals(True)
            other_spin.setValue(applied)
            other_spin.blockSignals(False)
            other_state = self.display_state.source(other_slot)
            if field == "window":
                other_state.window_id = other_spin.value()
            else:
                other_state.measurement = other_spin.value()
            if applied != requested:
                self.lbl_coordination_status.setText(
                    f"{field.capitalize()}: {other_slot} limitado a {applied} por su rango disponible"
                )
        self._redraw()

    def _configure_cuts(self, dataset: OCTDataset, slot: str = "a"):
        spin_x = self.spin_x_a if slot == "a" else self.spin_x_b
        spin_y = self.spin_y_a if slot == "a" else self.spin_y_b
        for spin, values in ((spin_x, dataset.X), (spin_y, dataset.Y)):
            if len(values) == 0:
                continue
            spin.setRange(float(np.min(values)), float(np.max(values)))
            spin.setValue(float(np.mean(values)))
            spin.setSingleStep(float(dataset.grid.x_step or 0.001) if spin is spin_x else float(dataset.grid.y_step or 0.001))
        self._configure_volume_coordinate(slot)

    def _volume_orientation_changed(self, slot: str, orientation: str):
        self._configure_volume_coordinate(slot)
        self._redraw()

    def _cut_changed(self, slot: str, field: str, value):
        suffix = slot.lower()
        self.display_state.set_cut(
            slot.upper(),
            getattr(self, f"spin_x_{suffix}").value(),
            getattr(self, f"spin_y_{suffix}").value(),
        )
        self._redraw()

    def _configure_volume_coordinate(self, slot: str = "a"):
        suffix = slot.lower()
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if dataset is None:
            return
        orientation = getattr(self, f"combo_volume_orientation_{suffix}").currentText()
        values = dataset.Z if orientation == "XY" else dataset.Y if orientation == "XZ" else dataset.X
        values = np.asarray(values, dtype=float)
        finite = values[np.isfinite(values)]
        if not finite.size:
            return
        spin = getattr(self, f"volume_coordinate_{suffix}")
        spin.blockSignals(True)
        spin.setRange(float(np.min(finite)), float(np.max(finite)))
        spin.setValue(float(np.mean(finite)))
        spin.setSingleStep(float(dataset.coordinate_tolerance_mm))
        spin.blockSignals(False)

    def _configure_region_level(self, dataset: OCTDataset, slot: str = "a"):
        suffix = slot.lower()
        if dataset.depth_mm is None or len(dataset.X) == 0:
            getattr(self, f"btn_apply_region_level_{suffix}").setEnabled(False)
            return
        finite_x = np.asarray(dataset.X, dtype=float)
        finite_x = finite_x[np.isfinite(finite_x)]
        finite_y = np.asarray(dataset.Y, dtype=float)
        finite_y = finite_y[np.isfinite(finite_y)]
        if not finite_x.size or not finite_y.size:
            getattr(self, f"btn_apply_region_level_{suffix}").setEnabled(False)
            getattr(self, f"lbl_region_level_status_{suffix}").setText("Sin coordenadas finitas")
            return
        for key, values in (("x_min", finite_x), ("x_max", finite_x), ("y_min", finite_y), ("y_max", finite_y)):
            spin = getattr(self, f"spin_region_{key}_{suffix}")
            spin.setRange(float(values.min()), float(values.max()))
        getattr(self, f"spin_region_x_min_{suffix}").setValue(float(finite_x.min()))
        getattr(self, f"spin_region_x_max_{suffix}").setValue(float(finite_x.max()))
        getattr(self, f"spin_region_y_min_{suffix}").setValue(float(finite_y.min()))
        getattr(self, f"spin_region_y_max_{suffix}").setValue(float(finite_y.max()))
        getattr(self, f"btn_apply_region_level_{suffix}").setEnabled(True)
        getattr(self, f"btn_restore_region_level_{suffix}").setEnabled(False)
        getattr(self, f"lbl_region_level_status_{suffix}").setText("Sin nivelado aplicado")

    def _apply_region_leveling(self, slot: str = "A"):
        suffix = slot.lower()
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if dataset is None or dataset.depth_mm is None:
            return
        try:
            level_index = self.display_state.source(slot).level_index
            level = dataset.volume_layout.levels[level_index]
            region = (
                getattr(self, f"spin_region_x_min_{suffix}").value(),
                getattr(self, f"spin_region_x_max_{suffix}").value(),
                getattr(self, f"spin_region_y_min_{suffix}").value(),
                getattr(self, f"spin_region_y_max_{suffix}").value(),
            )
            view = getattr(self, "view_a" if suffix == "a" else "view_b") or TransformedView(dataset)
            view.pipeline.add(self.plugin_registry.create("level_from_regions", {
                "regions_json": json.dumps([region]),
                "win_id": getattr(self, f"spin_window_{suffix}").value(),
                "measurement": getattr(self, f"spin_measurement_{suffix}").value(),
                "level_z_mm": level.z_mm,
                "level_tolerance_mm": dataset.coordinate_tolerance_mm,
            }))
            if suffix == "a":
                self.view_a = view
            else:
                self.view_b = view
            getattr(self, f"lbl_region_level_status_{suffix}").setText(
                f"{slot.upper()}: nivelado aplicado sobre región seleccionada"
            )
            getattr(self, f"btn_restore_region_level_{suffix}").setEnabled(True)
            self._refresh_pipeline_status(slot)
            self._redraw()
        except (IndexError, TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Nivelado inválido", str(exc))

    def _configure_filter(self, dataset: OCTDataset, slot: str = "a"):
        suffix = slot.lower()
        spin_min = getattr(self, f"spin_depth_mm_min_{suffix}")
        spin_max = getattr(self, f"spin_depth_mm_max_{suffix}")
        spin_offset = getattr(self, f"spin_depth_mm_offset_{suffix}")
        btn_apply = getattr(self, f"btn_apply_mask_{suffix}")
        btn_restore = getattr(self, f"btn_restore_mask_{suffix}")
        status = getattr(self, f"lbl_mask_status_{suffix}")
        self._set_plugin_buttons_enabled("filter", slot, dataset.depth_mm is not None)
        plane_window = getattr(self, f"spin_level_plane_window_{suffix}")
        plane_measurement = getattr(self, f"spin_level_plane_measurement_{suffix}")
        plane_apply = getattr(self, f"btn_apply_level_plane_{suffix}")
        plane_restore = getattr(self, f"btn_restore_level_plane_{suffix}")
        plane_status = getattr(self, f"lbl_level_plane_status_{suffix}")
        if dataset.depth_mm is None:
            btn_apply.setEnabled(False)
            plane_window.setRange(0, 0)
            plane_measurement.setRange(0, 0)
            plane_apply.setEnabled(False)
            plane_restore.setEnabled(False)
            plane_status.setText("Sin OPD disponible")
            return
        plane_window.setRange(0, max(0, dataset.depth_mm.shape[2] - 1))
        plane_measurement.setRange(0, max(0, dataset.depth_mm.shape[1] - 1))
        plane_window.setValue(0)
        plane_measurement.setValue(0)
        plane_apply.setEnabled(bool(dataset.X.size >= 3))
        plane_restore.setEnabled(False)
        plane_status.setText("Sin nivelado por plano aplicado")
        values = np.asarray(dataset.depth_mm, dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            btn_apply.setEnabled(False)
            plane_apply.setEnabled(False)
            return
        scale, unit = display_scale(finite)
        setattr(self, f"_depth_mm_filter_scale_{suffix}", scale)
        setattr(self, f"_depth_mm_filter_unit_{suffix}", unit)
        getattr(self, f"lbl_depth_mm_min_{suffix}").setText(f"Mínimo ({unit}):")
        getattr(self, f"lbl_depth_mm_max_{suffix}").setText(f"Máximo ({unit}):")
        getattr(self, f"lbl_depth_mm_offset_{suffix}").setText(f"Offset ({unit}):")
        decimals = 3 if unit == "µm" else 6
        step = 0.1 if unit == "µm" else 0.000001
        spin_min.setDecimals(decimals)
        spin_max.setDecimals(decimals)
        spin_offset.setDecimals(decimals)
        spin_min.setSingleStep(step)
        spin_max.setSingleStep(step)
        spin_offset.setSingleStep(step)
        spin_offset.setValue(0.0)
        getattr(self, f"chk_offset_zero_{suffix}").setChecked(False)
        spin_min.setValue(float(finite.min()) * scale)
        spin_max.setValue(float(finite.max()) * scale)
        btn_apply.setEnabled(True)
        btn_restore.setEnabled(False)
        status.setText("Sin máscara aplicada")

    @staticmethod
    def _is_depth_mm_filter_transform(transform) -> bool:
        if not isinstance(transform, PluginTransform):
            return False
        return getattr(transform.spec, "id", None) in {
            "mask_depth_range", "offset_depth", "offset_minimum_to_zero", "invert_depth",
        }

    def _apply_depth_mm_mask(self, slot: str = "A"):
        suffix = slot.lower()
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if dataset is None:
            return
        try:
            scale = getattr(self, f"_depth_mm_filter_scale_{suffix}")
            minimum = getattr(self, f"spin_depth_mm_min_{suffix}").value() / scale
            maximum = getattr(self, f"spin_depth_mm_max_{suffix}").value() / scale
            offset = getattr(self, f"spin_depth_mm_offset_{suffix}").value() / scale
            offset_zero = getattr(self, f"chk_offset_zero_{suffix}").isChecked()
            invert = getattr(self, f"chk_invert_depth_{suffix}").isChecked()
            current_view = self.view_a if suffix == "a" else self.view_b
            view = TransformedView(dataset)
            new_depth_mm_transforms = [self.plugin_registry.create("mask_depth_range", {
                "minimum_mm": minimum,
                "maximum_mm": maximum,
            })]
            if offset:
                new_depth_mm_transforms.append(self.plugin_registry.create("offset_depth", {"offset_mm": offset}))
            if offset_zero:
                automatic_offset = self.plugin_registry.create("offset_minimum_to_zero")
                new_depth_mm_transforms.append(automatic_offset)
            else:
                automatic_offset = None
            if invert:
                new_depth_mm_transforms.append(self.plugin_registry.create("invert_depth"))

            inserted = False
            existing_steps = current_view.pipeline.steps if current_view is not None else []
            for existing in existing_steps:
                if self._is_depth_mm_filter_transform(existing):
                    if not inserted:
                        for depth_mm_transform in new_depth_mm_transforms:
                            view.pipeline.add(depth_mm_transform)
                        inserted = True
                    continue
                view.pipeline.add(existing)
            if not inserted:
                for depth_mm_transform in new_depth_mm_transforms:
                    view.pipeline.add(depth_mm_transform)

            if automatic_offset is not None:
                view.transformed_data
                offset += getattr(automatic_offset, "offset_mm", 0.0)
                # El control muestra la suma efectiva del offset manual y el
                # automático, en la misma unidad visible que el resto del filtro.
                getattr(self, f"spin_depth_mm_offset_{suffix}").setValue(offset * scale)
            label = suffix.upper()
            self.display_state.set_filter(label, minimum, maximum, offset_mm=offset, invert=invert)
            if suffix == "a":
                self.view_a = view
            else:
                self.view_b = view
            getattr(self, f"lbl_mask_status_{suffix}").setText(
                f"{label}: {view.affected_points} puntos enmascarados"
            )
            getattr(self, f"btn_restore_mask_{suffix}").setEnabled(True)
            self._refresh_pipeline_status(slot)
            self._redraw()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Rango de OPD inválido", str(exc))

    def _restore_pipeline_transforms(self, slot: str, status_name: str, button_name: str, empty_text: str, plugin_id: str):
        suffix = slot.lower()
        view = self.view_a if suffix == "a" else self.view_b
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if view is None or dataset is None:
            return
        rebuilt = TransformedView(dataset)
        removed = False
        for transform in view.pipeline.steps:
            is_target = (
                isinstance(transform, PluginTransform)
                and getattr(transform.spec, "id", None) == plugin_id
            )
            if is_target:
                removed = True
                continue
            rebuilt.pipeline.add(transform)
        if not removed:
            return
        if suffix == "a":
            self.view_a = rebuilt if not rebuilt.pipeline.is_empty else None
        else:
            self.view_b = rebuilt if not rebuilt.pipeline.is_empty else None
        getattr(self, status_name.format(suffix=suffix)).setText(empty_text)
        getattr(self, button_name.format(suffix=suffix)).setEnabled(False)
        self._refresh_pipeline_status(slot)
        self._redraw()

    def _restore_region_leveling(self, slot: str = "A"):
        self._restore_pipeline_transforms(
            slot,
            "lbl_region_level_status_{suffix}",
            "btn_restore_region_level_{suffix}",
            "Sin nivelado aplicado",
            plugin_id="level_from_regions",
        )

    def _restore_median_filter(self, slot: str = "A"):
        self._restore_pipeline_transforms(
            slot,
            "lbl_median_status_{suffix}",
            "btn_restore_median_{suffix}",
            "Sin mediana aplicada",
            plugin_id="filter_median",
        )

    def _restore_depth_mm_mask(self, slot: str = "A"):
        suffix = slot.lower()
        view = self.view_a if suffix == "a" else self.view_b
        dataset = self.dataset_a if suffix == "a" else self.dataset_b
        if view is None or dataset is None:
            return
        rebuilt = TransformedView(dataset)
        removed = False
        for transform in view.pipeline.steps:
            if self._is_depth_mm_filter_transform(transform):
                removed = True
                continue
            rebuilt.pipeline.add(transform)
        if not removed:
            return
        if suffix == "a":
            self.view_a = rebuilt if not rebuilt.pipeline.is_empty else None
        else:
            self.view_b = rebuilt if not rebuilt.pipeline.is_empty else None
        getattr(self, f"chk_invert_depth_{suffix}").setChecked(False)
        getattr(self, f"chk_offset_zero_{suffix}").setChecked(False)
        getattr(self, f"lbl_mask_status_{suffix}").setText("Sin máscara aplicada")
        getattr(self, f"btn_restore_mask_{suffix}").setEnabled(False)
        self._refresh_pipeline_status(slot)
        self._redraw()

    def _shown_a(self):
        return self.view_a or self.dataset_a

    def _shown_b(self):
        return self.view_b or self.dataset_b

    def _close_b(self):
        self.dataset_b = None
        self.view_b = None
        self.group_b.setVisible(False)
        self.btn_close_b.setEnabled(False)
        self._refresh_comparison_controls()
        self.lbl_b.setText("No cargada")
        if self.combo_extract_source.currentText() == "B":
            self.combo_extract_source.setCurrentText("A")
        if self.combo_extract_source.findText("B") >= 0:
            self.combo_extract_source.removeItem(self.combo_extract_source.findText("B"))
        self._redraw()
        self.lbl_status.setText("Muestra B cerrada")

    def _extract_profile(self, axis: str):
        slot = self.combo_extract_source.currentText().lower()
        source = self._shown_a() if slot == "a" else self._shown_b()
        if source is None:
            self.lbl_derived_status.setText("La fuente seleccionada no está cargada")
            return
        spin_x = self.spin_x_a if slot == "a" else self.spin_x_b
        spin_y = self.spin_y_a if slot == "a" else self.spin_y_b
        spin_window = self.spin_window_a if slot == "a" else self.spin_window_b
        spin_measurement = self.spin_measurement_a if slot == "a" else self.spin_measurement_b
        try:
            if axis == "x":
                derived = extract_profile_x(
                    source,
                    requested_y_mm=spin_y.value(),
                    window_index=spin_window.value(),
                    measurement_index=spin_measurement.value(),
                )
            else:
                derived = extract_profile_y(
                    source,
                    requested_x_mm=spin_x.value(),
                    window_index=spin_window.value(),
                    measurement_index=spin_measurement.value(),
                )
        except (IndexError, ValueError, TypeError) as exc:
            self.lbl_derived_status.setText(f"Extracción no disponible: {exc}")
            return
        self.derived_objects.append(derived)
        self.lbl_derived_status.setText(
            f"Último: {derived.name}<br>"
            f"Puntos: {derived.n_points} · Proveniencia: {derived.provenance.extraction_type.name}"
        )
        self.lbl_status.setText(f"Objeto derivado creado: {derived.name}")

    def _export_options_for_tab(self, index: int):
        """Formatos permitidos por la vista activa, sin saturar sus controles."""
        if index == 4:  # Cortes: la salida tabular es la relevante.
            return ("PNG", "CSV")
        return ("PNG", "CSV", "NPZ", "HDF5")

    def _export_sources(self):
        sources = []
        source_a = self._shown_a()
        source_b = self._shown_b()
        if source_a is not None:
            sources.append(("Muestra A (vista actual)", source_a))
        if source_b is not None:
            sources.append(("Muestra B (vista actual)", source_b))
        for derived in self.derived_objects:
            sources.append((f"Perfil derivado: {derived.name}", derived))
        return sources

    def _active_canvas(self):
        canvases = (
            self.canvas_levels,
            self.canvas_3d,
            self.canvas_depth_mm,
            self.canvas_amp,
            self.canvas_cuts,
            self.canvas_hist,
        )
        return canvases[self.tabs.currentIndex()]

    def _export_to_path(self, fmt: str, source, filepath: str) -> str:
        """Exportar una fuente o la figura activa usando el formato contextual."""
        if fmt == "PNG":
            return to_png(self._active_canvas().figure, filepath)
        if source is None:
            raise ValueError("No hay una fuente de datos seleccionada")
        if fmt == "CSV":
            return to_csv(source, filepath)
        if fmt == "NPZ":
            return to_npz(source, filepath)
        if fmt == "HDF5":
            return to_h5(source, filepath)
        raise ValueError(f"Formato de exportación no soportado: {fmt}")

    def _show_export_dialog(self):
        if self.dataset_a is None:
            QMessageBox.information(self, "Exportar", "Cargá primero la muestra A.")
            return
        index = self.tabs.currentIndex()
        tab_name = self.tabs.tabText(index)
        dialog = ExportDialog(tab_name, self._export_options_for_tab(index), self._export_sources(), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            f"Exportar {tab_name}",
            "",
            {
                "PNG": "PNG (*.png)",
                "CSV": "CSV (*.csv)",
                "NPZ": "NPZ (*.npz)",
                "HDF5": "HDF5 (*.h5 *.hdf5)",
            }[dialog.selected_format],
        )
        if not filepath:
            return
        try:
            fmt = dialog.selected_format
            output = self._export_to_path(fmt, dialog.selected_source, filepath)
        except (OSError, TypeError, ValueError, ImportError) as exc:
            QMessageBox.warning(self, "Exportación no disponible", str(exc))
            return
        self.lbl_status.setText(f"Exportado {fmt}: {output}")

    def _refresh_comparison_controls(self):
        has_both = self.dataset_a is not None and self.dataset_b is not None
        self.btn_compare_ab.setEnabled(has_both)
        if hasattr(self, "btn_assemble_surface"):
            self.btn_assemble_surface.setEnabled(has_both)

    def _comparison_pair(self):
        if self.dataset_a is None or self.dataset_b is None:
            raise ValueError("Se necesitan las muestras A y B")
        return ComparisonPair(self._shown_a(), self._shown_b())

    def _create_comparison_difference(self):
        pair = self._comparison_pair()
        win_id = self.spin_window_a.value()
        measurement = self.spin_measurement_a.value()
        derived = pair.difference(window_index=win_id, measurement_index=measurement)
        self.derived_objects.append(derived)
        self.lbl_status.setText(
            f"Creada derivada A − B: {derived.n_points} puntos comunes; "
            "queda disponible para exportación."
        )
        return derived

    def _show_comparison(self):
        try:
            pair = self._comparison_pair()
            stats = pair.statistics(
                window_index=self.spin_window_a.value(),
                measurement_index=self.spin_measurement_a.value(),
            )
        except (TypeError, ValueError, IndexError) as exc:
            QMessageBox.warning(self, "Comparación no disponible", str(exc))
            return
        dialog = ComparisonDialog(stats, self._create_comparison_difference, self)
        dialog.exec_()

    def _show_metadata(self):
        if self.dataset_a is None:
            message = QMessageBox(self)
            message.setWindowTitle("Metadata")
            message.setIcon(QMessageBox.Information)
            message.setText("Cargá primero la muestra A.")
            message.setStyleSheet("""
                QMessageBox { background: #f2f2f2; }
                QMessageBox QLabel { color: #202020; min-width: 320px; }
                QMessageBox QPushButton { color: #ffffff; background: #3a4654; padding: 6px 18px; }
            """)
            message.exec_()
            return
        dialog = MetadataDialog(self.dataset_a, self.dataset_b, self)
        dialog.exec_()

    def _map_clicked(self, event):
        if self.dataset_a is None or event.inaxes is None:
            return
        label = getattr(event.inaxes, "_oct_sample_label", None)
        if label not in {"A", "B"}:
            return
        source = self._shown_a() if label == "A" else self._shown_b()
        if source is None:
            return
        spin_x = self.spin_x_a if label == "A" else self.spin_x_b
        spin_y = self.spin_y_a if label == "A" else self.spin_y_b
        if event.xdata is not None:
            spin_x.setValue(self._source_coordinate(source, "X", event.xdata))
        if event.ydata is not None:
            spin_y.setValue(self._source_coordinate(source, "Y", event.ydata))

    @staticmethod
    def _display_coordinate(source, axis: str, source_value: float) -> float:
        """Convertir una coordenada de control original a la vista transformada."""
        axis = axis.upper()
        if not isinstance(source, TransformedView):
            return float(source_value)
        original = getattr(source.dataset, axis)
        transformed = getattr(source.transformed_data, axis)
        valid = np.isfinite(original) & np.isfinite(transformed)
        if not valid.any():
            return float(source_value)
        index = np.flatnonzero(valid)[int(np.argmin(np.abs(original[valid] - source_value)))]
        return float(transformed[index])

    @staticmethod
    def _source_coordinate(source, axis: str, display_value: float) -> float:
        """Convertir una coordenada dibujada a la coordenada de control original."""
        axis = axis.upper()
        if not isinstance(source, TransformedView):
            return float(display_value)
        original = getattr(source.dataset, axis)
        transformed = getattr(source.transformed_data, axis)
        valid = np.isfinite(original) & np.isfinite(transformed)
        if not valid.any():
            return float(display_value)
        index = np.flatnonzero(valid)[int(np.argmin(np.abs(transformed[valid] - display_value)))]
        return float(original[index])

    def _update_sidebar_for_tab(self, index: int):
        """Mantener disponibles las etapas de preparación A/B.

        La navegación común de Selección/FILTROS/GEOMETRÍA determina el
        contexto visible. La pestaña de análisis ya no oculta filtros ni
        geometría, porque esas herramientas son independientes de la vista.
        """
        show_level_controls = index == 0
        show_selectors = index != 0
        show_cuts = index == 4
        show_extraction = index == 4
        show_processing = True
        show_region_leveling = True
        show_median = True
        show_geometry = True

        for level_controls in (self.level_controls_a, self.level_controls_b):
            level_controls.setVisible(show_level_controls)
        if hasattr(self, "sample_mode_bar"):
            mode_enabled = (True, True, show_geometry)
            for mode_index, enabled in enumerate(mode_enabled):
                self.sample_mode_bar.setTabEnabled(mode_index, enabled)
            if not mode_enabled[self.sample_mode_bar.currentIndex()]:
                self.sample_mode_bar.setCurrentIndex(0)
        for selector_group in (self.selector_group_a, self.selector_group_b):
            selector_group.setVisible(show_selectors)
        for cut_group in (self.cut_group_a, self.cut_group_b):
            cut_group.setVisible(show_cuts)
        for volume_group in (self.volume_group_a, self.volume_group_b):
            volume_group.setVisible(show_cuts)

        self._update_coordination_visibility()
        self.extraction_group.setVisible(show_extraction)
        for filters_group in (self.filters_group_a, self.filters_group_b):
            filters_group.setVisible(show_processing or show_region_leveling or show_median)
        for filter_group in (self.filter_group_a, self.filter_group_b):
            filter_group.setVisible(show_processing)
        for region_group in (self.region_level_group_a, self.region_level_group_b):
            region_group.setVisible(show_region_leveling)
        for median_group in (self.median_group_a, self.median_group_b):
            median_group.setVisible(show_median)
        for geometry_group in (self.geometry_group_a, self.geometry_group_b):
            geometry_group.setVisible(show_geometry)
        self.pipeline_group_a.setVisible(self.dataset_a is not None)
        self.pipeline_group_b.setVisible(self.dataset_b is not None)
        if hasattr(self, "preparation_group"):
            self.preparation_group.setVisible(
                self.sample_mode_bar.currentIndex() == 0
                and (self.dataset_a is not None or self.dataset_b is not None)
            )
        self.pipeline_header.setVisible(True)
        self._refresh_sample_card_heights()

    def _redraw(self, *_args):
        self._update_sidebar_for_tab(self.tabs.currentIndex())
        if self.dataset_a is None:
            for canvas in (self.canvas_levels, self.canvas_depth_mm, self.canvas_amp, self.canvas_3d, self.canvas_hist, self.canvas_cuts):
                canvas.figure.clear()
                canvas.canvas.draw_idle()
            return
        index = self.tabs.currentIndex()
        if index == 0:
            self._draw_levels()
        elif index == 1:
            self._draw_3d()
        elif index == 2:
            self._draw_maps("depth_mm")
        elif index == 3:
            self._draw_maps("amplitude")
        elif index == 4:
            self._draw_cuts()
        else:
            self._draw_histogram()

    def _draw_levels(self):
        canvas = self.canvas_levels
        canvas.figure.clear()
        sources = [(self._shown_a(), "A")]
        if self.dataset_b is not None:
            sources.append((self._shown_b(), "B"))
        axes = [
            canvas.figure.add_subplot(1, len(sources), index + 1, projection="3d")
            for index in range(len(sources))
        ]
        for axis, (source, label) in zip(axes, sources):
            dataset = source.dataset if isinstance(source, TransformedView) else source
            displayed = source.transformed_data if isinstance(source, TransformedView) else source
            layout = dataset.volume_layout
            state = self.display_state.source(label)
            x_values = displayed.X[np.isfinite(displayed.X)]
            y_values = displayed.Y[np.isfinite(displayed.Y)]
            x0, x1 = (float(x_values.min()), float(x_values.max())) if x_values.size else (0.0, 1.0)
            y0, y1 = (float(y_values.min()), float(y_values.max())) if y_values.size else (0.0, 1.0)
            if x0 == x1:
                x1 = x0 + 1.0
            if y0 == y1:
                y1 = y0 + 1.0
            z_values = layout.z_values_mm
            finite_z = z_values[np.isfinite(z_values)]
            z_floor = float(finite_z.min()) if finite_z.size else 0.0
            z_ceiling = float(finite_z.max()) if finite_z.size else max(1.0, float(layout.n_levels - 1))
            if z_floor == z_ceiling:
                z_ceiling = z_floor + 1.0
            z_span = max(z_ceiling - z_floor, 1e-9)
            for level in layout.levels:
                z = float(level.z_mm) if np.isfinite(level.z_mm) else z_floor
                excluded = level.index in state.excluded_levels
                selected = level.index == state.level_index and not excluded
                normalized_z = np.clip((z - z_floor) / z_span, 0.0, 1.0)
                if selected:
                    face_color, edge_color, alpha = "#ef4444", "#991b1b", 0.70
                elif excluded:
                    face_color, edge_color, alpha = "#64748b", "#475569", 0.08
                else:
                    face_color = matplotlib.colormaps["viridis"](0.22 + 0.60 * normalized_z)
                    edge_color, alpha = "#2563eb", 0.22
                vertices = [[
                    (x0, y0, z),
                    (x1, y0, z),
                    (x1, y1, z),
                    (x0, y1, z),
                ]]
                card = Poly3DCollection(
                    vertices,
                    facecolors=[face_color],
                    edgecolors=[edge_color],
                    linewidths=2.4 if selected else 1.0,
                    alpha=alpha,
                )
                axis.add_collection3d(card)
                if selected:
                    axis.text(x0, y0, z, f"Nivel {level.index}", color="#991b1b", weight="bold")

            # Conectores de las cuatro esquinas: hacen visible la profundidad del mazo.
            ordered_levels = [
                float(level.z_mm) for level in layout.levels if np.isfinite(level.z_mm)
            ]
            ordered_levels.sort()
            for z_low, z_high in zip(ordered_levels, ordered_levels[1:]):
                for x_corner, y_corner in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                    axis.plot(
                        [x_corner, x_corner], [y_corner, y_corner], [z_low, z_high],
                        color="#64748b", alpha=0.28, linewidth=0.8,
                    )
            axis.set_box_aspect((max(x1 - x0, 1e-6), max(y1 - y0, 1e-6), max(z_span, 0.35 * max(x1 - x0, y1 - y0))))
            axis.view_init(elev=24, azim=-58)
            axis.set_xlim(x0, x1)
            axis.set_ylim(y0, y1)
            axis.set_zlim(z_floor, z_ceiling)
            axis.set_xlabel("X (mm)")
            axis.set_ylabel("Y (mm)")
            axis.set_zlabel("Z (mm)")
            axis.set_title(
                f"{label}: {layout.dimensions[0]} × {layout.dimensions[1]} × {layout.dimensions[2]}\n"
                f"Nivel seleccionado: {state.level_index}"
            )
        canvas.figure.subplots_adjust(left=0.04, right=0.90, bottom=0.19, top=0.84, wspace=0.18)
        canvas.canvas.draw_idle()

    def _draw_maps(self, kind: str):
        canvas = self.canvas_depth_mm if kind == "depth_mm" else self.canvas_amp
        canvas.figure.clear()
        datasets = [self._shown_a()] + ([self._shown_b()] if self.dataset_b else [])
        axes = canvas.figure.subplots(1, len(datasets), squeeze=False).ravel()
        comparison_values = []
        for dataset, label in zip(datasets, ("A", "B")):
            try:
                values = self._map_values(dataset, kind, label)
            except (IndexError, ValueError):
                continue
            if values is not None:
                comparison_values.append(values[2])
        scale, unit = shared_display_scale(comparison_values)
        color_min, color_max = shared_color_limits(comparison_values)
        display_min, display_max = color_min * scale, color_max * scale
        for axis, dataset, label in zip(axes, datasets, ("A", "B")):
            axis._oct_sample_label = label
            try:
                values = self._map_values(dataset, kind, label)
            except (IndexError, ValueError) as exc:
                axis.text(
                    0.5, 0.5, str(exc), ha="center", va="center",
                    transform=axis.transAxes,
                )
                axis.set_axis_off()
                continue
            if values is None:
                axis.text(0.5, 0.5, "Sin datos", ha="center", va="center", transform=axis.transAxes)
                continue
            x_grid, y_grid, grid = values
            spin_measurement = self.spin_measurement_a if label == "A" else self.spin_measurement_b
            spin_window = self.spin_window_a if label == "A" else self.spin_window_b
            assembly_patches = self._surface_assembly_patch_arrays(dataset, kind, label)
            if assembly_patches is not None:
                image = None
                for patch in assembly_patches:
                    native_grid = _native_patch_grid(
                        patch["x"], patch["y"], patch["values"], patch["tolerance"]
                    )
                    if native_grid is not None:
                        patch_x, patch_y, patch_grid = native_grid
                        image = axis.pcolormesh(
                            patch_x, patch_y, patch_grid * scale, shading="auto",
                            cmap="viridis" if kind == "depth_mm" else "inferno",
                            vmin=display_min, vmax=display_max,
                        )
                    else:
                        image = axis.scatter(
                            patch["x"], patch["y"], c=patch["values"] * scale,
                            cmap="viridis" if kind == "depth_mm" else "inferno",
                            vmin=display_min, vmax=display_max,
                            marker="s", s=30, linewidths=0,
                        )
                if image is None:
                    axis.text(0.5, 0.5, "Sin puntos en el nivel seleccionado", ha="center", va="center", transform=axis.transAxes)
                    axis.set_axis_off()
                    continue
                axis.text(
                    0.02, 0.98, "Ensamble nativo: parches separados",
                    transform=axis.transAxes, va="top", fontsize=8,
                    bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "none"},
                )
            else:
                finite_grid = np.isfinite(x_grid).all() and np.isfinite(y_grid).all()
                if finite_grid:
                    image = axis.pcolormesh(
                        x_grid, y_grid, grid * scale, shading="auto",
                        cmap="viridis" if kind == "depth_mm" else "inferno",
                        vmin=display_min, vmax=display_max,
                    )
                else:
                    raw_x, raw_y, _raw_z, raw_depth_mm, raw_amplitude, _layout = self._level_arrays(dataset, label)
                    raw_values = (
                        raw_depth_mm[:, spin_measurement.value(), spin_window.value()]
                        if kind == "depth_mm"
                        else raw_amplitude[:, spin_measurement.value(), spin_window.value()]
                        if raw_amplitude is not None else None
                    )
                    if raw_values is None:
                        axis.text(0.5, 0.5, "Sin amplitud", ha="center", va="center", transform=axis.transAxes)
                        continue
                    valid = np.isfinite(raw_x) & np.isfinite(raw_y) & np.isfinite(raw_values)
                    image = axis.scatter(
                        raw_x[valid], raw_y[valid], c=raw_values[valid] * scale,
                        cmap="viridis" if kind == "depth_mm" else "inferno", s=18,
                        vmin=display_min, vmax=display_max,
                    )
                    axis.text(
                        0.02, 0.98, "Grilla incompleta: vista de puntos",
                        transform=axis.transAxes, va="top", fontsize=8,
                        bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none"},
                    )
            canvas.figure.colorbar(
                image, ax=axis, shrink=0.78,
                label=f"OPD ({unit})" if kind == "depth_mm" else "Amplitud",
            )
            spin_x = self.spin_x_a if label == "A" else self.spin_x_b
            spin_y = self.spin_y_a if label == "A" else self.spin_y_b
            axis.axvline(self._display_coordinate(dataset, "X", spin_x.value()), color="white", linestyle="--", linewidth=0.8)
            axis.axhline(self._display_coordinate(dataset, "Y", spin_y.value()), color="white", linestyle="--", linewidth=0.8)
            axis.set_xlabel("X (mm)")
            axis.set_ylabel("Y (mm)")
            axis.set_title(f"{label}: {dataset.sample_name or dataset.filename}")
            axis.set_aspect("equal")
        canvas.figure.subplots_adjust(left=0.04, right=0.96, bottom=0.10, top=0.93, wspace=0.14)
        canvas.canvas.draw_idle()

    def _draw_3d_native_patches(self, canvas, payloads):
        """Renderizar cada región 3D sin conectar parches independientes."""
        all_values = [patch["values"] for patches, _label, _cmap in payloads for patch in patches]
        if not all_values:
            axis = canvas.figure.add_subplot(111)
            axis.text(0.5, 0.5, "Sin puntos en el nivel seleccionado", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
            canvas.canvas.draw_idle()
            return

        scale, unit = display_scale(np.concatenate(all_values))
        finite_value_groups = [values[np.isfinite(values)] for values in all_values if np.isfinite(values).any()]
        if not finite_value_groups:
            axis = canvas.figure.add_subplot(111, projection="3d")
            axis.text2D(0.5, 0.5, "Sin valores finitos para representar", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
            canvas.canvas.draw_idle()
            return
        finite_values = np.concatenate(finite_value_groups)
        value_min, value_max = float(finite_values.min() * scale), float(finite_values.max() * scale)
        if value_min == value_max:
            value_max = value_min + 1.0
        axes = [
            canvas.figure.add_subplot(1, len(payloads), index + 1, projection="3d")
            for index in range(len(payloads))
        ]
        for axis, (patches, label, cmap) in zip(axes, payloads):
            axis.set_proj_type("ortho")
            all_x = np.concatenate([patch["x"] for patch in patches])
            all_y = np.concatenate([patch["y"] for patch in patches])
            all_z = np.concatenate([patch["values"] for patch in patches]) * scale
            for patch in patches:
                native_grid = _native_patch_grid(
                    patch["x"], patch["y"], patch["values"], patch["tolerance"]
                )
                if native_grid is not None:
                    patch_x, patch_y, patch_grid = native_grid
                    axis.plot_surface(
                        patch_x, patch_y, patch_grid * scale,
                        cmap=cmap, vmin=value_min, vmax=value_max,
                        linewidth=0, antialiased=True, alpha=0.84,
                    )
                else:
                    axis.scatter(
                        patch["x"], patch["y"], patch["values"] * scale,
                        c=patch["values"] * scale, cmap=cmap,
                        vmin=value_min, vmax=value_max,
                        marker="s", s=22, depthshade=False,
                    )
            x_min, x_max = float(np.min(all_x)), float(np.max(all_x))
            y_min, y_max = float(np.min(all_y)), float(np.max(all_y))
            z_min_values = all_z[np.isfinite(all_z)]
            if z_min_values.size:
                z_min, z_max = float(z_min_values.min()), float(z_min_values.max())
            else:
                z_min, z_max = 0.0, 1.0
            if x_min == x_max:
                x_max += 1.0
            if y_min == y_max:
                y_max += 1.0
            if z_min == z_max:
                z_max += 1.0
            axis.set_xlim(x_min, x_max)
            axis.set_ylim(y_min, y_max)
            axis.set_zlim(z_min, z_max)
            axis._workbench_native_surface = True
            axis._workbench_surface_aspect = True
            _refresh_native_3d_box_aspect(axis)
            axis.set_xlabel("X (mm)", labelpad=8)
            axis.set_ylabel("Y (mm)", labelpad=8)
            axis.set_zlabel(f"OPD ({unit})", labelpad=8)
            axis.tick_params(axis="both", which="major", pad=2, labelsize=8)
            axis.set_title(f"{label}: Superficie OPD")
            axis.view_init(elev=24, azim=-58)
        canvas.figure.subplots_adjust(left=0.02, right=0.97, bottom=0.12, top=0.90, wspace=0.10)
        canvas.canvas.draw_idle()

    def _draw_3d(self):
        """Mostrar una superficie OPD independiente para cada muestra."""
        canvas = self.canvas_3d
        canvas.figure.clear()
        sources = [(self._shown_a(), "A", "viridis")]
        if self.dataset_b is not None:
            sources.append((self._shown_b(), "B", "plasma"))

        native_by_source = []
        for source, label, _cmap in sources:
            if source is None:
                native_by_source.append(None)
                continue
            try:
                native_by_source.append(self._surface_assembly_patch_arrays(source, "depth_mm", label))
            except (IndexError, ValueError):
                native_by_source.append(None)
        if any(patches is not None for patches in native_by_source):
            native_payloads = []
            for (source, label, cmap), patches in zip(sources, native_by_source):
                if patches is not None:
                    native_payloads.append((patches, label, cmap))
                    continue
                try:
                    x_grid, y_grid, z_grid = self._map_values(source, "depth_mm", label)
                except (IndexError, ValueError):
                    continue
                valid = np.isfinite(x_grid) & np.isfinite(y_grid) & np.isfinite(z_grid)
                if np.any(valid):
                    native_payloads.append(([
                        {
                            "name": "malla",
                            "x": x_grid[valid],
                            "y": y_grid[valid],
                            "values": z_grid[valid],
                            "tolerance": 1e-9,
                        }
                    ], label, cmap))
            self._draw_3d_native_patches(canvas, native_payloads)
            return

        prepared = []
        all_values = []
        for source, label, cmap in sources:
            if source is None:
                continue
            try:
                x_grid, y_grid, z_grid = self._map_values(source, "depth_mm", label)
            except (IndexError, ValueError):
                continue
            if not np.isfinite(z_grid).any():
                continue
            prepared.append((x_grid, y_grid, z_grid, label, cmap))
            all_values.append(z_grid[np.isfinite(z_grid)])

        if not prepared:
            axis = canvas.figure.add_subplot(111)
            axis.text(
                0.5, 0.5,
                "La vista 3D requiere una medición 2D con datos OPD",
                ha="center", va="center", transform=axis.transAxes,
            )
            axis.set_axis_off()
            canvas.canvas.draw_idle()
            return

        scale, unit = display_scale(np.concatenate(all_values))
        axes = [
            canvas.figure.add_subplot(1, len(prepared), index + 1, projection="3d")
            for index in range(len(prepared))
        ]
        for axis, (x_grid, y_grid, z_grid, label, cmap) in zip(axes, prepared):
            axis.set_proj_type("ortho")
            axis.plot_surface(
                x_grid, y_grid, z_grid * scale,
                cmap=cmap, linewidth=0, antialiased=True, alpha=0.78,
            )
            axis._workbench_surface_aspect = True
            _refresh_native_3d_box_aspect(axis)
            axis.set_xlabel("X (mm)")
            axis.set_ylabel("Y (mm)")
            axis.set_zlabel(f"OPD ({unit})")
            axis.set_title(f"{label}: Superficie OPD")
        canvas.figure.subplots_adjust(left=0.02, right=0.97, bottom=0.12, top=0.90, wspace=0.10)
        canvas.canvas.draw_idle()

    def _draw_histogram(self):
        canvas = self.canvas_hist
        canvas.figure.clear()
        axis = canvas.figure.add_subplot(111)
        plotted = False
        datasets = ((self._shown_a(), "A", "#2774ae"), (self._shown_b(), "B", "#d46a1f"))
        raw_groups = []
        for dataset, label, _color in datasets:
            if dataset is None:
                continue
            try:
                raw_groups.append(self._map_values(dataset, "depth_mm", label)[2])
            except (IndexError, ValueError):
                continue
        scale, unit = shared_display_scale(raw_groups)
        for dataset, label, color in datasets:
            if dataset is None:
                continue
            try:
                values = self._map_values(dataset, "depth_mm", label)[2]
            except (IndexError, ValueError):
                continue
            values = values[np.isfinite(values)]
            if values.size:
                axis.hist(values * scale, bins=50, alpha=0.55, label=label, color=color)
                plotted = True
        axis.set_xlabel(f"OPD ({unit})")
        axis.set_ylabel("Cuentas")
        axis.set_title("Histograma de OPD")
        axis.grid(alpha=0.25)
        axis.legend() if self.dataset_b else None
        canvas.figure.subplots_adjust(left=0.10, right=0.94, bottom=0.18, top=0.86)
        canvas.canvas.draw_idle()

    def _draw_cuts(self):
        canvas = self.canvas_cuts
        canvas.figure.clear()
        sources = [(self._shown_a(), "A", "#2774ae")]
        if self.dataset_b is not None:
            sources.append((self._shown_b(), "B", "#d46a1f"))
        axes = canvas.figure.subplots(len(sources), 2, squeeze=False)
        previews = []
        raw_groups = []
        for source, label, _color in sources:
            if source is None:
                previews.append(None)
                continue
            mode = getattr(self, f"combo_cut_mode_{label.lower()}").currentText()
            if mode == "B-scan espectral":
                try:
                    bscan = self._selected_bscan(source, label)
                except (IndexError, ValueError, TypeError):
                    bscan = None
                previews.append(("BSCAN", bscan))
                continue
            orientation = getattr(self, f"combo_volume_orientation_{label.lower()}").currentText()
            try:
                preview = (
                    self._selected_cuts(source, label)
                    if orientation == "XY"
                    else self._selected_volume_slice(source, label, orientation)
                )
            except (IndexError, ValueError, TypeError):
                preview = None
            previews.append((orientation, preview))
            if orientation == "XY" and preview is not None:
                raw_groups.append(preview["x_depth_mm"])
        scale, unit = shared_display_scale(raw_groups)
        for row, ((source, label, color), item) in enumerate(zip(sources, previews)):
            axis_x, axis_y = axes[row]
            orientation, preview = item if item is not None else ("XY", None)
            for axis in (axis_x, axis_y):
                axis.grid(alpha=0.25)
            if source is None:
                axis_x.set_title(f"{label}: sin fuente")
                continue
            if orientation == "BSCAN":
                axis_x.set_title(f"{label}: B-scan espectral")
                axis_x.set_xlabel("Posición X (mm)")
                axis_x.set_ylabel("Longitud de onda (nm)")
                axis_y.axis("off")
                if preview is None:
                    axis_x.text(
                        0.5, 0.5, f"{label}: B-scan no disponible en este archivo",
                        ha="center", va="center", transform=axis_x.transAxes,
                    )
                else:
                    positions, wavelengths, values = preview
                    axis_x.pcolormesh(positions, wavelengths, values.T, shading="auto", cmap="viridis")
                continue
            if source.depth_mm is None:
                try:
                    depth_mm, axial = self._selected_axial_profile(source, label)
                except (IndexError, ValueError, TypeError):
                    depth_mm, axial = None, None
                if depth_mm is not None:
                    axis_x.set_title(f"{label}: Perfil axial")
                    axis_x.set_xlabel("Profundidad física (mm)")
                    axis_x.set_ylabel("Amplitud del perfil")
                    axis_x.plot(depth_mm, axial, color=color)
                    axis_y.axis("off")
                else:
                    axis_x.set_title(f"{label}: corte {orientation}")
                    axis_x.text(
                        0.5, 0.5, f"{label}: el archivo no contiene picos/profundidad ni perfil axial disponible",
                        ha="center", va="center", transform=axis_x.transAxes,
                    )
                continue
            if preview is None:
                axis_x.set_title(f"{label}: corte {orientation}")
                axis_x.text(
                    0.5, 0.5, f"{label}: corte no disponible",
                    ha="center", va="center", transform=axis_x.transAxes,
                )
                continue
            if orientation == "XY":
                axis_x.set_title(f"{label}: Corte sobre X")
                axis_x.set_xlabel("X (mm)")
                axis_x.set_ylabel(f"OPD ({unit})")
                axis_y.set_title(f"{label}: Corte sobre Y")
                axis_y.set_xlabel("Y (mm)")
                axis_y.set_ylabel(f"OPD ({unit})")
                axis_x.plot(preview["x_position"], preview["x_depth_mm"] * scale, color=color)
                if preview["y_position"] is not None:
                    axis_y.plot(preview["y_position"], preview["y_depth_mm"] * scale, color=color)
            else:
                finite = np.isfinite(preview.horizontal) & np.isfinite(preview.vertical) & np.isfinite(preview.values)
                axis_x.set_title(f"{label}: corte {orientation} @ {preview.coordinate_mm:.6g} mm")
                axis_x.set_xlabel(f"{preview.horizontal_axis} (mm)")
                axis_x.set_ylabel(f"{preview.vertical_axis} (mm)")
                axis_y.axis("off")
                if finite.any():
                    axis_x.scatter(
                        preview.horizontal[finite],
                        preview.vertical[finite],
                        c=preview.values[finite],
                        cmap="viridis",
                        s=28,
                        edgecolors="none",
                    )
        volume_mode = any(item is not None and item[0] != "XY" for item in previews)
        hspace = 0.72 if volume_mode else 0.36
        canvas.figure.subplots_adjust(left=0.08, right=0.95, bottom=0.14, top=0.88, hspace=hspace, wspace=0.28)
        canvas.canvas.draw_idle()

    def _selected_cuts(self, source, label: str):
        x, y, _z, depth_mm, _amplitude, layout = self._level_arrays(source, label)
        spin_measurement = self.spin_measurement_a if label == "A" else self.spin_measurement_b
        spin_window = self.spin_window_a if label == "A" else self.spin_window_b
        spin_x = self.spin_x_a if label == "A" else self.spin_x_b
        spin_y = self.spin_y_a if label == "A" else self.spin_y_b
        values = depth_mm[:, spin_measurement.value(), spin_window.value()]

        def profile(independent, fixed, target):
            finite = np.isfinite(independent) & np.isfinite(fixed) & np.isfinite(values)
            if not finite.any():
                return np.array([]), np.array([])
            distances = np.abs(fixed[finite] - target)
            fixed_value = fixed[finite][int(np.argmin(distances))]
            selected = finite & (np.abs(fixed - fixed_value) <= layout.tolerance_mm)
            order = np.argsort(independent[selected], kind="stable")
            return independent[selected][order], values[selected][order]

        x_position, x_depth_mm = profile(x, y, self._display_coordinate(source, "Y", spin_y.value()))
        y_position, y_depth_mm = profile(y, x, self._display_coordinate(source, "X", spin_x.value()))
        return {
            "x_position": x_position,
            "x_depth_mm": x_depth_mm,
            "y_position": y_position if y_position.size else None,
            "y_depth_mm": y_depth_mm if y_depth_mm.size else None,
        }

    def _selected_bscan(self, source, label: str):
        base = source.dataset if isinstance(source, TransformedView) else source
        transformed = source.transformed_data.apply_mask() if isinstance(source, TransformedView) else None
        spectra = transformed.spectra if transformed is not None else base.spectra
        wavelengths = base.wavelengths
        if spectra is None or wavelengths is None:
            raise ValueError("No hay espectros y longitudes de onda en el payload")
        if spectra.ndim not in (2, 3) or spectra.shape[-1] != len(wavelengths):
            raise ValueError("Shape espectral incompatible con wavelengths_nm")
        layout = (
            VolumeLayout.from_coordinates(
                transformed.X, transformed.Y, transformed.Z,
                tolerance_mm=base.coordinate_tolerance_mm,
                tolerance_x_mm=base.position_tolerance_x_mm,
                tolerance_y_mm=base.position_tolerance_y_mm,
                tolerance_z_mm=base.position_tolerance_z_mm,
            ) if transformed is not None else base.volume_layout
        )
        state = self.display_state.source(label)
        if state.level_index >= layout.n_levels or state.level_index in state.excluded_levels:
            raise ValueError("Nivel no disponible para B-scan")
        indices = layout.levels[state.level_index].point_indices
        if transformed is not None:
            x = transformed.X[indices]
            y = transformed.Y[indices]
        else:
            x = base.X[indices]
            y = base.Y[indices]
        spectra = spectra[indices]
        measurement = (self.spin_measurement_a if label == "A" else self.spin_measurement_b).value()
        if spectra.ndim == 3:
            if measurement >= spectra.shape[1]:
                raise ValueError("Medición fuera de rango para espectros")
            spectra = spectra[:, measurement, :]
        finite = np.isfinite(x) & np.isfinite(y)
        if not finite.any():
            raise ValueError("No hay posiciones finitas para B-scan")
        target_y = self._display_coordinate(
            source,
            "Y",
            (self.spin_y_a if label == "A" else self.spin_y_b).value(),
        )
        nearest_y = y[finite][int(np.argmin(np.abs(y[finite] - target_y)))]
        selected = finite & (np.abs(y - nearest_y) <= layout.tolerance_mm)
        order = np.argsort(x[selected], kind="stable")
        return x[selected][order], np.asarray(wavelengths, dtype=float), spectra[selected][order]

    def _selected_axial_profile(self, source, label: str):
        if isinstance(source, TransformedView):
            data = source.transformed_data.apply_mask()
            x, y = data.X, data.Y
            profiles = data.profiles
            axes = data.profile_depth_axes_m
        else:
            x, y = source.X, source.Y
            profiles = source.profiles
            axes = source.profile_depth_axes_m
        if not profiles:
            raise ValueError("No hay perfiles axiales en el payload")
        spin_measurement = self.spin_measurement_a if label == "A" else self.spin_measurement_b
        spin_window = self.spin_window_a if label == "A" else self.spin_window_b
        win_id = spin_window.value()
        measurement = spin_measurement.value()
        if win_id not in profiles or not axes or win_id not in axes:
            raise ValueError("El perfil axial no tiene eje físico persistido")
        profile = np.asarray(profiles[win_id])
        depth_m = np.asarray(axes[win_id], dtype=float)
        spin_x = self.spin_x_a if label == "A" else self.spin_x_b
        spin_y = self.spin_y_a if label == "A" else self.spin_y_b
        target_x = self._display_coordinate(source, "X", spin_x.value())
        target_y = self._display_coordinate(source, "Y", spin_y.value())
        finite = np.isfinite(x) & np.isfinite(y)
        if not finite.any():
            raise ValueError("No hay posiciones finitas para seleccionar el perfil")

        if profile.ndim == 3:
            if profile.shape[0] != len(x) or measurement >= profile.shape[1]:
                raise ValueError("Shape de perfil axial incompatible")
            distances = (x[finite] - target_x) ** 2 + (y[finite] - target_y) ** 2
            point = np.flatnonzero(finite)[int(np.argmin(distances))]
            values = profile[point, measurement, :]
        elif profile.ndim == 2:
            if profile.shape[0] == len(x):
                distances = (x[finite] - target_x) ** 2 + (y[finite] - target_y) ** 2
                point = np.flatnonzero(finite)[int(np.argmin(distances))]
                values = profile[point, :]
            elif measurement < profile.shape[0]:
                values = profile[measurement, :]
            else:
                raise ValueError("Shape de perfil axial incompatible")
        elif profile.ndim == 1:
            values = profile
        else:
            raise ValueError("Shape de perfil axial incompatible")
        if len(values) != len(depth_m):
            raise ValueError("El eje axial no coincide con el perfil")
        return depth_m * 1000.0, np.abs(values) if np.iscomplexobj(values) else values

    def _selected_volume_slice(self, source, label: str, orientation: str):
        if isinstance(source, TransformedView):
            td = source.transformed_data.apply_mask()
            x, y, z = td.X, td.Y, td.Z
            depth_mm = td.depth_mm
            tolerance = source.dataset.coordinate_tolerance_mm
        else:
            x, y, z = source.X, source.Y, source.Z
            depth_mm = source.depth_mm
            tolerance = source.coordinate_tolerance_mm
        if depth_mm is None:
            raise ValueError("No hay datos de OPD")
        spin_measurement = self.spin_measurement_a if label == "A" else self.spin_measurement_b
        spin_window = self.spin_window_a if label == "A" else self.spin_window_b
        coordinate = getattr(self, f"volume_coordinate_{label.lower()}").value()
        if orientation == "XZ":
            coordinate = self._display_coordinate(source, "Y", coordinate)
        elif orientation == "YZ":
            coordinate = self._display_coordinate(source, "X", coordinate)
        values = depth_mm[:, spin_measurement.value(), spin_window.value()]
        return select_volume_slice(
            x,
            y,
            z,
            values,
            orientation,
            coordinate_mm=coordinate,
            tolerance_mm=tolerance,
        )

    def _level_arrays(self, source, label: str):
        if isinstance(source, TransformedView):
            td = source.transformed_data.apply_mask()
            tolerance = source.dataset.coordinate_tolerance_mm
            x, y, z = td.X, td.Y, td.Z
            depth_mm, amplitude = td.depth_mm, td.amplitude
        else:
            tolerance = source.coordinate_tolerance_mm
            x, y, z = source.X, source.Y, source.Z
            depth_mm, amplitude = source.depth_mm, source.amplitude
        if depth_mm is None:
            raise ValueError("No hay datos de OPD")
        layout = VolumeLayout.from_coordinates(x, y, z, tolerance_mm=tolerance)
        state = self.display_state.source(label)
        if state.level_index >= layout.n_levels:
            raise IndexError(f"Nivel fuera de rango: {state.level_index}")
        if state.level_index in state.excluded_levels:
            raise ValueError(f"El nivel {state.level_index} está excluido")
        indices = layout.levels[state.level_index].point_indices
        return x[indices], y[indices], z[indices], depth_mm[indices], (
            amplitude[indices] if amplitude is not None else None
        ), layout

    def _surface_assembly_patch_arrays(self, source, kind: str, label: str):
        """Obtener cada parche por separado para no conectar regiones lejanas."""
        metadata = {}
        if isinstance(source, TransformedView):
            metadata.update(source.dataset.metadata)
            data = source.transformed_data
        else:
            metadata.update(getattr(source, "metadata", {}))
            data = source
        metadata.update(getattr(data, "metadata", {}))
        parameters = _surface_assembly_parameters(metadata)
        if parameters is None:
            return None

        depth_mm = getattr(data, "depth_mm", None)
        if depth_mm is None:
            return []
        x = np.asarray(data.X, dtype=float)
        y = np.asarray(data.Y, dtype=float)
        z = np.asarray(data.Z, dtype=float)
        amplitude = getattr(data, "amplitude", None)
        values = depth_mm[:, (self.spin_measurement_a if label == "A" else self.spin_measurement_b).value(), (self.spin_window_a if label == "A" else self.spin_window_b).value()]
        if kind == "amplitude":
            if amplitude is None:
                return []
            values = amplitude[:, (self.spin_measurement_a if label == "A" else self.spin_measurement_b).value(), (self.spin_window_a if label == "A" else self.spin_window_b).value()]

        tolerance = max(float(getattr(data, "coordinate_tolerance_mm", 1e-9)), 1e-9)
        layout = VolumeLayout.from_coordinates(x, y, z, tolerance_mm=tolerance)
        state = self.display_state.source(label)
        if state.level_index >= layout.n_levels:
            raise IndexError(f"Nivel fuera de rango: {state.level_index}")
        if state.level_index in state.excluded_levels:
            raise ValueError(f"El nivel {state.level_index} está excluido")
        selected_z = float(layout.levels[state.level_index].z_mm)
        level_mask = np.isfinite(z) & (np.abs(z - selected_z) <= tolerance)
        if getattr(data, "mask", None) is not None:
            level_mask &= np.asarray(data.mask, dtype=bool)

        output = []
        offset = 0
        for patch in parameters.get("patches", []):
            count = max(int(patch.get("n_points", 0)), 0)
            end = min(offset + count, len(x))
            if end > offset:
                valid = level_mask[offset:end] & np.isfinite(x[offset:end]) & np.isfinite(y[offset:end])
                if np.any(valid):
                    output.append({
                        "name": patch.get("name", f"parche_{len(output) + 1}"),
                        "x": x[offset:end][valid],
                        "y": y[offset:end][valid],
                        "z": z[offset:end][valid],
                        "values": np.asarray(values[offset:end][valid], dtype=float),
                        "tolerance": tolerance,
                    })
            offset += count
        return output

    def _map_values(self, dataset, kind: str, label: str):
        x, y, _z, depth_mm, amplitude, layout = self._level_arrays(dataset, label)
        spin_measurement = self.spin_measurement_a if label == "A" else self.spin_measurement_b
        spin_window = self.spin_window_a if label == "A" else self.spin_window_b
        values = depth_mm[:, spin_measurement.value(), spin_window.value()]
        if kind == "amplitude":
            if amplitude is None:
                return None
            values = amplitude[:, spin_measurement.value(), spin_window.value()]
        if kind == "depth_mm" and isinstance(dataset, OCTDataset) and layout.n_levels == 1:
            try:
                x_grid, y_grid, legacy_grid = dataset.topography_grid(
                    spin_window.value(), spin_measurement.value()
                )
                if not (np.isfinite(x_grid).all() and np.isfinite(y_grid).all()):
                    return x_grid, y_grid, legacy_grid
            except (IndexError, ValueError):
                pass
        x_sorted = layout.x_unique
        y_sorted = layout.y_unique
        x_grid, y_grid = np.meshgrid(x_sorted, y_sorted)
        grid = np.full((y_sorted.size, x_sorted.size), np.nan, dtype=float)
        for x_value, y_value, value in zip(x, y, values):
            if not np.isfinite(x_value) or not np.isfinite(y_value):
                continue
            xi = int(np.argmin(np.abs(x_sorted - x_value)))
            yi = int(np.argmin(np.abs(y_sorted - y_value)))
            if abs(x_sorted[xi] - x_value) <= layout.tolerance_mm and abs(y_sorted[yi] - y_value) <= layout.tolerance_mm:
                grid[yi, xi] = value
        return x_grid, y_grid, grid

    @staticmethod
    def _dataset_card(dataset: OCTDataset) -> str:
        return dataset_card_text(dataset)

    def _apply_style(self):
        checkmark_path = (PROJECT_ROOT / "assets" / "checkbox_checked.svg").as_posix()
        self.setStyleSheet("""
            QMainWindow { background: #20242a; color: #e8e8e8; }
            QWidget#appHeader { background: #20242a; border-bottom: 1px solid #566371; }
            QLabel#headerTitle { color: #f2f4f7; font-size: 12pt; font-weight: bold; }
            QLabel#headerStatus { color: #b9c7d6; padding: 2px 4px; }
            QDialog { background: #252b34; color: #f2f4f7; }
            QDialog#modalDialog { background: #20242a; color: #f2f4f7; }
            QDialog#modalDialog QLabel#dialogIntro { background: #252b34; color: #b9c7d6; border: 1px solid #566371; border-radius: 4px; padding: 9px 10px; }
            QDialog#modalDialog QTableWidget { background: #292e35; color: #f0f0f0; border: 1px solid #566371; border-radius: 4px; gridline-color: #505862; alternate-background-color: #303842; }
            QDialog#modalDialog QHeaderView::section { background: #3b4550; color: #f0f0f0; border: 1px solid #596574; padding: 6px 7px; font-weight: bold; }
            QDialog#modalDialog QComboBox, QDialog#modalDialog QDoubleSpinBox, QDialog#modalDialog QSpinBox { min-height: 23px; }
            QDialogButtonBox#modalButtons { margin-top: 2px; }
            QDialogButtonBox#modalButtons QPushButton { min-width: 84px; padding: 5px 13px; }
            QDialogButtonBox#modalButtons QPushButton:default { background: #506b86; border-color: #8ba5bd; }
            QDialogButtonBox#modalButtons QPushButton:default:hover { background: #5e7d9b; }
            QMessageBox { background: #20242a; color: #f2f4f7; }
            QMessageBox QLabel { color: #f2f4f7; padding: 2px; }
            QMessageBox QPushButton { background: #3a4654; color: #f2f4f7; border: 1px solid #687789; border-radius: 3px; min-width: 84px; padding: 5px 13px; }
            QMessageBox QPushButton:default { background: #506b86; border-color: #8ba5bd; }
            QMessageBox QPushButton:hover { background: #4c6075; }
            QMessageBox QTextBrowser { background: #252b34; color: #f2f4f7; border: 1px solid #596574; }
            QDialog QLabel { color: #f2f4f7; }
            QWidget { color: #e8e8e8; font-family: "DejaVu Sans"; font-size: 10pt; }
            QToolBar#plotNavigationToolbar {
                background: #252b34;
                border: 1px solid #566371;
                spacing: 2px;
                padding: 2px;
            }
            QToolBar#plotNavigationToolbar QToolButton {
                background: #303945;
                color: #f2f4f7;
                border: 1px solid #566371;
                border-radius: 3px;
                padding: 2px;
            }
            QToolBar#plotNavigationToolbar QToolButton:hover {
                background: #46617a;
            }
            QWidget#sidebar { background: #20242a; }
            QScrollArea#sidebarScroll { background: #20242a; border: none; }
            QScrollArea#sidebarScroll > QWidget > QWidget { background: #20242a; }
            QGroupBox {
                background: #252b34;
                border: 1px solid #566371;
                border-radius: 4px;
                margin-top: 9px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 7px;
                padding: 0 5px;
                color: #e6edf5;
                font-weight: bold;
            }
            QGroupBox#sampleCard {
                background: #252b34;
                border-color: #718093;
                margin-top: 11px;
                padding-top: 9px;
            }
            QGroupBox#sampleCard::title {
                color: #ffffff;
                font-size: 11pt;
                font-weight: bold;
                left: 9px;
                padding: 0 6px;
            }
            QGroupBox#filtersGroup {
                background: #2a323c;
                border-color: #647486;
            }
            QGroupBox#geometryGroup {
                background: #2a323c;
                border-color: #647486;
            }
            QWidget#filtersGroup, QWidget#geometryGroup, QWidget#selectionControls,
            QWidget#pipelineRowA, QWidget#pipelineRowB {
                background: transparent;
            }
            QLabel#pipelineSlot {
                color: #ffffff;
                font-weight: bold;
                padding: 4px 6px;
            }
            QLabel#stageHeading {
                color: #aebdcb;
                font-size: 9pt;
                font-weight: 700;
                letter-spacing: 0.5px;
                padding-top: 4px;
            }
            QLabel#geometrySubheading {
                color: #aebdcb;
                font-weight: 700;
                padding-top: 2px;
            }
            QWidget#filterSubsection {
                background: transparent;
                border-bottom: 1px solid #46515e;
            }
            QLabel#subsectionTitle {
                color: #cbd7e4;
                font-weight: bold;
                padding: 2px 0;
            }
            QLabel#sampleDataset {
                color: #b9c7d6;
                padding: 2px 0 4px 0;
            }
            QPushButton {
                background: #3a4654;
                color: #f2f4f7;
                border: 1px solid #687789;
                border-radius: 3px;
                padding: 5px 9px;
                min-height: 22px;
            }
            QPushButton:hover { background: #4c6075; }
            QPushButton:disabled { background: #2b3038; color: #8b949e; border-color: #444b55; }
            QComboBox { background: #f5f6f8; color: #20242a; border: 1px solid #718093; border-radius: 3px; padding: 3px 7px; min-height: 21px; }
            QComboBox:disabled { background: #dfe3e8; color: #66717d; }
            QComboBox QAbstractItemView { background: #f5f6f8; color: #20242a; selection-background-color: #2f80d0; selection-color: #ffffff; border: 1px solid #718093; }
            QSpinBox, QDoubleSpinBox { background: #303842; color: #f2f4f7; border: 1px solid #718093; border-radius: 3px; padding: 3px; min-height: 21px; }
            QCheckBox { spacing: 6px; }
            QCheckBox::indicator { width: 16px; height: 16px; border-radius: 2px; }
            QCheckBox::indicator:unchecked { background: #000000; border: 2px solid #ffffff; }
            QCheckBox::indicator:checked { background: #000000; border: 2px solid #ffffff; image: url("__CHECKMARK_PATH__"); }
            QCheckBox::indicator:disabled { background: #000000; border: 2px solid #8b949e; }
            QTabWidget::pane { border: 1px solid #59616d; background: #f7f7f7; }
            QTabBar#sampleModeBar { background: transparent; }
            QTabBar#sampleModeBar::tab { background: #303842; color: #dce3eb; padding: 6px 14px; border: 1px solid #59616d; margin-right: 3px; }
            QTabBar#sampleModeBar::tab:selected { background: #506b86; color: #ffffff; }
            QTabBar#sampleModeBar::tab:disabled { background: #252b34; color: #697582; border-color: #3d4650; }
            QStackedWidget#sampleStages { background: transparent; }
            QTabBar::tab { background: #303842; color: #dce3eb; padding: 7px 15px; border: 1px solid #59616d; border-bottom: none; }
            QTabBar::tab:selected { background: #506b86; color: #ffffff; }
            QTableWidget { background: #292e35; color: #f0f0f0; gridline-color: #505862; }
            QHeaderView::section { background: #3b4550; color: #f0f0f0; padding: 5px; }
        """.replace("__CHECKMARK_PATH__", checkmark_path))


def shared_display_scale(value_groups) -> tuple[float, str]:
    """Elegir una única escala de display para todas las fuentes A/B."""
    groups = [np.asarray(values, dtype=float).ravel() for values in value_groups]
    finite = np.concatenate([group[np.isfinite(group)] for group in groups if np.isfinite(group).any()]) if groups else np.array([])
    return display_scale(finite)


def shared_color_limits(value_groups) -> tuple[float, float]:
    """Obtener límites cromáticos comunes para todas las fuentes."""
    groups = [np.asarray(values, dtype=float).ravel() for values in value_groups]
    finite_groups = [group[np.isfinite(group)] for group in groups if np.isfinite(group).any()]
    if not finite_groups:
        return 0.0, 1.0
    finite = np.concatenate(finite_groups)
    minimum = float(np.min(finite))
    maximum = float(np.max(finite))
    if minimum == maximum:
        padding = max(abs(minimum) * 0.05, 1.0)
        return minimum - padding, maximum + padding
    return minimum, maximum


def dataset_card_text(dataset: OCTDataset) -> str:
    """Texto de identificación; la calidad y adquisición viven en Metadata."""
    return f"<b>{dataset.sample_name or dataset.filename}</b><br>{dataset.filename}"


def display_scale(values) -> tuple[float, str]:
    """Elegir una unidad legible; los valores internos permanecen en mm."""
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size and float(np.max(np.abs(finite))) < 1.0:
        return 1000.0, "µm"
    return 1.0, "mm"


def _display(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, tuple):
        return "[" + ", ".join(f"{float(v):.6g}" for v in value) + "]"
    return str(value)


def configure_numeric_locale():
    """Usar punto decimal y omitir separadores de miles en la interfaz Qt."""
    numeric_locale = QLocale(QLocale.English, QLocale.UnitedStates)
    numeric_locale.setNumberOptions(QLocale.OmitGroupSeparator)
    QLocale.setDefault(numeric_locale)

