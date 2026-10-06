"""Contrato de plugins simples para filtros y geometría.

Los plugins de laboratorio sólo necesitan declarar ``PLUGIN`` y definir
``aplicar(superficie, parametros)``. La complejidad de validación y del pipeline
queda en este módulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

import numpy as np

from transforms.base import Transform, TransformData
from transforms.plugin_surface import Superficie


class PluginValidationError(ValueError):
    """Error legible producido por un plugin o sus parámetros."""


@dataclass(frozen=True)
class ParameterSpec:
    id: str
    type: str = "float"
    label: str = ""
    unit: str = ""
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    options: tuple[Any, ...] = ()


@dataclass(frozen=True)
class PluginSpec:
    id: str
    kind: str
    name: str
    description: str
    apply_function: Callable[[TransformData, dict[str, Any]], Any]
    version: str = "1.0"
    parameters: tuple[ParameterSpec, ...] = ()
    source: str = ""
    cancellation_group: Optional[str] = None
    modifies_amplitude: bool = False
    integrated: bool = False
    changes_point_count: bool = False
    name_template: Optional[str] = None
    description_template: Optional[str] = None

    @classmethod
    def from_module(cls, module: Any, source: str = "") -> "PluginSpec":
        raw = getattr(module, "PLUGIN", None)
        if not isinstance(raw, Mapping):
            raise PluginValidationError("PLUGIN debe ser un diccionario")

        plugin_id = str(raw.get("id", "")).strip()
        kind = str(raw.get("tipo", raw.get("kind", ""))).strip().lower()
        name = str(raw.get("nombre", raw.get("name", ""))).strip()
        description = str(raw.get("descripcion", raw.get("description", name))).strip()
        apply_function = getattr(module, "aplicar", getattr(module, "apply", None))

        if not plugin_id:
            raise PluginValidationError("PLUGIN.id es obligatorio")
        if kind not in {"filter", "geometry"}:
            raise PluginValidationError("PLUGIN.tipo debe ser 'filter' o 'geometry'")
        if not name:
            raise PluginValidationError("PLUGIN.nombre es obligatorio")
        if not callable(apply_function):
            raise PluginValidationError("el módulo debe definir una función aplicar(superficie, parametros)")
        modifies_amplitude = raw.get("modifica_amplitud", raw.get("modifies_amplitude", False))
        if not isinstance(modifies_amplitude, bool):
            raise PluginValidationError("PLUGIN.modifica_amplitud debe ser booleano")
        integrated = raw.get("integrado", raw.get("integrated", False))
        if not isinstance(integrated, bool):
            raise PluginValidationError("PLUGIN.integrado debe ser booleano")
        changes_point_count = raw.get("cambia_numero_puntos", raw.get("changes_point_count", False))
        if not isinstance(changes_point_count, bool):
            raise PluginValidationError("PLUGIN.cambia_numero_puntos debe ser booleano")

        parameters = tuple(
            _parameter_from_dict(item)
            for item in raw.get("parametros", raw.get("parameters", ()))
        )
        ids = [parameter.id for parameter in parameters]
        if len(ids) != len(set(ids)):
            raise PluginValidationError("los parámetros no pueden repetir id")

        return cls(
            id=plugin_id,
            kind=kind,
            name=name,
            description=description,
            apply_function=apply_function,
            version=str(raw.get("version", "1.0")),
            parameters=parameters,
            source=source,
            cancellation_group=raw.get("cancellation_group"),
            modifies_amplitude=modifies_amplitude,
            integrated=integrated,
            changes_point_count=changes_point_count,
            name_template=raw.get("nombre_parametrico", raw.get("name_template")),
            description_template=raw.get("descripcion_parametrica", raw.get("description_template")),
        )


@dataclass(frozen=True)
class PluginError:
    source: str
    message: str


def _parameter_from_dict(raw: Mapping[str, Any]) -> ParameterSpec:
    if not isinstance(raw, Mapping):
        raise PluginValidationError("cada parámetro debe ser un diccionario")
    parameter_id = str(raw.get("id", "")).strip()
    parameter_type = str(raw.get("tipo", raw.get("type", "float"))).strip().lower()
    if not parameter_id:
        raise PluginValidationError("cada parámetro necesita id")
    if parameter_type not in {"float", "int", "bool", "str", "choice"}:
        raise PluginValidationError(f"tipo de parámetro inválido: {parameter_type}")
    options = tuple(raw.get("opciones", raw.get("options", ())))
    if parameter_type == "choice" and not options:
        raise PluginValidationError(f"el parámetro {parameter_id} necesita opciones")
    return ParameterSpec(
        id=parameter_id,
        type=parameter_type,
        label=str(raw.get("nombre", raw.get("label", parameter_id))),
        unit=str(raw.get("unidad", raw.get("unit", ""))),
        default=raw.get("default"),
        minimum=raw.get("min", raw.get("minimum")),
        maximum=raw.get("max", raw.get("maximum")),
        options=options,
    )


def _validate_parameters(spec: PluginSpec, supplied: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    supplied = dict(supplied or {})
    known = {parameter.id: parameter for parameter in spec.parameters}
    unknown = set(supplied) - set(known)
    if unknown:
        raise PluginValidationError(f"parámetros desconocidos: {', '.join(sorted(unknown))}")

    result: dict[str, Any] = {}
    for parameter in spec.parameters:
        value = supplied.get(parameter.id, parameter.default)
        if value is None:
            raise PluginValidationError(f"falta el parámetro {parameter.id}")
        if parameter.type == "float":
            try:
                value = float(value)
            except (TypeError, ValueError) as exc:
                raise PluginValidationError(f"{parameter.id} debe ser numérico") from exc
        elif parameter.type == "int":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise PluginValidationError(f"{parameter.id} debe ser entero") from exc
        elif parameter.type == "bool":
            if not isinstance(value, bool):
                raise PluginValidationError(f"{parameter.id} debe ser booleano")
        elif parameter.type == "choice" and value not in parameter.options:
            raise PluginValidationError(f"{parameter.id} debe ser una de las opciones declaradas")
        elif parameter.type == "str":
            value = str(value)

        if parameter.minimum is not None and value < parameter.minimum:
            raise PluginValidationError(f"{parameter.id} no puede ser menor que {parameter.minimum}")
        if parameter.maximum is not None and value > parameter.maximum:
            raise PluginValidationError(f"{parameter.id} no puede ser mayor que {parameter.maximum}")
        result[parameter.id] = value
    return result


class PluginTransform(Transform):
    """Adaptador seguro entre una función de laboratorio y el pipeline."""

    def __init__(self, spec: PluginSpec, parameters: Optional[Mapping[str, Any]] = None) -> None:
        self.spec = spec
        self._parameters = _validate_parameters(spec, parameters)
        if spec.id == "filter_median" and self._parameters["kernel_size"] % 2 == 0:
            self._parameters["kernel_size"] += 1
        self.offset_mm = 0.0
        if spec.id == "mask_depth_range":
            self.minimum_mm = self._parameters["minimum_mm"]
            self.maximum_mm = self._parameters["maximum_mm"]
        elif spec.id == "offset_depth":
            self._axis = "DEPTH"
            self._value = self._parameters["offset_mm"]
        elif spec.id == "filter_median":
            self._kernel = self._parameters["kernel_size"]
            self._win_id = self._parameters["win_id"]
        elif spec.id == "level_plane":
            self._win_id = self._parameters["win_id"]
            self._meas = self._parameters["measurement"]
        elif spec.id == "invert_axis":
            self._axis = self._parameters["axis"]
        elif spec.id == "mirror":
            self._axis = self._parameters["axis"]
        elif spec.id == "offset_geometry":
            self._axis = self._parameters["axis"]
            self._value = self._parameters["value_mm"]

    def apply(self, data: TransformData) -> TransformData:
        working = Superficie.from_data(data)
        if self.spec.id == "offset_minimum_to_zero" and data.depth_mm is not None:
            finite = data.depth_mm[np.isfinite(data.depth_mm)]
            self.offset_mm = 0.0 if finite.size == 0 else -float(np.min(finite))
        output = self.spec.apply_function(working, dict(self._parameters))
        if isinstance(output, Superficie):
            result = output.to_data()
        elif isinstance(output, TransformData):
            result = output.copy()
        elif isinstance(output, np.ndarray) and self.spec.kind == "filter":
            if data.depth_mm is None:
                raise PluginValidationError(f"{self.spec.id}: no hay datos OPD para filtrar")
            if output.shape != data.depth_mm.shape:
                raise PluginValidationError(
                    f"{self.spec.id}: el filtro devolvió shape {output.shape}, se esperaba {data.depth_mm.shape}"
                )
            result = working.to_data()
            result.depth_mm = np.array(output, copy=True)
        else:
            raise PluginValidationError(
                f"{self.spec.id}: aplicar debe devolver Superficie/TransformData"
                " o una matriz OPD de igual shape para filtros"
            )
        self._validate_result(data, result)
        return result

    def _validate_result(self, source: TransformData, result: TransformData) -> None:
        if self.spec.kind == "filter" and source.depth_mm is None:
            raise PluginValidationError(f"{self.spec.id}: un filtro requiere datos OPD")
        if source.depth_mm is not None and result.depth_mm is None:
            raise PluginValidationError(f"{self.spec.id}: no puede eliminar los datos OPD")
        for axis in ("X", "Y", "Z"):
            source_axis = getattr(source, axis)
            result_axis = getattr(result, axis)
            if self.spec.changes_point_count:
                if result_axis.ndim != source_axis.ndim or result_axis.ndim != 1:
                    raise PluginValidationError(f"{self.spec.id}: la coordenada {axis} perdió su forma vectorial")
            elif result_axis.shape != source_axis.shape:
                raise PluginValidationError(
                    f"{self.spec.id}: la coordenada {axis} cambió de shape "
                    f"{source_axis.shape} a {result_axis.shape}"
                )
        if self.spec.changes_point_count:
            point_count = result.n_points
            if not (len(result.X) == len(result.Y) == len(result.Z) == point_count):
                raise PluginValidationError(f"{self.spec.id}: coordenadas con distinto número de puntos")
            if result.depth_mm is not None and result.depth_mm.shape[0] != point_count:
                raise PluginValidationError(f"{self.spec.id}: OPD no acompaña el número de puntos")
        elif source.depth_mm is not None and result.depth_mm is not None and result.depth_mm.shape != source.depth_mm.shape:
            raise PluginValidationError(
                f"{self.spec.id}: OPD cambió de shape {source.depth_mm.shape} a {result.depth_mm.shape}"
            )
        if (source.amplitude is None) != (result.amplitude is None):
            raise PluginValidationError(f"{self.spec.id}: no puede crear o eliminar amplitud")
        if source.amplitude is not None and result.amplitude is not None:
            if self.spec.changes_point_count:
                if result.amplitude.ndim != source.amplitude.ndim or result.amplitude.shape[0] != result.n_points or result.amplitude.shape[1:] != source.amplitude.shape[1:]:
                    raise PluginValidationError(f"{self.spec.id}: amplitud no acompaña el número de puntos")
            elif result.amplitude.shape != source.amplitude.shape:
                raise PluginValidationError(
                    f"{self.spec.id}: amplitud cambió de shape "
                    f"{source.amplitude.shape} a {result.amplitude.shape}"
                )
            if not self.spec.modifies_amplitude and not self.spec.changes_point_count and not np.array_equal(
                source.amplitude, result.amplitude, equal_nan=True
            ):
                raise PluginValidationError(f"{self.spec.id}: cambió la amplitud sin declararlo")
        if source.mask is not None and result.mask is not None and result.mask.shape != source.mask.shape:
            raise PluginValidationError(
                f"{self.spec.id}: máscara cambió de shape {source.mask.shape} a {result.mask.shape}"
            )
        if source.coordinate_tolerance_mm != result.coordinate_tolerance_mm:
            raise PluginValidationError(f"{self.spec.id}: cambió la tolerancia de coordenadas")
        if source.units != result.units:
            raise PluginValidationError(f"{self.spec.id}: cambió las unidades")
        if source.metadata != result.metadata:
            raise PluginValidationError(f"{self.spec.id}: cambió la metadata")
        if source.provenance != result.provenance:
            raise PluginValidationError(f"{self.spec.id}: cambió la proveniencia")
        if (source.mask is None) != (result.mask is None) or (
            source.mask is not None and not np.array_equal(source.mask, result.mask)
        ):
            raise PluginValidationError(f"{self.spec.id}: cambió la máscara")
        self._validate_array_dict(source, result, "profiles")
        self._validate_array_dict(source, result, "profile_depth_axes_m")
        if (source.spectra is None) != (result.spectra is None):
            raise PluginValidationError(f"{self.spec.id}: no puede crear o eliminar espectros")
        if source.spectra is not None:
            if self.spec.changes_point_count:
                if result.spectra.ndim != source.spectra.ndim or result.spectra.shape[1:] != source.spectra.shape[1:] or result.spectra.shape[0] != result.n_points:
                    raise PluginValidationError(f"{self.spec.id}: espectros no acompañan el número de puntos")
            elif not np.array_equal(source.spectra, result.spectra, equal_nan=True):
                raise PluginValidationError(f"{self.spec.id}: cambió los espectros")

    def _validate_array_dict(self, source: TransformData, result: TransformData, field: str) -> None:
        source_values = getattr(source, field)
        result_values = getattr(result, field)
        if source_values is None and result_values is None:
            return
        if source_values is None or result_values is None or set(source_values) != set(result_values):
            raise PluginValidationError(f"{self.spec.id}: cambió {field}")
        for key in source_values:
            source_array = np.asarray(source_values[key])
            result_array = np.asarray(result_values[key])
            if self.spec.changes_point_count and field == "profiles":
                if source_array.ndim == 0 or result_array.ndim != source_array.ndim or result_array.shape[1:] != source_array.shape[1:] or result_array.shape[0] != result.n_points:
                    raise PluginValidationError(f"{self.spec.id}: cambió la estructura de {field}")
            elif not np.array_equal(source_array, result_array, equal_nan=True):
                raise PluginValidationError(f"{self.spec.id}: cambió {field}")

    @property
    def name(self) -> str:
        if self.spec.name_template:
            return self.spec.name_template.format(**self._parameters)
        return self.spec.name

    @property
    def description(self) -> str:
        if self.spec.description_template:
            return self.spec.description_template.format(**self._parameters)
        return self.spec.description

    def cancellation_key(self):
        if self.spec.cancellation_group:
            return ("plugin", self.spec.cancellation_group, tuple(sorted(self._parameters.items())))
        return None

    @property
    def parameters(self) -> dict[str, Any]:
        return dict(self._parameters)


class PluginRegistry:
    """Registro de plugins válidos y errores de carga no bloqueantes."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginSpec] = {}
        self.errors: list[PluginError] = []

    def register(self, spec: PluginSpec) -> None:
        if spec.id in self._plugins:
            raise PluginValidationError(f"id de plugin duplicado: {spec.id}")
        self._plugins[spec.id] = spec

    def add_error(self, source: str, message: str) -> None:
        self.errors.append(PluginError(source=source, message=message))

    def get(self, plugin_id: str) -> PluginSpec:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise PluginValidationError(f"plugin no encontrado: {plugin_id}") from exc

    def create(self, plugin_id: str, parameters: Optional[Mapping[str, Any]] = None) -> PluginTransform:
        return PluginTransform(self.get(plugin_id), parameters)

    def list(self, kind: Optional[str] = None, include_integrated: bool = False) -> list[PluginSpec]:
        specs = self._plugins.values()
        if kind is not None:
            specs = (spec for spec in specs if spec.kind == kind)
        if not include_integrated:
            specs = (spec for spec in specs if not spec.integrated)
        return sorted(specs, key=lambda spec: spec.id)

    def ids(self, kind: Optional[str] = None, include_integrated: bool = False) -> list[str]:
        return [spec.id for spec in self.list(kind, include_integrated=include_integrated)]

    def __len__(self) -> int:
        return len(self._plugins)
