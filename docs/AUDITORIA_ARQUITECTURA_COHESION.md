# Auditoría de arquitectura y cohesión

**Proyecto:** `OCT_Workbench`  
**Fecha de auditoría:** 2026-08-10  
**Alcance:** código activo del Workbench, excluyendo `.venv/`, `.hermes/`, caches,
`test_data/` y `/opt/data/workspace/OCT_Static_Software`.  
**Tipo:** revisión estática y probes ejecutables, sin refactorización.

## 1. Veredicto ejecutivo

El software **no presenta un spaghetti sin estructura**: los módulos principales tienen
responsabilidades reconocibles, no se detectaron ciclos de importación entre los 98
módulos Python auditados y la suite funcional vigente permanece verde.

Sí existe **deuda de cohesión y acoplamiento suficiente para justificar una
refactorización por bloques** antes de seguir agregando funcionalidades:

1. `oct_workbench_gui.py` concentra la composición de la UI, el estado de sesión,
   operaciones científicas, exportación y renderizado.
2. El paquete `model` depende de `work_io`, `transforms` y `extract`, por lo que el
   modelo no funciona como núcleo independiente.
3. Varios módulos importan helpers privados desde `model.dataset`, creando una fuente
   de utilidades espaciales mal ubicada.
4. Loader y exporter mezclan detección de formato, normalización de schema,
   adaptación de fuentes, validación y escritura.
5. El sistema de plugins declara un contrato genérico, pero contiene ramas especiales
   codificadas por `plugin_id`.

**Conclusión:** el código es mantenible con una refactorización incremental; no
recomiendo reescribirlo ni mover funciones indiscriminadamente. El primer objetivo
debe ser separar contratos y estado, no cambiar algoritmos científicos.

## 2. Evidencia y método

Se ejecutaron:

- Inventario AST de 98 archivos Python y 15.556 líneas.
- Grafo de imports locales y búsqueda de componentes fuertemente conectados.
- Detección de funciones/clases grandes y complejidad estructural aproximada.
- Revisión de imports entre capas y de imports privados.
- `compileall` de `compare export extract gui model transforms work_io` y
  `oct_workbench_gui.py`: **OK**.
- Regresión de exportación con `pathlib.Path`: corregida y verificada con prueba dirigida.
- La suite de regresión vigente está documentada y verificada aparte como
  `219 passed` con `QT_QPA_PLATFORM=offscreen`.

Resultado del grafo:

```text
MODULES=98
CYCLES=none
```

La ausencia de ciclos no elimina la inversión de responsabilidades: sólo indica que
la dependencia cruzada todavía no forma un bucle de importación directo.

## 3. Hallazgos

### A1 — `MainWindow` es un coordinador monolítico — severidad alta

**Evidencia:** `oct_workbench_gui.py:530-3264`.

- `MainWindow` tiene 91 métodos.
- El archivo completo tiene 3.320 líneas.
- El constructor crea UI, descubre plugins y configura el estado de sesión.
- La misma clase mantiene `dataset_a`, `dataset_b`, `view_a`, `view_b`,
  `derived_objects` y `display_state`.
- También ejecuta extracción, comparación, ensamblado de niveles, ensamblado de
  superficies, filtros, máscaras, exportación y todos los renderizadores.

Ejemplos de funciones grandes dentro de la ventana:

| Función | Líneas | Complejidad aproximada | Responsabilidad dominante |
|---|---:|---:|---|
| `_draw_maps` | 107 | 28 | renderizado, grilla y selección |
| `_draw_cuts` | 110 | 26 | cortes, datos y presentación |
| `_draw_levels` | 84 | 23 | niveles y representación |
| `_create_surface_assembly` | 68 | 17 | diálogo, dominio, warnings y persistencia |
| `_apply_opd_mask` | 59 | 17 | controles, transformación y estado |
| `_open_file` | 46 | 5 | diálogo, carga, estado y errores |

**Por qué es deuda:** cualquier cambio científico puede requerir tocar la ventana;
los tests de dominio no protegen completamente el comportamiento de UI y las
funciones no se pueden reutilizar sin instanciar el `QMainWindow`.

**Refactor mínimo recomendado:**

1. Crear un `WorkbenchSession`/`WorkbenchState` tipado para A/B, views, selección,
   coordinación y derivados.
2. Extraer un `gui/renderers.py` para mapas, niveles, cortes, histograma y 3D.
3. Extraer un `gui/commands.py` o `application/operations.py` para cargar,
   transformar, extraer, ensamblar y exportar.
4. Dejar `MainWindow` como composición de widgets, señales y delegación.

No conviene empezar separando cada función en archivos individuales: eso cambiaría
spaghetti vertical por dispersión horizontal.

### A2 — Inversión de capas alrededor de `model` — severidad alta

El modelo de datos y los ensambladores conocen infraestructura o contratos de capas
superiores:

- `model/dataset.py:335-340`: `OCTDataset.from_file()` importa y ejecuta
  `work_io.loader.load()`.
- `model/level_assembly.py:10`: importa `TransformData` desde `transforms.base`.
- `model/level_assembly.py:182-213`: importa `DerivedObject`, `ExtractionType` y
  `Provenance` desde `extract.derived`.
- `model/surface_assembly.py:14`: también depende de `TransformData`.
- `transforms/base.py:21`: importa helpers privados desde `model.dataset`.
- `extract/operations.py:19` y `extract/cuts.py:11`: importan helpers privados del
  modelo.
- `compare/pair.py:19-22`: combina `model`, `transforms` y `extract` para resolver
  fuentes y resultados.

**Impacto:** `model` no puede evolucionar o probarse como núcleo independiente;
subir una modificación del contrato de transformaciones puede afectar ensamblado,
comparación y extracción. El lazy import de `from_file()` evita un ciclo directo,
pero no corrige la dependencia conceptual.

**Refactor mínimo recomendado:**

- Mover los contratos compartidos (`TransformData`, provenance y resultados
  derivados) a un módulo de dominio neutral, por ejemplo `core/contracts.py` o
  `model/contracts.py`.
- Mover `from_file()` a una fachada de `work_io`, manteniendo durante una transición
  un wrapper de compatibilidad claramente marcado.
- Mantener `model` independiente de exportadores, dialogs y loaders.

### A3 — Helpers espaciales privados usados como API transversal — severidad media

`_canonical_unique()` y `_nearest_index()` viven en `model/dataset.py`, pero son
usados por:

- `transforms/base.py`
- `transforms/surface.py`
- `extract/operations.py`
- `extract/cuts.py`
- `compare/pair.py`
- además del propio dataset

**Problema:** un helper privado (`_...`) se convirtió de hecho en contrato global.
Eso oculta dónde vive la semántica de tolerancias y hace que cambios en `dataset.py`
tengan radio de impacto en casi todo el pipeline.

**Refactor mínimo recomendado:** crear `model/coordinates.py` o
`core/spatial.py` con funciones públicas y tests propios:

- `canonical_unique(values, tolerance)`
- `nearest_index(values, requested, tolerance)`
- resolución de tolerancias por eje
- agrupamiento/buckets espaciales

Después retirar progresivamente los imports privados desde `dataset.py`.

### A4 — Loader y exporter tienen demasiadas responsabilidades — severidad media-alta

**Loader:** `work_io/loader.py` tiene 559 líneas y mezcla:

- selección de formato;
- lectura NPZ;
- lectura HDF5;
- mapeo de aliases de schema;
- extracción de perfiles;
- inferencia de mediciones;
- validación de shapes y posiciones;
- derivación de duración y escalares.

`_load_npz()` mide 132 líneas con complejidad aproximada 32 y `_load_h5()` 148
líneas con complejidad aproximada 25.

**Exporter:** `export/exporter.py` mezcla adaptación de fuentes, schema persistente y
múltiples formatos. `_resolve_to_data()` mide 110 líneas con complejidad aproximada
32 y `to_csv()` 91 líneas con complejidad aproximada 22.

**Refactor mínimo recomendado:**

- `work_io/npz_reader.py` y `work_io/h5_reader.py` para lectura de formato;
- `work_io/normalization.py` para aliases, metadata y validaciones comunes;
- `export/schema6.py` para convertir una fuente a payload persistente;
- writers separados para NPZ, HDF5, CSV y PNG.

La conversión a payload debe ser única; los writers no deberían conocer
`OCTDataset`, `TransformedView` ni `DerivedObject` en detalle.

### A5 — Estado A/B duplicado y acceso dinámico por nombres — severidad media

**Evidencia:** `oct_workbench_gui.py:542-548`, `1064-1078`, `1184-1208`,
`2086-2090` y `1510-1524`.

La ventana mantiene pares de atributos y usa `getattr(self, f"..._{suffix}")` para
controles. Además conserva aliases legacy para los controles de A. El patrón reduce
código repetido hoy, pero deja varias fuentes de verdad:

- dataset base;
- view transformada;
- estado visual compartido;
- widgets por sufijo;
- lista de derivados.

**Riesgo:** una operación puede actualizar el pipeline o el widget y dejar desfasada
la otra representación. El riesgo aumenta con cada nuevo filtro, diálogo o control
A/B.

**Refactor mínimo recomendado:** un objeto `SampleSlotState` para A/B y un mapa
explícito `slot -> controls`, con métodos tipados para `source()`, `view()` y
`reset_pipeline()`. Mantener aliases visuales sólo en una capa de compatibilidad.

### A6 — Plugin genérico con comportamiento especial por ID — severidad media

**Evidencia:** `transforms/plugin_api.py:171-198`.

`PluginTransform` pretende adaptar cualquier plugin, pero su constructor contiene
ramas específicas para:

- `filter_median`;
- `mask_opd_range`;
- `offset_opd`;
- `level_plane`;
- `invert_axis`;
- `mirror`;
- `offset_geometry`.

**Problema:** el contrato parece extensible, pero parte de la semántica real está
codificada en el adaptador central. Cada nuevo plugin puede obligar a editar este
archivo, lo que es una señal de violación del principio de extensión.

**Refactor mínimo recomendado:** hacer que `PluginSpec` exponga capacidades o un
hook de inicialización/estado; la lógica específica debe vivir en el plugin o en
adaptadores registrados por tipo, no en una lista de IDs dentro del núcleo.

### A7 — `OCTDataset` mezcla dominio y presentación — severidad media-baja

**Evidencia:** `model/dataset.py:573-694`.

`OCTDataset.summary()` construye texto con formato de consola, símbolos, unidades,
secciones y datos de archivo; además consulta `os.path.getsize()` para mostrar el
tamaño. `data_inventory()` también está documentado explícitamente como útil para
la GUI.

**Impacto:** el modelo conoce cómo debe verse el resumen y la existencia física del
archivo, lo que dificulta reutilizarlo en CLI, API, tests o una GUI futura.

**Refactor mínimo recomendado:** exponer un `DatasetSummary` estructurado y dejar el
formateo (`str`, labels, colores, símbolos) en `gui/metadata.py` o un formatter de
presentación. No es prioritario frente a A1/A2.

### A8 — Contrato declarado y comportamiento real de exportación no coinciden — bug
funcional de API, severidad media

`export/exporter.py:6-7` declara aceptar `ComparisonPair`, y el módulo importa
`ComparisonPair` en la línea 27. Sin embargo, `_resolve_to_data()` sólo maneja
`DerivedObject`, `TransformedView` y `OCTDataset` (`:38-71`); para un
`ComparisonPair` lanza `TypeError`.

El mismo módulo tenía además un bug confirmado con `pathlib.Path`:

```text
AttributeError: 'PosixPath' object has no attribute 'lower'
```

Ese punto ya fue corregido mediante `os.fspath()` y cuenta con una regresión
específica. `ComparisonPair` también quedó soportado explícitamente: se exporta
su resultado A−B y, si no existe amplitud propia, se conserva la shape con
`NaN` para mantener el payload reabrible.

### A9 — Captura amplia de excepciones: parte justificada, parte opaca — severidad baja-media

- `transforms/discovery.py:33` captura `Exception` y `SystemExit` deliberadamente
  para aislar un plugin defectuoso.
- `oct_workbench_gui.py:1210`, `1571`, `1640` y `1687` captura `Exception` para
  mostrar errores al usuario.

La intención es válida, pero en la GUI se pierde contexto de diagnóstico y en el
sistema de plugins puede ocultarse un error de programación como si fuera sólo un
plugin inválido.

**Refactor mínimo recomendado:** registrar traceback con `logger.exception()` y
convertir únicamente errores esperados a mensajes de usuario. Mantener el aislamiento
por plugin, pero con error estructurado (`source`, tipo, traceback y mensaje).

## 4. Lo que no encontré

- No se detectaron ciclos de imports locales en los 98 módulos auditados.
- No hay evidencia de que todos los módulos estén mezclados indiscriminadamente:
  `compare`, `extract` y buena parte de `transforms` tienen límites funcionales
  reconocibles.
- No se recomienda mover algoritmos científicos sólo por reducir líneas; primero hay
  que extraer contratos y coordinadores.
- La suite verde no demuestra por sí sola que la arquitectura esté limpia, pero sí
  permite refactorizar por bloques con una red de regresión útil.

## 5. Orden de intervención recomendado

### Bloque 1 — contratos y utilidades compartidas

1. Crear `core/contracts.py`/`model/contracts.py` para payload transformable,
   provenance y resultado derivado.
2. Crear `core/spatial.py`/`model/coordinates.py` para tolerancias, agrupamiento y
   selección espacial.
3. Añadir tests de import boundaries y retirar imports privados.

### Bloque 2 — sesión de aplicación

1. Crear `WorkbenchSession` con slots A/B, views, pipelines y derivados.
2. Migrar handlers de carga, filtros, máscaras, extracción, comparación y ensamblado.
3. Mantener `MainWindow` como adaptador Qt y no cambiar primero la semántica visual.

### Bloque 3 — renderizado

1. Extraer renderers de mapas, niveles, cortes, histograma y 3D.
2. Pasar datos ya preparados, sin que el renderer consulte datasets globales o
   widgets.

### Bloque 4 — IO y plugins

1. Separar readers, normalización, payload Schema 6 y writers.
2. Reemplazar ramas por ID en `PluginTransform` por capacidades/hook.
3. ~~Resolver explícitamente `ComparisonPair` y `pathlib.Path` con regresiones.~~
   Resuelto en el bloque incremental actual.

## 6. Criterios de cierre de una refactorización

Cada bloque debe conservar:

- `219 passed` con `QT_QPA_PLATFORM=offscreen` como baseline vigente;
- `compileall` sin errores;
- roundtrip NPZ/HDF5 y provenance;
- preservación de máscaras, `NaN`, unidades y aliases;
- ningún ciclo de imports;
- tests de límites de importación para impedir que `model` vuelva a conocer GUI,
  loader o writer;
- evidencia separada de compatibilidad con saver externo y de aceptación con datos
  OCT/hardware reales.

**Estado final de esta auditoría:** la estructura es recuperable y no requiere
reescritura, pero A1 y A2 deben tratarse como deuda prioritaria antes de agregar
más lógica transversal. No se aplicaron cambios de código durante esta auditoría.

## 7. Addendum posterior: aceptación cross-format y probes paralelos

La revisión paralela ejecutó probes de frontera contra el saver externo. La
reclasificación posterior del flujo activo determinó que los casos con
`depth_m=None` usados en esos probes no representan el camino normal del
Workbench: `ScanController` construye arrays completos y conserva los faltantes
como `NaN` antes de llamar al saver. El saver externo queda fuera del alcance de
esta tanda.

### Probes de frontera y alcance

| Prioridad | Evidencia | Impacto |
|---|---|---|
| **Fuera de alcance** | Probes directos al saver con `depth_m=None` no representan el flujo activo: `ScanController._on_point()` crea arrays `(M, N_w)` completos con `NaN` y los pasa al saver. | No se clasifica como bug del Workbench normal; queda como contrato débil del saver externo. |
| **Pendiente externo** | Persistencia de `M` sin payloads y diferencias de creación diferida de perfiles en NPZ/HDF5. | No se modifica ni se prioriza en esta tanda. |
| **Fuera de alcance** | Reglas históricas NPZ/HDF5 sobre profundidad/OPD del saver externo. | No se usa para definir el contrato del Workbench actual. |
| **Resuelto** | `DerivedObject.to_export_dict()` emitía una representación distinta de la salida canónica. | La fachada histórica ahora delega en el payload Schema 6. Schema 6 es el único contrato vigente; no se mantiene una migración Schema 5. |
| **Resuelto** | `assess_comparison()` clasificaba como compatible una selección fuera de rango mientras `ComparisonPair` la rechazaba. | Ahora devuelve `not_comparable` para índices inválidos; índices distintos pero válidos siguen generando advertencia. |
| **Resuelto** | `LevelPlane` indexaba `win_id` antes de validarlo; `-1` seleccionaba silenciosamente la última ventana. | `LevelPlane`, `FilterMedian` y `LevelFromRegions` validan índices antes de indexar. |
| **Media** | `to_csv()` busca metadata uppercase (`SAMPLE_NAME`) mientras `_resolve_to_data()` produce `sample_name`. | CSV pierde proveniencia que sí existe en NPZ/HDF5. |
| **Media** | La GUI convierte opciones `choice` tipadas a texto en vez de conservar `userData`. | Plugins con opciones numéricas/booleanas fallan sólo desde la GUI. |
| **Media** | Un cambio de coordenada provoca dos `_redraw()` por conexiones duplicadas. | Renderizado redundante y degradación durante interacción. |
| **Media** | Coordenadas completamente `NaN` llegan a `QDoubleSpinBox` o reducciones vacías. | Dataset válido pero no utilizable puede romper controles o diálogos. |

### Riesgo de verificación

La suite actual escribe artefactos en rutas fijas de `test_data/`. La auditoría
paralela observó que la ejecución de tests reescribe 16 archivos. No existe Git ni
snapshot byte-a-byte disponible para restaurarlos automáticamente.

Esto no se clasifica como pérdida de datos confirmada, pero sí como **deuda de
reproducibilidad y aislamiento**. Los tests de writers deben migrar a `tmp_path` y
`test_data/` debe quedar reservado para fixtures inmutables.

### Prioridad revisada para el Workbench

1. Mantener documentado el contrato de entrada que el Workbench espera del
   saver: arrays completos por punto, con `NaN` sólo para mediciones sin pico.
2. Mantener congelado el árbol hasta disponer de mediciones OCT reales.
3. Al reabrir, ejecutar aceptación real NPZ/HDF5, GUI A/B, 2D, Multi-Z/3D,
   perfiles, cortes, B-scan, ensamblado, reapertura y exportación.
4. Validar hardware físico cuando esté disponible.
5. Recién después evaluar `WorkbenchSession`, el adelgazamiento de `MainWindow`
   y la separación de renderers.

Schema 6, `depth_m`/`depth_mm`, índices, comparación, exportación y bugs GUI de
impacto directo ya fueron corregidos y verificados. El saver externo permanece
deliberadamente fuera del alcance y no se agregan cambios funcionales durante
el congelamiento.

### Congelamiento y deuda diferida

Durante el congelamiento no se agregan funcionalidades, no se hacen nuevos
renombrados globales, no se inicia la extracción de `WorkbenchSession` y no se
adelgaza `MainWindow`.

Después de la aceptación real podrán retomarse, como deuda no bloqueante, la
migración de writers de tests a `tmp_path`, las opciones tipadas de plugins GUI,
los redraws duplicados, los controles ante coordenadas totalmente `NaN`, la
separación de renderers y el fijado completo de `requirements.txt`.
