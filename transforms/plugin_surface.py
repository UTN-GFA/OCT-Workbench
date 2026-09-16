"""Fachada simple y segura para plugins escritos por el laboratorio."""

from __future__ import annotations

import copy

import numpy as np

from transforms.base import TransformData


class PluginSurfaceError(ValueError):
    """Error de uso de la fachada de superficie."""


class Superficie:
    """Vista editable de una superficie sin exponer su complejidad interna.

    La instancia contiene siempre una copia de trabajo. Las propiedades de
    lectura devuelven copias de los arrays y los helpers devuelven otra
    ``Superficie``; por lo tanto un plugin no puede modificar la entrada del
    pipeline por accidente.
    """

    def __init__(self, data: TransformData) -> None:
        if not isinstance(data, TransformData):
            raise TypeError("Superficie necesita un TransformData")
        self._data = data.copy()

    @classmethod
    def from_data(cls, data: TransformData) -> "Superficie":
        return cls(data)

    def to_data(self) -> TransformData:
        """Devolver una copia interna apta para el pipeline."""
        return self._data.copy()

    def copy(self) -> "Superficie":
        return Superficie(self._data)

    @property
    def x(self) -> np.ndarray:
        return self._data.X.copy()

    @x.setter
    def x(self, value) -> None:
        self._set_coordinate("X", value)

    @property
    def y(self) -> np.ndarray:
        return self._data.Y.copy()

    @y.setter
    def y(self, value) -> None:
        self._set_coordinate("Y", value)

    @property
    def coordenada_z(self) -> np.ndarray:
        return self._data.Z.copy()

    @coordenada_z.setter
    def coordenada_z(self, value) -> None:
        self._set_coordinate("Z", value)

    @property
    def z(self) -> np.ndarray:
        if self._data.depth_mm is None:
            raise PluginSurfaceError("la superficie no contiene datos OPD")
        return self._data.depth_mm.copy()

    @property
    def depth_mm(self) -> np.ndarray | None:
        """Profundidad normalizada de la superficie en milímetros."""
        return self._data.depth_mm.copy() if self._data.depth_mm is not None else None

    @depth_mm.setter
    def depth_mm(self, value) -> None:
        self._set_depth_mm(value)

    @property
    def X(self) -> np.ndarray:
        return self.x

    @X.setter
    def X(self, value) -> None:
        self.x = value

    @property
    def Y(self) -> np.ndarray:
        return self.y

    @Y.setter
    def Y(self, value) -> None:
        self.y = value

    @property
    def Z(self) -> np.ndarray:
        return self.coordenada_z

    @Z.setter
    def Z(self, value) -> None:
        self.coordenada_z = value

    @property
    def amplitude(self) -> np.ndarray | None:
        return self._data.amplitude.copy() if self._data.amplitude is not None else None

    @property
    def mask(self) -> np.ndarray | None:
        return self._data.mask.copy() if self._data.mask is not None else None

    @property
    def units(self) -> dict:
        return copy.deepcopy(self._data.units)

    @property
    def coordinate_tolerance_mm(self) -> float:
        return float(self._data.coordinate_tolerance_mm)

    @property
    def metadata(self) -> dict:
        return copy.deepcopy(self._data.metadata)

    @property
    def provenance(self) -> list:
        return copy.deepcopy(self._data.provenance)

    def con_x(self, new_x) -> "Superficie":
        return self._with_coordinate("X", new_x)

    def con_y(self, new_y) -> "Superficie":
        return self._with_coordinate("Y", new_y)

    def con_coordenada_z(self, new_z) -> "Superficie":
        return self._with_coordinate("Z", new_z)

    def desplazar(self, eje: str, valor: float) -> "Superficie":
        """Desplazar un eje físico u OPD sin cambiar shape ni metadata."""
        eje = str(eje).upper()
        valor = float(valor)
        if eje == "DEPTH":
            return self.con_z(self.z + valor)
        if eje not in {"X", "Y", "Z"}:
            raise PluginSurfaceError("desplazar admite X, Y, Z u OPD")
        return self._with_coordinate(eje, getattr(self._data, eje) + valor)

    def centrar_origen(self) -> "Superficie":
        """Centrar X/Y en cero usando sólo coordenadas finitas."""
        result = self
        for eje in ("X", "Y"):
            values = getattr(result._data, eje)
            finite = values[np.isfinite(values)]
            if finite.size:
                center = (finite.min() + finite.max()) / 2.0
                result = result._with_coordinate(eje, values - center)
        return result

    def con_z(self, new_z) -> "Superficie":
        """Crear una superficie con nuevos valores OPD y misma estructura."""
        if self._data.depth_mm is None:
            raise PluginSurfaceError("no se puede reemplazar z sin datos OPD")
        array = np.asarray(new_z)
        if array.shape != self._data.depth_mm.shape:
            raise PluginSurfaceError(
                f"z tiene shape {array.shape}; se esperaba {self._data.depth_mm.shape}"
            )
        result = self._data.copy()
        result.depth_mm = np.array(array, copy=True)
        return Superficie(result)

    def con_amplitud(self, new_amplitude) -> "Superficie":
        if self._data.amplitude is None:
            raise PluginSurfaceError("no se puede reemplazar amplitud sin datos")
        array = np.asarray(new_amplitude)
        if array.shape != self._data.amplitude.shape:
            raise PluginSurfaceError(
                f"amplitud tiene shape {array.shape}; se esperaba {self._data.amplitude.shape}"
            )
        result = self._data.copy()
        result.amplitude = np.array(array, copy=True)
        return Superficie(result)

    def con_z_y_amplitud(self, new_z, new_amplitude) -> "Superficie":
        """Reemplazar OPD y amplitud juntos, con shapes idénticos y copia profunda."""
        if self._data.depth_mm is None:
            raise PluginSurfaceError("no se puede reemplazar z sin datos OPD")
        if self._data.amplitude is None:
            raise PluginSurfaceError("no se puede reemplazar amplitud sin datos")
        z_array = np.asarray(new_z)
        amplitude_array = np.asarray(new_amplitude)
        if z_array.shape != self._data.depth_mm.shape:
            raise PluginSurfaceError(
                f"z tiene shape {z_array.shape}; se esperaba {self._data.depth_mm.shape}"
            )
        if amplitude_array.shape != self._data.amplitude.shape:
            raise PluginSurfaceError(
                f"amplitud tiene shape {amplitude_array.shape}; se esperaba {self._data.amplitude.shape}"
            )
        result = self._data.copy()
        result.depth_mm = np.array(z_array, copy=True)
        result.amplitude = np.array(amplitude_array, copy=True)
        return Superficie(result)

    def espejar(self, eje: str) -> "Superficie":
        eje = str(eje).upper()
        if eje not in {"X", "Y"}:
            raise PluginSurfaceError("espejar sólo admite el eje X o Y")
        result = self._data.copy()
        values = result.X if eje == "X" else result.Y
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            return Superficie(result)
        mirrored = finite.min() + finite.max() - values
        if eje == "X":
            result.X = mirrored
        else:
            result.Y = mirrored
        return Superficie(result)

    def reordenar_eje(self, eje: str, sentido: int = 1) -> "Superficie":
        """Cambiar el sentido físico de un eje sin remuestrear datos."""
        eje = str(eje).upper()
        if eje not in {"X", "Y", "Z"}:
            raise PluginSurfaceError("reordenar_eje admite X, Y o Z")
        if int(sentido) not in {-1, 1}:
            raise PluginSurfaceError("sentido debe ser 1 o -1")
        result = self._data.copy()
        if int(sentido) == -1:
            setattr(result, eje, -getattr(result, eje))
        return Superficie(result)

    def rotar_90(self, sentido: int = 1) -> "Superficie":
        """Rotar X/Y 90 grados alrededor del centro físico, sin interpolar."""
        sentido = int(sentido)
        if sentido not in {-1, 1}:
            raise PluginSurfaceError("sentido debe ser 1 o -1")
        result = self._data.copy()
        x, y = result.X, result.Y
        finite = np.isfinite(x) & np.isfinite(y)
        if not np.any(finite):
            return Superficie(result)
        center_x = (x[finite].min() + x[finite].max()) / 2.0
        center_y = (y[finite].min() + y[finite].max()) / 2.0
        dx, dy = x - center_x, y - center_y
        if sentido == 1:
            result.X = center_x - dy
            result.Y = center_y + dx
        else:
            result.X = center_x + dy
            result.Y = center_y - dx
        return Superficie(result)

    def conservar_puntos(self, mask) -> "Superficie":
        """Conservar sólo los puntos indicados por una máscara booleana."""
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != self._data.X.shape:
            raise PluginSurfaceError(
                f"la máscara tiene shape {mask.shape}; se esperaba {self._data.X.shape}"
            )
        result = self._data.copy()
        result.X = result.X[mask]
        result.Y = result.Y[mask]
        result.Z = result.Z[mask]
        if result.depth_mm is not None:
            result.depth_mm = result.depth_mm[mask]
        if result.amplitude is not None:
            result.amplitude = result.amplitude[mask]
        if result.profiles is not None:
            result.profiles = {key: values[mask] for key, values in result.profiles.items()}
        result.mask = None
        return Superficie(result)

    def _with_coordinate(self, axis: str, value) -> "Superficie":
        array = np.asarray(value)
        current = getattr(self._data, axis)
        if array.shape != current.shape:
            raise PluginSurfaceError(
                f"coordenada {axis} tiene shape {array.shape}; se esperaba {current.shape}"
            )
        result = self._data.copy()
        setattr(result, axis, np.array(array, copy=True))
        return Superficie(result)

    def _set_coordinate(self, axis: str, value) -> None:
        array = np.asarray(value)
        current = getattr(self._data, axis)
        if array.shape != current.shape:
            raise PluginSurfaceError(
                f"coordenada {axis} tiene shape {array.shape}; se esperaba {current.shape}"
            )
        setattr(self._data, axis, np.array(array, copy=True))

    def _set_depth_mm(self, value) -> None:
        if self._data.depth_mm is None:
            raise PluginSurfaceError("no se puede reemplazar z sin datos OPD")
        array = np.asarray(value)
        if array.shape != self._data.depth_mm.shape:
            raise PluginSurfaceError(
                f"OPD tiene shape {array.shape}; se esperaba {self._data.depth_mm.shape}"
            )
        self._data.depth_mm = np.array(array, copy=True)
