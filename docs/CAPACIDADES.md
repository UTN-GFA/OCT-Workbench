# OCT Workbench — Mapa de capacidades funcionales

## Propósito

Workbench genérico para **abrir, inspeccionar, visualizar, comparar, preparar reversiblemente, extraer, ensamblar manualmente y exportar** mediciones OCT 2D, Multi-Z y 3D.

El archivo fuente permanece intacto. A y B usan pipelines independientes por defecto. Las vistas transformadas y los objetos derivados conservan unidades, coordenadas, metadata y proveniencia.

## Vistas de producto

La GUI conserva exactamente seis pestañas:

```text
Niveles | Superficie | Topografía | Reflectividad | Cortes | Histograma
```

No se agrega una pestaña independiente para ensamblado, Metadata ni comparación.

## Capacidades conservadas/completadas

### Carga e inspección

- Carga A/B de NPZ, HDF5 y H5.
- Carga de un archivo contra un objeto derivado.
- Clasificación genérica del tipo de medición.
- Resumen de grilla/layout físico: `nx × ny × nz`, rangos y pasos.
- Metadata curada: muestra, archivo, fecha/duración si existen, unidades, payloads y advertencias.
- Indicadores de calidad: puntos totales, OPD válido, amplitud válida, `NaN`, cobertura, adquiridos/esperados y estado completo/incompleto/abortado.
- Inspector técnico secundario y colapsable de keys/shapes/dtypes relevantes, sin volcado indiscriminado.

### Niveles y vistas

- Navegación de niveles Z para mediciones 2D y Multi-Z/3D.
- Una medición 2D se trata como volumen con `nz = 1`.
- Prisma geométrico A/B con nivel activo resaltado.
- Exclusión/restauración reversible de niveles sin mutar el origen.
- Superficie: OPD del nivel seleccionado.
- Topografía: OPD sobre XY con codificación cromática.
- Reflectividad: amplitud de señal reflejada; la etiqueta visible sigue siendo `Reflectividad`.
- Histograma: distribución de OPD.
- Topografía y Reflectividad son vistas independientes: Topografía representa OPD y Reflectividad representa amplitud.

### A/B

- Comparación visual lado a lado.
- Escalas, rangos y unidades compatibles/sincronizables.
- A y B independientes por defecto para nivel, ventana, medición, filtros, transformaciones, cortes y perfiles.
- Coordinación A/B explícita y opt-in para nivel, ventana y medición; Cortes permanece siempre independiente.
- Al activar coordinación, los valores actuales se sincronizan de inmediato; si el rango de B no alcanza, la GUI informa el límite aplicado en lugar de ocultarlo.
- Comparación punto a punto tolerante.
- Diferencia opcional con signo definido `A − B`.
- Estadísticas únicamente de la diferencia: puntos comunes, media, STD, pico-valle, RMS y máximo absoluto.
- Comparación de perfiles X/Y en Cortes.

### Cortes y extracción

- Cortes físicos XY/XZ/YZ por coordenada y tolerancia.
- `XY → Z fijo`, `XZ → Y fijo`, `YZ → X fijo`.
- Dataset 2D: sólo corte XY.
- XZ/YZ: sólo cuando el payload contiene información suficiente.
- Sin interpolación ni voxelización automática.
- Perfiles X/Y interactivos desde A o B.
- Perfil axial desde `profile_mod_wN`/`profile_real_wN` con eje persistido.
- B-scan espectral desde `spectra` + `wavelengths_nm`.
- Objetos derivados con proveniencia y lista compacta en GUI.

### Preparación reversible

- Máscara OPD usando `NaN`, conservando la grilla.
- Offset OPD automático: llevar el mínimo finito a `0`.
- Inversión OPD disponible sólo dentro de Filtro OPD.
- Invertir ejes X/Y/Z.
- Espejar X/Y.
- Offset X/Y/Z.
- Centrar origen.
- Nivelado global por plano ajustado por mínimos cuadrados, aplicado como `OPD_plano − OPD_medido` sobre la ventana/medición elegida y reversible.
- Nivelado por regiones rectangulares X/Y en Superficie y Topografía.
- Filtro de mediana 2D como filtro secundario en Superficie y Topografía.
- Filtro OPD, filtro secundario y nivelado por regiones se presentan juntos bajo el bloque **Filtros**, sin repetir el título de la etapa dentro de cada tarjeta; cada operación conserva su transformador y restauración selectiva.
- La navegación común **Selección | Filtros | Geometría** mantiene A/B alineadas y permite acceder a cada sección desde cualquier pestaña de análisis; la vista activa no bloquea ni oculta filtros o geometría. Dentro de **Geometría**, las operaciones son controles directos y no hay selector **Acción**.
- Plugins locales de filtros y geometría mediante archivos `.py` completos, copiables desde plantillas privadas.
- Metadata declarativa de plugins, controles Qt automáticos, fachada `Superficie` para laboratorio, validación de parámetros y validación de shape/salida. Los plugins que modifican OPD y amplitud deben declarar `modifica_amplitud: true` y usar `con_z_y_amplitud`; la amplitud sigue protegida por defecto.
- Los plugins se incorporan al pipeline lógico existente, conservando independencia A/B, historial, deshacer, proveniencia y no mutación de la fuente. Cada plugin integrado contiene su propia operación y usa la fachada `Superficie`; no delega la matemática a módulos históricos. Las implementaciones antiguas fueron retiradas del árbol activo y sólo existen en el rollback externo.
- Un plugin inválido se registra como error de descubrimiento y no bloquea el arranque del Workbench.
- Cada vista gráfica incorpora navegación Matplotlib: rueda para zoom centrado en el cursor, toolbar para zoom rectangular, paneo, restaurar vista y guardar figura. En 3D la superficie ensamblada usa proyección ortográfica: la rueda modifica sólo la distancia de cámara y el zoom rectangular conserva Z y la orientación, mientras el paneo permite estudiar cada parche sin alterar X, Y, Z, OPD ni las mallas nativas.
- En OPD, **Auto offset** y **Offset** son controles separados; la mediana se parametriza por **Matriz cuadrada**.
- Pipeline visible de transformaciones, proveniencia y restauración.
- Los controles **Deshacer**, **Historial**, **Restaurar** y **Último paso** de cada muestra se muestran en una fila propia de la barra superior, separados de las acciones globales para evitar truncamiento, y permanecen disponibles en todas las vistas.
- Las operaciones geométricas auto-inversas consecutivas (por ejemplo, **Invertir X** dos veces) se cancelan por pares y el historial conserva el estado neto activo.
- Restaurar Nivelado por regiones o Mediana quita sólo ese paso y conserva el resto del pipeline; Restaurar original limpia todos los pasos.
- Fuente original inmutable.

### Ensamblado y exportación

- Ensamblado de niveles de una misma Muestra/medición.
- Ensamblado A/B de superficies nativas mediante una lista de parches independientes.
  Cada parche conserva fuente, nivel, dominio X/Y, coordenadas reales, `paso_x`,
  `paso_y`, posición Z y máscara de válidos; no se interpola ni se fuerza una
  grilla común.
- Selección/exclusión de niveles, región X/Y y `ΔZ` independiente por nivel.
- Parches con extensiones XY, cantidades de puntos y resoluciones diferentes.
- Huecos como ausencia de puntos/`NaN`, cobertura y advertencias.
- Muestra derivada guardable y reabrible.
- Recorte y reconstrucción de niveles tolerantes al jitter de adquisición; los huecos de borde de un recorte rectangular se conservan como `NaN` dentro de la malla nativa, sin degradar el parche completo a puntos.
- Los valores OPD/amplitud que son `NaN` por filtros se conservan junto con sus coordenadas; las mallas estructuradas se reconstruyen con huecos y el 3D ignora esos NaN al calcular límites de eje.
- Exportación contextual CSV, NPZ, HDF5 y PNG.
- CSV con unidades, metadata y proveniencia en comentarios.
- NPZ/HDF5 reabribles en el Workbench.

## Estado técnico y producto

| Elemento | Producto |
|---|---|
| `CropRegion` XY | Plugin integrado de backend/derivadas; no control permanente |
| Inspector keys/shapes/dtypes | Metadata secundaria/colapsable |
| Lista de derivados | Compacta; sin gestor avanzado |
| Filtro mediana | Incluir como filtro secundario |
| Gaussiano | No incluir |
| Outliers automáticos `n×σ` | No incluir |
| Nivelado por media | No incluir |
| Estadísticas individuales A/B | No incluir por ahora |
| `CropOPDRange` | Retirar del producto y del backend |

## Fuera de alcance permanente

El Workbench no incorpora análisis específicos de muestra, instrumento o aplicación:

- Ajustes exponenciales, ERF o gaussianos interpretativos.
- Rugosidad `Ra/Rz/Rmax`.
- Altura de escalón.
- Cintura de haz `ω₀`, longitud de Rayleigh `z_R` o apertura numérica `NA`.
- Parámetros confocales o distancia de trabajo.
- Repetibilidad temporal, drift o relajación.
- Pasos de motor, backlash o control de adquisición.
- Calibraciones científicas no declaradas en el payload.
- Interpolación automática.
- Voxelización automática.

## Reglas físicas y de datos

- Profundidad física, OPD y amplitud permanecen separadas.
- No se afirma calibración física no garantizada por el payload.
- La tolerancia `coordinate_tolerance_mm` se conserva y exporta.
- Las transformaciones, máscaras, exclusiones, nivelados, selecciones y derivadas no mutan el archivo fuente.
- El ensamblado no infiere offsets laterales, rotaciones ni registros geométricos desconocidos.

## Estado de verificación actual

La tanda de correcciones de código queda verificada con **219 passed** usando
`QT_QPA_PLATFORM=offscreen`, además de compilación completa y roundtrips
focalizados. Se verificaron la semántica explícita de profundidad, aliases e
índices, tolerancias por eje, duplicados XY, shapes `(P, M, N_win)`, ventanas y
proveniencia de objetos derivados y vistas transformadas. También se verificaron
la exportación de `ComparisonPair` como resultado A−B, la validación previa de
índices en transformaciones de superficie, la aceptación sintética del saver
real de `OCT_Static_Software` en NPZ/HDF5 (**2 passed**) y el smoke test GUI
offscreen (**52 passed**).

Esto cierra la corrección del Workbench, no la aceptación científica completa.
Continúan pendientes:

- aceptación manual con archivos OCT reales: 2D, Multi-Z/3D, A/B, cortes,
  perfiles, B-scan, ensamblado, reapertura y exportación;
- validación con hardware físico;
- casos límite opcionales del saver externo fuera del flujo normal, que no fue
  modificado;
- actualización futura de los contratos del saver externo o de su migrador,
  sólo si se decide ampliar el release.

### Alcance congelado

El árbol queda congelado hasta disponer de mediciones OCT reales. Durante el
congelamiento no se agregan funcionalidades, no se inicia la extracción de
`WorkbenchSession`, no se adelgaza `MainWindow`, no se hacen nuevos
renombrados globales y no se modifica funcionalmente el saver externo.

La reapertura del plan requiere, en este orden:

1. cargar un NPZ/HDF5 real producido por `OCT_Static_Software`;
2. verificar `depth_m`/`depth_mm`, ventanas, amplitudes, `NaN`, shapes,
   cardinalidad, metadata y provenance;
3. completar roundtrip NPZ/HDF5 y reapertura;
4. probar GUI A/B, filtros, geometría, comparación, perfiles, cortes, B-scan,
   ensamblado y exportación;
5. cubrir mediciones 2D, Multi-Z/3D y ventanas sin pico;
6. validar hardware físico cuando esté disponible;
7. actualizar el veredicto científico-operativo y regenerar el ZIP final.

La deuda estructural y de reproducibilidad queda diferida: `WorkbenchSession`,
adelgazamiento de `MainWindow`, renderers separados, migración completa de
writers de tests a `tmp_path`, opciones tipadas de plugins GUI, redraws
duplicados, controles ante coordenadas totalmente `NaN` y versiones fijadas de
`requirements.txt`.

## Fuentes históricas

Los scripts históricos y `Visualizador_OCT_V43_Compatible.py` son referencias externas de capacidades, no contratos ni archivos incluidos en este árbol.
