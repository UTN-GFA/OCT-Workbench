# Auditoría completa de coherencia de variables

## 1. Alcance y estado

Auditoría report-only de `/opt/data/workspace/OCT_Workbench`. Se revisaron:

- modelo y dataclasses;
- loader y exporter NPZ/HDF5/CSV;
- transformaciones y plugins;
- extracción y objetos derivados;
- comparación A/B;
- ensamblado de niveles y superficies;
- GUI y estado de display;
- tests y documentación local.

La auditoría fue el baseline previo a la migración. Desde entonces se aplicó una primera tanda
de aliases nominales compatibles y se consolidó la salida de objetos derivados en Schema 6.
Schema 6 es el único contrato vigente; no hay mediciones Schema 5 que migrar o preservar.

## 2. Regla de coherencia

Un nombre se considera coherente cuando expresa o hereda de forma inequívoca:

1. magnitud;
2. unidad;
3. dimensión o shape;
4. índice frente a valor físico;
5. estado mutable frente a fuente inmutable;
6. origen/proveniencia;
7. capa de contrato a la que pertenece.

No se renombra por coincidencia textual aislada. Antes de cambiar un nombre hay que comprobar productores, consumidores, plugins, schemas, tests y archivos reales.

## 3. Capas que no deben mezclarse

| Capa | Convención actual | Decisión |
|---|---|---|
| Schema 6 externo | `x_mm`, `y_mm`, `z_mm`, `depth_m`, `wavelengths_nm`, `profile_depth_m_wN` | Mantener; son claves persistidas |
| Loader normalizado | `positions["X"]`, `positions["Y"]`, `positions["Z"]`, `peaks["depth_mm"]` | Contrato interno vigente; deriva exclusivamente de `depth_m` |
| Modelo/pipeline | `X`, `Y`, `Z`, `depth_mm`, `amplitude`, `spectra` | Contrato canónico; no existen aliases `opd` |
| CSV | `X_mm`, `Y_mm`, `Z_mm`, `OPD_mm`, `Amplitude_W` | Mantener como contrato tabular |
| GUI | nombres de controles y estados | Puede modernizarse sin alterar schemas |
| Plugins | API interna inglesa + aliases declarativos españoles | Normalizar internamente, conservar lectura bilingüe |

`X`, `x_mm` y `X_mm` no son automáticamente el mismo contrato: pertenecen a capas distintas aunque representen la misma coordenada física.

## 4. Mapa canónico transversal propuesto

### 4.1 Coordenadas físicas e índices

| Concepto | Canon nuevo recomendado | Nombres actuales | Diagnóstico |
|---|---|---|---|
| Coordenadas arrays del modelo | `X`, `Y`, `Z` en la primera migración | `X`, `Y`, `Z` | API histórica, documentada en mm |
| Coordenada escalar física | `x_mm`, `y_mm`, `z_mm` | `x`, `y`, `z`, `x_value`, `y_value`, `z_value`, `coordinate` | Incoherencia en funciones científicas |
| Límites físicos | `x_min_mm`, `x_max_mm`, `y_min_mm`, `y_max_mm`, `z_min_mm`, `z_max_mm` | `x_min`, `x_max`, `y_min`, `y_max`, `z_min`, `z_max` | Candidatos prioritarios |
| Valor solicitado por el usuario | `requested_x_mm`, etc. | `x_value`, `y_value`, `z_value` | Distinguir de valor adquirido |
| Valor adquirido efectivo | `actual_x_mm`, etc. | `x_actual`, `y_actual`, `z_actual` | Candidato claro |
| Coordenada devuelta en perfil | `x_position_mm`, `y_position_mm` | `x_position`, `y_position` | Candidato con alias |
| Índice de punto | `point_index` | `i`, `index`, `idx`, `point` | Sólo cambiar en APIs públicas |
| Eje lógico | `axis` o `axis_name` | `axis`, `_axis`, `horizontal_axis`, `vertical_axis` | Válido si no se confunde con coordenada |
| Índice de ventana | `window_index` | `win_id`, `window_id`, `window` | Incoherencia real de naming |
| Índice de medición | `measurement_index` | `measurement`, `m_idx` | Candidato de claridad |
| Índice de nivel | `level_index` | `level`, `level_id` | `level` solo es ambiguo |

### 4.2 OPD, profundidad y perfiles

| Concepto | Canon nuevo recomendado | Nombres actuales | Diagnóstico |
|---|---|---|---|
| Profundidad normalizada interna | `depth_mm` | `opd`, `opd_mm`, `opd_value`, `opd_prof`, `opd_win` | `depth_mm` es el único canal interno; `OPD` queda para presentación |
| Profundidad física | `physical_depth_mm` | `depth_mm` en arrays de trabajo | `physical_depth_mm` describe la semántica del eje; `depth_mm` sus valores internos |
| Entrada persistida en metros | `depth_m` | `depth_m` | Correcto; no convertir el nombre |
| Ejes de perfil en metros | `profile_depth_axes_m` | `profile_axes`, `profile_depth_m_wN` | El interno es correcto; el alias genérico debe limitarse |
| Tipo semántico | `depth_axis_kind` | `physical_depth_mm` | Único valor aceptado por el contrato actual |
| Límites de ventana normalizados | `window_depth_min_mm`, `window_depth_max_mm` | `z_min`, `z_max`, `win_z_min`, `win_depth_min_m` | Diferencia de schema/capa; internos deben explicitar mm |

### 4.3 Payloads científicos

| Concepto | Canon nuevo recomendado | Nombres actuales | Diagnóstico |
|---|---|---|---|
| Amplitud | `amplitude` | `amplitude`, `amp`, `amp_prof`, `amp_win`, `amp_value`, `amplitude_array` | Unificar abreviaturas en código científico |
| Unidad de amplitud | `amplitude_unit` | `units["amplitude"]` ausente o variable | Riesgo de contrato: no inventar `W` sin evidencia |
| Espectro crudo | `spectra` | `spectra`, `spectrum` en contextos posibles | `spectra` es la convención actual; documentar plural |
| Perfiles | `profiles` | `profiles`, `profile`, `profile_data` | Contenedor vs un perfil; distinguir en APIs |
| Picos | `peaks` | `peaks`, `peak_values` | Contenedor frente al array de valores; correcto si se explicita |
| Valores genéricos | `values` | `values`, `all_values`, `raw_values`, `source_values` | Deben calificarse por canal o eje cuando cruzan capas |
| Datos de trabajo | `TransformData` / `data` | `data`, `result_data`, `transformed_data` | Válido por rol; no todos son la misma instancia |

### 4.4 Máscaras, validez y NaN

| Concepto | Canon nuevo recomendado | Nombres actuales | Diagnóstico |
|---|---|---|---|
| Máscara de puntos | `point_mask` | `mask`, `level_mask`, `region_mask`, `point_mask` | `mask` genérico es ambiguo fuera de `TransformData` |
| Máscara de valores | `value_mask` o `finite_value_mask` | `nan_mask`, `valid`, `finite` | Separar máscara de puntos y máscara de payload |
| Validez de profundidad | `depth_valid_mask`, `valid_depth_points` | `opd_valid`, `valid_opd_points`, `nan_opd_points` | La API científica usa profundidad; OPD sólo aparece en la GUI |
| Validez de amplitud | `amplitude_valid_mask`, `valid_amplitude_points` | `amp_valid`, `valid_amplitude_points` | `amp_valid` debe desaparecer en API científica |
| Coordenadas finitas | `finite_coordinate_mask` | `finite_coordinates`, `finite_x`, `finite_y`, `finite_z` | Nombres locales aceptables; documentar shape |
| Hueco científico | `NaN` | `np.nan`, `missing`, `invalid` | No reemplazar por cero; el significado está bien preservado |

### 4.5 Dimensiones y conteos

| Concepto | Canon nuevo recomendado | Nombres actuales | Diagnóstico |
|---|---|---|---|
| Puntos actuales en array | `n_points` | `n_points` | Correcto |
| Puntos planificados | `planned_points` o `n_points_expected` | `n_points_total`, `expected_points` | Alias de metadata, no siempre equivalente |
| Puntos adquiridos | `acquired_points` | `n_points_acquired`, `acquired_points` | Alias externo/interno |
| Puntos comunes A/B | `n_points_common` | `n_points_common` | Correcto |
| Mediciones por punto | `measurements_per_point` internamente | `m_measurements`, `measurements_per_point` | Alias de schema; unificar interno |
| Ventanas configuradas | `n_windows` | `n_windows`, `window` | No mezclar cantidad con índice |
| Muestras espectrales | `n_spectral_samples` | `k_samples` | `k_samples` histórico; documentar si es dimensión espectral |
| Muestras de perfil | `n_profile_samples` | `profile_samples`, `global_profile_samples` | Alias externo; clarificar global vs por ventana |
| Shape | `shape` | `shape`, `tail_shape` | Correcto, pero debe acompañar nombre del payload |

### 4.6 Tolerancias y unidades

| Concepto | Canon nuevo recomendado | Nombres actuales | Diagnóstico |
|---|---|---|---|
| Tolerancia espacial escalar | `coordinate_tolerance_mm` | `coordinate_tolerance_mm`, `tolerance_mm` | Interno correcto; `tolerance_mm` sólo en contexto local |
| Tolerancia espacial por eje | `coordinate_tolerances_mm` | `coordinate_tolerances_mm`, `tolerance_x`, `tolerance_x_mm` | Unificar nombres internos por eje |
| Metadata histórica | `position_tolerance_*_mm` | `position_tolerance_*_mm` | Mantener como alias persistido |
| Tolerancia en µm | `position_tolerance_um` sólo en entrada externa | `position_tolerance_um` | No mezclar con valores internos en mm |
| Unidades declaradas | `units` | `units`, `unit`, `opd_unit` | `unit` sólo para un parámetro/plugin; `units` para mapa |
| Coordenada física | sufijo `_mm` | `coordinate`, `position`, `value` | Requiere revisión por función |

### 4.7 Estado, A/B y proveniencia

| Concepto | Canon nuevo recomendado | Nombres actuales | Diagnóstico |
|---|---|---|---|
| Fuente de datos | `dataset` o `source_data` | `source`, `data`, `source_data` | `source` tiene demasiados significados |
| Archivo de origen | `source_file` | `source_file`, `source` | Debe ser explícito cuando es ruta |
| Slot A/B | `slot` | `slot`, `label`, `source_a`, `source_b` | `slot` correcto; `label` no debe reemplazarlo |
| Fuente activa | `active_slot` | `active_source` | La GUI mezcla slot y objeto fuente |
| Resultado derivado | `derived_object` | `derived`, `result`, `result_data` | Distinguir objeto científico de array temporal |
| Padre | `parent_id` | `parent_id`, `derived_from` | ID y archivo de origen son magnitudes diferentes |
| Proveniencia | `provenance` | `provenance`, `transforms_applied`, `derived_from_sources` | Separar historial, origen y lista de transforms |
| Paso de pipeline | `pipeline_step` | `step`, `last_step`, `history` | `step` genérico es ambiguo |

### 4.8 Plugins y parámetros

| Concepto | Canon interno | Aliases aceptados | Diagnóstico |
|---|---|---|---|
| Tipo de plugin | `kind` | `tipo` | Normalización correcta en `PluginSpec` |
| Nombre visible | `name` | `nombre` | Alias de entrada |
| Descripción | `description` | `descripcion` | Alias de entrada |
| Función de aplicación | `apply_function` | `aplicar`, `apply` | Compatibilidad deliberada |
| ID de parámetro | `id` | `id` | Correcto |
| Tipo de parámetro | `type` | `tipo` | Alias bilingüe |
| Unidad de parámetro | `unit` | `unidad` | Correcto en `ParameterSpec`; debe declararse cuando sea física |
| Modifica amplitud | `modifies_amplitude` | `modifica_amplitud` | Correcto como contrato explícito |
| Parámetro OPD | `minimum_mm`, `maximum_mm`, `offset_mm` | nombres equivalentes declarativos | Correcto; no quitar sufijos |
| Parámetro eje | `axis` | `axis` | Debe ser `X/Y/Z/OPD` y no coordenada numérica |

## 5. Hallazgos reales prioritarios

### Alta prioridad: unidad física ausente en nombres internos

1. `WindowConfig.z_min/z_max` representan mm pero no lo expresan.
2. `LevelSelection.x_min/x_max/y_min/y_max` representan mm pero no lo expresan.
3. `SurfacePatchSpec.x_min/x_max/y_min/y_max` representan mm pero no lo expresan.
4. `extract_profile_x(y_value)`, `extract_profile_y(x_value)`, `extract_z_slice(z_value)` reciben coordenadas físicas sin sufijo.
5. `Cuts.x_position/y_position` devuelven coordenadas físicas sin sufijo.
6. `ScanGrid.x_unique`, `x_range`, `x_step` representan mm sólo por documentación.
7. Variables locales `tolerance`, `x_actual`, `y_actual`, `z_actual` mezclan valor físico y tolerancia sin marca de unidad.

### Alta prioridad: mismo concepto con abreviaturas distintas

1. `amplitude` frente a `amp`, `amp_prof`, `amp_win`, `amp_value`.
2. `win_id` frente a `window_id` y `window` para el selector de ventana.
3. `measurement` frente a `m_measurements` y `measurements_per_point`.
4. `profile_axes` frente a `profile_depth_axes_m`.
5. `valid_opd_points`/`opd_valid` y `valid_amplitude_points`/`amp_valid` mezclan conteos con estados.

### Prioridad media: nombres genéricos sobrecargados

1. `source` puede ser dataset, archivo, slot, plugin source o fuente A/B.
2. `data` puede ser `TransformData`, dict loader, array o resultado exportable.
3. `values` puede ser coordenada, OPD, amplitud, espectro o estadística.
4. `axis` puede ser nombre lógico, orientación visual o eje axial.
5. `mask` puede ser máscara de puntos, región, nivel, OPD o valores finitos.
6. `step` puede ser paso físico, paso de pipeline o etapa de historial.

### Riesgos de contrato, no renombrar ciegamente

1. `X/Y/Z` son atributos públicos de `OCTDataset`, `TransformData` y `DerivedObject`.
2. `opd` es clave histórica de payload y canal interno; ya existe metadata para distinguir `opd_mm` de `physical_depth_mm`.
3. `depth_m` y `profile_depth_m_wN` son claves externas expresadas en metros.
4. `position_tolerance_*` es metadata persistida; el interno preferido es `coordinate_tolerance_*`.
5. Los aliases bilingües de plugins son una frontera de compatibilidad, no duplicación accidental.
6. `X_mm/Y_mm/Z_mm` y `OPD_mm` son encabezados CSV; no deben reemplazarse por las claves NPZ.

## 6. Migración nominal aplicada

La migración se ejecutó como renombrado destructivo porque no existen mediciones históricas que preservar:

1. Usar `depth_m` como única clave persistida de profundidad.
2. Normalizar a `depth_mm` al entrar al Workbench.
3. Migrar modelo, extracción, ensamblado, comparación, plugins y GUI a `depth_mm`.
4. Usar `DEPTH` como eje interno de transforms; `OPD` queda en textos visibles.
5. Rechazar payloads con `opd`, `depth_mm` persistido o `depth_axis_kind` no físico.
6. Mantener regresiones de valores, shapes, unidades, masks, NaN, metadata y provenance.
7. Ejecutar suite completa y roundtrips.

## 7. Estado

- Inventario transversal: completado.
- Matriz concepto/nombre/unidad/semántica: completada.
- Clasificación de incoherencias y aliases: completada.
- Mapa canónico completo: documentado.
- Renombrados funcionales: **migración destructiva completada**.
- El canal de profundidad ya usa `depth_m` en persistencia y `depth_mm` en memoria;
  no se conservan aliases `opd` ni claves persistidas `depth_mm`.
- Claves NPZ/HDF5 y CSV: **sin cambios**.
- Verificación posterior a esta tanda: **194 tests pasados**, compilación completa y
  regresiones de núcleo/IO/extracción/ensamblado verificadas.

## 8. Fuente nominal prioritaria: `OCT_Static_Software`

Por decisión del usuario, `OCT_Static_Software` es la referencia nominal del software. La migración debe conservar sus nombres siempre que representen la misma magnitud y no exista una diferencia semántica real.

| Convención en `OCT_Static_Software` | Uso confirmado | Estado equivalente en Workbench | Acción prevista |
|---|---|---|---|
| `x_mm`, `y_mm` | Coordenadas espaciales de runtime y saver | `X`, `Y`, aliases `x_mm/y_mm` | Adoptar `x_mm/y_mm` internamente; conservar `X/Y` como aliases temporales |
| `z_mechanical_mm` | Coordenada Z mecánica explícita en adquisición/control | `Z` | Usar sólo en la frontera de hardware/adquisición si se necesita distinguirla de profundidad óptica; no imponerla al modelo completo |
| `z_mm` | Coordenada Z espacial/persistida | loader acepta `Z`, `z_mm`, `z_mechanical_mm` | Preferir `z_mm` en el modelo espacial y persistencia cuando no haya ambigüedad; conservar aliases de compatibilidad |
| `depth_m` | Profundidad física de entrada y eje axial | Workbench carga a `peaks["depth_mm"]` y `OCTDataset.depth_mm` | Contrato compartido; no existe alias `opd` |
| `amplitude` | Amplitud del pico/perfil | `amplitude`, además de abreviaturas locales | Unificar código científico en `amplitude` |
| `spectra` | Espectros crudos | `spectra` | Mantener |
| `profiles` | Perfiles axiales por ventana | `profiles` | Mantener; distinguir un perfil individual de su contenedor |
| `profile_depth_axes_m` | Ejes axiales físicos por ventana | `profile_depth_axes_m` | Mantener como nombre canónico |
| `measurements_per_point` | Cantidad de mediciones M | `m_measurements`, `measurement` | Adoptar `measurements_per_point` para cantidad; reservar `measurement_index` para índice |
| `WindowConfig.index` | Índice 0-based de ventana | `win_id` | Adoptar `window_index`/`index` según el contrato de Static; aliases de `win_id` |
| `depth_min_m`, `depth_max_m` | Límites físicos de ventana | `z_min`, `z_max` internos en mm | Usar nombres en metros en la capa de procesamiento Static; conservar conversión explícita en Workbench |
| `window_profile_samples` | Muestras del perfil de una ventana | `profile_samples`/campos derivados | Adoptar el nombre Static donde aplique |
| `planned_points` | Puntos planificados | `n_points_total` | Normalizar metadata interna a `planned_points` con alias histórico |
| `acquired_points` | Puntos adquiridos | `n_points_acquired` | Normalizar metadata interna a `acquired_points` |
| `written_points` | Puntos escritos | aparece en contratos Static, no como equivalente principal en Workbench | Incorporar sólo donde represente escritura real |
| `duration_s` | Duración del scan | `duration_sec` | Adoptar `duration_s`; conservar alias de lectura |
| `position_tolerance_mm` | Tolerancia de posición/movimiento | `coordinate_tolerance_mm` y por eje | Mantener la política anisotrópica, pero exponer alias compatible Static |
| `fiber_diameter_um` | Diámetro de fibra | `d_fiber_um` | Adoptar nombre Static en `Optics`, alias histórico `d_fiber_um` |
| `wavelength_nm` | Longitud de onda central | `wl_nm` | Adoptar nombre Static, alias `wl_nm` |
| `collimator_focal_length_mm` | Focal del colimador | `f_col_mm` | Adoptar nombre Static, alias `f_col_mm` |
| `objective_focal_length_mm` | Focal del objetivo | `f_obj_mm` | Adoptar nombre Static, alias `f_obj_mm` |
| `k_axis`, `spectra_k` | Eje y espectros en k uniforme | no hay equivalente único directo en Workbench | Adoptar si se incorpora esa capa de procesamiento |
| `depth_axis_m` | Eje de profundidad de un `WindowResult` | `profile_depth_axes_m` por contenedor | Usar para un eje individual; mantener plural para mapa por ventana |
| `window_id` | Identificador de ventana en `PeakData` | `win_id` | Adoptar `window_id` en resultados; alias `win_id` |

### Diferencia que debe conservarse

`z_mechanical_mm` se reserva para adquisición/control cuando hace falta remarcar que la coordenada pertenece al eje mecánico. `z_mm` puede ser el nombre preferible para el modelo espacial y para persistencia si no existe ambigüedad. `depth_m` es profundidad óptica/física y nunca debe mezclarse silenciosamente con la coordenada espacial Z ni con OPD. La propia referencia `OCT_Static_Software` presenta ambos usos —incluido un mock de test con `z_mm`—, por lo que no se debe copiar `z_mechanical_mm` como regla global.

### Orden de migración alineado con `OCT_Static_Software`

1. Renombrar variables locales y nuevos objetos a los nombres Static.
2. Añadir aliases de propiedades y constructores para `X/Y/Z`, `opd`, `d_fiber_um`, `wl_nm`, `f_col_mm` y `f_obj_mm`.
3. Migrar `Optics`, estados de scan, ventanas y metadata normalizada.
4. Separar por capa `z_mm` espacial, `z_mechanical_mm` de hardware —sólo si aporta información— y `depth_m` óptica.
5. Separar explícitamente `depth_m`, `physical_depth_mm` y `opd_mm` sin alterar Schema 6.
6. Migrar extracción, comparación, ensamblado, GUI y plugins por bloques.
7. Mantener las claves persistidas de `OCT_Static_Software` y verificar roundtrips con fixtures del productor.

## 5. Estado de la migración nominal compatible

La migración por bloques alcanzó 16 de 16 frentes nominales planificados. Se añadieron contratos canónicos sin retirar aliases históricos ni modificar `OCT_Static_Software`:

- límites físicos explícitos en mm y metros derivados para ventanas, niveles, superficies y `ScanGrid`;
- `requested_*_mm` y aliases `window_index`/`measurement_index` en extracción, comparación y GUI;
- separación de lectura `opd_mm`, `physical_depth_mm`, `depth_m` y `depth_axis_kind`;
- amplitud con nombre público `amplitude`, reemplazando abreviaturas locales en extracción/ensamblado;
- ejes de perfil individuales mediante `profile_depth_axis_m(window_index)` frente al contenedor plural;
- máscaras booleanas por coordenadas, OPD y amplitud, separadas de los conteos de calidad;
- tolerancias anisotrópicas explícitas `position_tolerance_*_mm`;
- metadata de lectura `spectral_samples`, `profile_samples` y `scan_aborted`;
- constructor compatible de `WindowConfig` con `window_index` y `depth_min/max_mm`.

Los nombres genéricos (`source`, `values`, `axis`, `mask`, `step`) no se sustituyeron globalmente: sólo se modernizaron usos con contrato inequívoco. `Cuts` conserva su constructor de payload completo y expone aliases de lectura, evitando duplicar un constructor frágil.

### Validación de la tanda nominal histórica:

- suite completa con `QT_QPA_PLATFORM=offscreen`: `204 passed`;
- compilación forzada de módulos modificados: correcta;
- schemas NPZ/HDF5/CSV: sin cambios intencionales;
- `OCT_Static_Software`: no modificado.

## 6. Nueva auditoría independiente de verificación (histórica; baseline previo a las correcciones)

Fecha de verificación: 2026-08-10. Esta revisión se realizó sobre una copia temporal del árbol para evitar que los tests alteraran fixtures del workspace. El directorio no es un repositorio Git, por lo que no fue posible comparar un diff formal ni atribuir cambios por commit.

### Evidencia positiva

- Suite completa headless: `204 passed in 12.39s`.
- Integración I/O/schema/export: `21 passed`.
- GUI y plugins: `73 passed`.
- `compileall` sobre módulos y tests: correcto.
- Imports y resolución de type hints de los módulos centrales: correctos.
- No se modificó `OCT_Static_Software`.

### Hallazgos confirmados

| Severidad | Hallazgo | Evidencia |
|---|---|---|
| Alta | `export._resolve_to_data()` serializa siempre el canal interno como `depth_m`, incluso cuando el origen declara `depth_axis_kind = "opd_mm"`. Un NPZ OPD reexportado se recarga como `physical_depth_mm` y pierde `opd_mm`. | Probe directo NPZ → `to_npz()` → loader: `opd_mm` pasó a `physical_depth_mm`. |
| Alta | `ComparisonPair` compara cualquier canal `td.opd` como OPD y etiqueta el resultado con `units: {opd: mm}`, aun cuando ambos datasets declaran `physical_depth_mm`. | Probe directo: dos datasets físicos produjeron `stats_label = "mm"` y `diff_metadata.units.opd`. |
| Alta | Los aliases de índice no detectan siempre conflictos: `win_id=0, window_index=1` se acepta y selecciona la ventana 1. El mismo patrón existe para mediciones y comparación, porque `0` se usa como valor por defecto y como sentinel implícito. | Probe directo de `extract_window()` aceptó la combinación discrepante. |
| Media | `extract_window(window_index=-1)` no rechaza el índice negativo y devuelve un objeto con canal vacío por el slicing `-1:0`. | Probe directo: llamada aceptada con `opd = [[[]]]`. |
| Media | Los exportadores anuncian `filepath: str` pero fallan con `pathlib.Path` en `_ensure_ext()` (`.lower()`); afecta `to_npz`, `to_h5`, `to_npy`, `to_png`, `to_csv` y `stats_to_csv`. | Probe directo con `Path`: `AttributeError: PosixPath has no attribute lower`. |
| Media | La heurística del loader interpreta un payload legacy `opd` pequeño (`0.05`) como metros y lo convierte a `50 mm`; la clave no contiene unidad suficiente para resolver esa ambigüedad con seguridad. | Probe directo: `opd=0.05` terminó como `physical_depth_mm=50.0`. |
| Baja | El módulo de exportación documenta `ComparisonPair` como fuente aceptada, pero `Source` y `_resolve_to_data()` sólo aceptan `OCTDataset`, `TransformedView` y `DerivedObject`. | Inspección estática de `exporter.py`; no hay cobertura de exportación directa de `ComparisonPair`. |

### Cobertura faltante

La suite actual valida los roundtrips Schema 6 físicos, pero no contiene regresiones específicas para: roundtrip OPD explícito, comparación de profundidad física, conflicto `0`/alias canónico, índices negativos, `pathlib.Path` en exportadores ni payloads legacy OPD de magnitud menor a `0.1`.

### Estado y recomendación

La migración nominal está completa en nombres y aliases, pero la auditoría **no debe cerrarse como libre de riesgos**: los tres hallazgos de severidad alta afectan semántica científica y pueden producir resultados físicamente mal etiquetados sin hacer fallar la suite. Recomiendo corregirlos antes de aceptar archivos OCT reales como validación final. No se aplicaron correcciones de código durante esta auditoría.

`pip check` no pudo ejecutarse porque el entorno `.venv` no contiene el módulo `pip`; esto queda como limitación del entorno de verificación.

## 7. Addendum histórico: probes de frontera y paridad de writers

Fecha: 2026-08-10. Esta pasada adicional se ejecutó fuera del árbol activo, con fixtures temporales, y no modificó código de producción ni `OCT_Static_Software`.

### Hallazgos adicionales confirmados

| Severidad | Archivo/línea | Hallazgo | Evidencia |
|---|---|---|---|
| Alta | `model/dataset.py:811-815` | `_build_grid()` usa la tolerancia escalar máxima para X/Y/Z, aunque conserva tolerancias anisotrópicas. | Con tolerancias X=0.001 mm, Y=0.1 mm y separación X=0.05 mm, la grilla resultó `nx=1`; esperado `nx=2`. |
| Alta | `transforms/base.py:343-390` | `TransformedView.topography_grid()` no rechaza duplicados XY ni valida `nz`; sobrescribe la celda con el último valor. | Dos puntos XY idénticos con Z distinto fueron aceptados y devolvieron una grilla de un único valor. La ruta `OCTDataset.topography_grid()` sí rechaza duplicados, por lo que las capas divergen. |
| Alta | `work_io/loader.py:504-525` | La validación de shapes exige sólo el primer eje de picos; acepta payload rank-2 donde el contrato documenta `(P,M,W)`. | Payload `depth_m.shape=(2,1)` fue aceptado como `opd.shape=(2,1)`. |
| Alta | `export/exporter.py:36-126` | `DerivedObject` se exporta sin límites de ventanas; al recargar queda `n_windows=0` aunque conserve el payload axial. | Roundtrip NPZ y HDF5: `shape=(2,1,1)`, pero `windows=0`. |
| Alta | `export/exporter.py:48-56, 108-125` | `TransformedView` copia `dataset.metadata` pero no persiste el historial de transformaciones de la vista. | Tras aplicar `InvertAxis`, el NPZ no contenía `transforms_applied`. |
| Alta | `work_io/loader.py:256-295` y aliases NPZ | Los aliases de cardinalidad `M` no son equivalentes entre formatos. | NPZ con `m_measurements=1` y `measurements_per_point=2` fue aceptado como M=2; HDF5 equivalente fue rechazado por inconsistencia. |
| Media | `model/dataset.py:737-796` vs `transforms/base.py:343-390` | La validación de Multi-Z/duplicados no está centralizada: el modelo rechaza y la vista transformada acepta. | Probe con XY duplicado y Z distinto. |
| Media | `model/dataset.py` / `transforms/base.py` | La API genérica `TransformedView.profile_1d()` ordena siempre por X y no representa un perfil sólo-Y. | Dataset X constante/Y variable: devolvió `X=[0]`; `extract_profile_y()` explícito sí devolvió Y correctamente. |
| Media | `model/dataset.py` y loader | Un payload con W>1 pero sin metadata de ventanas se acepta, pero el modelo queda con `n_windows=0`; el dato no puede seleccionarse funcionalmente. | `opd.shape=(2,2,2)` cargó como M=2 pero `topography_grid(win_id=1)` falló por ausencia de ventanas. |
| Alta | `OCT_Static_Software/storage/saver.py:321-364` | El writer NPZ compacta payloads de picos opcionales: si falta un punto intermedio, `depth_m` queda con menos filas que X/Y/Z. | Scan de 3 puntos con payload ausente en el punto 1: NPZ no recargó (`primer eje ... no coincide`). |
| Alta | `OCT_Static_Software/storage/saver.py:442-471, 533-552` | El writer HDF5 conserva la posición y deja `NaN` en el payload faltante, mientras NPZ compacta y falla; no hay contrato común. | Mismo scan: HDF5 recargó `shape=(3,2,1)` con 2 NaN; NPZ falló al cargar. |
| Alta | `OCT_Static_Software/storage/saver.py:490-531` | HDF5 crea datasets de perfiles sólo con el primer punto; si el primer perfil está vacío y uno posterior es válido, lo omite. | NPZ conservó `profile W0.shape=(3,1,3)`; HDF5 quedó sin perfiles ni eje. |
| Media | `OCT_Static_Software/storage/saver.py:345-352` vs `:584-612` | La política de scan vacío diverge entre formatos. | NPZ devolvió `None` y no creó archivo; HDF5 devolvió ruta y creó archivo vacío. |

### Verificaciones positivas de esta pasada

- Suite completa aislada con Qt offscreen: `204 passed in 11.53s`.
- GUI/plugins focalizados: `31 passed in 1.58s`.
- I/O/export/Schema 6/loader y contrato saver: `21 passed in 0.72s`.
- Tests directos del saver externo: `6 passed in 0.19s`.
- `compileall`: correcto.
- `typing.get_type_hints()` en 10 módulos centrales: sin errores.
- `uv pip check`: todos los paquetes instalados compatibles.
- Paridad Z en comparación: datasets con XY igual y Z distinto no se alinearon; se produjo `ValueError` por ausencia de puntos comunes.
- Payload incompleto sin amplitud: rechazado explícitamente.
- Extracción explícita Y-only: correcta.
- No se modificó `OCT_Static_Software`; los scripts temporales de probes fueron eliminados.

### Deuda y limitaciones

- `requirements.txt` no fija versiones (`numpy`, `matplotlib`, `PyQt5`, `h5py`, `scipy`); queda como deuda de reproducibilidad/cadena de suministro, no como bug demostrado en los probes.
- `pyflakes` no está instalado.
- El árbol no es un repositorio Git; no existe diff formal.
- La suite generó o ya contenía caches `__pycache__`/`.pytest_cache`; no se eliminaron porque forman parte de los artefactos protegidos del workspace.
- No se validó con archivos OCT reales de laboratorio ni con hardware físico.

### Veredicto histórico de esa pasada

La migración nominal de nombres y aliases sigue siendo **16/16 frentes implementados**, y la integración nominal tiene una suite verde. Sin embargo, el contrato científico y de persistencia **no está cerrado**: permanecen pérdidas de semántica OPD, divergencias NPZ/HDF5, pérdida de ventanas/proveniencia, tolerancias por eje mal aplicadas y rutas transformadas que no validan Multi-Z/duplicados. Deben corregirse y cubrirse con regresiones antes de aceptar la auditoría como aprobación científica o antes de validar archivos OCT reales.

## 8. Estado actual después de la tanda de correcciones

Fecha de actualización: **2026-08-10**. Las secciones históricas anteriores
conservan el baseline y los hallazgos originales; este apartado es el estado
vigente del árbol actual.

### Correcciones implementadas y verificadas

- Preservación explícita de `depth_axis_kind` y `depth_source_key` en carga y
  exportación; OPD no se convierte silenciosamente en profundidad física.
- `ComparisonPair` conserva la semántica del eje y rechaza mezclar OPD con
  profundidad física.
- Aliases de ventana/medición/comparación distinguen `None` de índice `0` y
  rechazan conflictos; los índices negativos se rechazan.
- `_build_grid()` usa tolerancias independientes por eje.
- `topography_grid()` rechaza celdas XY duplicadas en datasets y vistas
  transformadas.
- Los payloads de picos exigen shape `(P, M, N_win)`.
- Los `DerivedObject` conservan límites de ventana y provenance en roundtrip.
- `TransformedView` conserva `transforms_applied` en exportación.
- El writer HDF5 del Workbench incluye el canal `depth_m` cuando corresponde.

### Evidencia actual

- Suite completa con `QT_QPA_PLATFORM=offscreen`: **219 passed**.
- Suite focalizada de exportación, comparación, extracción, grillas y loader:
  **50 passed**.
- Aceptación sintética usando la implementación real de
  `OCT_Static_Software/storage/saver.py`, con roundtrip Workbench NPZ/HDF5:
  **2 passed**.
- Smoke test GUI Qt offscreen sobre datos sintéticos: **52 passed**.
- `compileall`: correcto.
- ZIP distribuible generado y validado: `../OCT_Workbench_depth_migration.zip`.
- `OCT_Static_Software` no fue modificado.
- El árbol no es un repositorio Git; no existe diff formal por commit.

### Pendientes que no se presentan como resueltos

1. **Resuelto:** los exportadores aceptan uniformemente
   `pathlib.Path`; `_ensure_ext()` normaliza mediante `os.fspath()` y cuenta con
   regresión dedicada.
2. **Compatibilidad externa normal verificada:** el flujo normal del saver de
   `OCT_Static_Software` con arrays completos de picos pasó por NPZ y HDF5,
   incluyendo conversión `depth_m` ↔ `depth_mm`, shapes, `NaN` y metadata.
   Los payloads opcionales ausentes, perfiles vacíos y scans vacíos siguen fuera
   del alcance y no justifican modificar el saver.
3. **Aceptación científica pendiente:** no se validó con archivos OCT reales de
   laboratorio ni con hardware físico.
4. **Reproducibilidad:** `requirements.txt` no fija versiones completas; queda
   como deuda de entorno, no como bug funcional confirmado.
5. **Documentación histórica:** las secciones previas de este informe son
   evidencia del baseline; este apartado prevalece para el estado actual.

### Veredicto vigente

La **etapa de corrección del código del Workbench queda cerrada y verificada**.
La compatibilidad del flujo normal con el saver externo quedó verificada con
datos sintéticos. La auditoría no debe etiquetarse todavía como aprobación
científica final: falta ejecutar la aceptación con mediciones OCT reales y,
cuando estén disponibles, validar hardware físico.

### Congelamiento y reapertura

El árbol queda congelado hasta disponer de mediciones reales. No se agregan
funcionalidades, no se inicia la extracción de `WorkbenchSession`, no se
adelgaza `MainWindow`, no se hacen nuevos renombrados globales y no se modifica
funcionalmente `OCT_Static_Software` durante este intervalo.

Para reabrir el plan se debe:

1. cargar un NPZ/HDF5 real producido por `OCT_Static_Software`;
2. verificar `depth_m`/`depth_mm`, ventanas, amplitudes, `NaN`, shapes,
   cardinalidad, metadata y provenance;
3. completar roundtrip NPZ/HDF5 y reapertura;
4. ejecutar el recorrido GUI A/B completo, incluyendo filtros, geometría,
   comparación, perfiles, cortes, B-scan, ensamblado y exportación;
5. cubrir 2D, Multi-Z/3D y ventanas sin pico;
6. validar hardware físico si está disponible;
7. actualizar este veredicto y regenerar el ZIP de release.

La deuda estructural queda registrada, pero no bloquea el congelamiento:
`WorkbenchSession`, adelgazamiento de `MainWindow`, renderers separados,
writers de tests aislados en `tmp_path`, opciones tipadas de plugins GUI,
redraws duplicados, controles ante coordenadas totalmente `NaN` y versiones
completas de `requirements.txt`.
