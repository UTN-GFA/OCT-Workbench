# OCT Workbench

Workbench genérico de visualización, comparación, preparación reversible, extracción y exportación de mediciones. El software de adquisición queda fuera de este proyecto; el Workbench consume los datos que éste genera.

## Alcance cerrado

El flujo del Workbench es:

```text
Abrir → inspeccionar → visualizar → comparar → preparar reversiblemente
→ extraer → ensamblar manualmente → exportar
```

Se conservan las seis pestañas `Niveles`, `Superficie`, `Topografía`, `Reflectividad`, `Cortes` e `Histograma`. A y B son independientes por defecto; la coordinación es opt-in. La diferencia `A − B` es opcional y sus estadísticas se calculan sólo sobre la diferencia.

La interfaz mantiene un encabezado mínimo con el título y el estado global. Las acciones de carga, comparación, metadata, exportación y creación de derivadas viven en la etapa **Selección**, junto con las tarjetas compactas A/B y una sección común de **Preparación**; **Filtros** y **Geometría** quedan reservados para transformar los datos. El sidebar y el canvas se reparten mediante un divisor redimensionable, sin depender de una resolución de pantalla particular.

La máscara OPD es reversible y conserva la grilla. El bloque **Filtros** expone también **Nivelar plano**, que ajusta un plano por mínimos cuadrados para la ventana/medición elegida y calcula `OPD_corregido = OPD_plano − OPD_medido` punto a punto; el original permanece intacto. `CropOPDRange` se retira del producto y del backend. La mediana 2D se ofrece como filtro secundario sólo en Superficie y Topografía. Gaussiano, outliers automáticos y nivelado por media no forman parte del producto.

El ensamblado de superficies A/B se prueba como una derivada compuesta de parches nativos. Cada parche puede tener dominio X/Y, cantidad de puntos, `paso_x`, `paso_y` y posición Z diferentes; se dibujan juntos usando sus coordenadas físicas sin interpolación ni grilla común implícita.

El Workbench no incorpora análisis específicos de muestra, instrumento o aplicación, interpolación automática, voxelización, calibraciones no declaradas, ajustes científicos, rugosidad, altura de escalón, parámetros confocales, drift ni control de adquisición.

## Primera instalación

En Windows, podés ejecutar `Instalador.bat` desde la carpeta del proyecto. El script busca Python 3.12, crea `.venv`, actualiza `pip` e instala las dependencias
reales de `requirements.txt`. Si Python no está instalado, intenta usar
`installers\\python-3.12.10-amd64.exe` sólo si ese instalador local fue agregado al
proyecto; de lo contrario informa que Python debe instalarse manualmente.

También se puede hacer manualmente:

```powershell
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install --upgrade pip
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.\\.venv\\Scripts\\python.exe oct_workbench_gui.py
```

Una vez instalado el entorno, `Setup.bat` abre la GUI con el Python del entorno virtual. Si todavía no existe `.venv`, ejecutá primero `Instalador.bat`.


## Estructura activa

```text
oct_workbench_gui.py       GUI principal
model/                    modelo de datos y layout físico de niveles
  volume.py               layout común 2D/3D y selección reversible de niveles
  level_assembly.py       ensamblado derivado de Niveles de una misma Muestra/medición
  surface_assembly.py     ensamblado A/B de parches con mallas nativas
gui/                      estado, metadata y diálogos Qt de la GUI
  display_state.py        estado central de visualización A/B
  metadata.py             inspección de metadata y calidad
  level_assembly_dialog.py editor Qt de regiones y ΔZ por Nivel
  surface_assembly_dialog.py editor Qt de parches A/B, dominios y ΔZ
work_io/                  carga NPZ/HDF5
extract/                   perfiles, cortes y objetos derivados
transforms/                transformaciones reversibles
  filters/                plugins de filtros locales + plantilla
  geometry/               plugins geométricos locales + plantilla
  plugin_api.py           contrato y validación de plugins
  plugin_surface.py       fachada simple `Superficie` para el laboratorio
  discovery.py            descubrimiento automático por carpeta
compare/                   compatibilidad A/B, pares y estadísticas
export/                    exportación Schema 6.0 y formatos tabulares
tests/                     pruebas automatizadas
test_data/                 datos usados por las pruebas
docs/                      documentación funcional y diseño de usuario
README.md                  mapa del proyecto
```

La arquitectura activa está organizada en paquetes del nivel raíz; la GUI auxiliar vive en `gui/` y la documentación funcional en `docs/`. No existe un wrapper adicional `oct_workbench/`.

No existen módulos de compatibilidad entre arquitecturas: cada responsabilidad tiene una implementación canónica dentro de estos paquetes.

## Plugins locales de filtros y geometría

El laboratorio puede agregar una operación sin modificar la GUI ni el pipeline. Para hacerlo:

1. Copiar `transforms/filters/_plantilla_filtro.py` o `transforms/geometry/_plantilla_geometria.py`.
2. Guardar la copia con un nombre nuevo que termine en `.py`.
3. Completar el bloque `PLUGIN` y modificar solamente la función `aplicar`.
4. Reiniciar el Workbench: el archivo se descubre automáticamente y aparece en `Plugins locales`. El proyecto incluye `transforms/geometry/rotar_90.py` como ejemplo operativo.

Los filtros reciben una fachada segura `superficie` y deben devolver otra superficie mediante `con_z(...)`, `conservar_puntos(...)` u otro constructor permitido. Las geometrías deben devolver otra `Superficie` sin remuestrear valores. Un plugin que modifique OPD y amplitud debe declarar `"modifica_amplitud": true` y usar `superficie.con_z_y_amplitud(...)`; sin esa declaración el adaptador lo rechaza. El Workbench valida parámetros, shape, metadata, unidades, máscara, perfiles, errores de carga y compatibilidad antes de incorporarlos al historial. Los archivos que empiezan con `_` son plantillas y no se cargan.

Los filtros y geometrías integrados implementan su operación dentro de cada plugin mediante `PLUGIN` + `aplicar(superficie, parametros)`. La fachada `Superficie` centraliza copias seguras, shapes y unidades; el pipeline centraliza validación, historial y proveniencia. Las implementaciones históricas fueron retiradas del árbol activo y se conservan únicamente como rollback externo.


## Verificación

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m compileall -q -f oct_workbench_gui.py compare export extract gui model work_io transforms tests
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
```

## Estado de verificación actual — 2026-08-10

La tanda de correcciones del Workbench está implementada y verificada:

- Suite completa con Qt headless: **223 passed, 1 skipped**.
- Compilación de paquetes y tests: correcta.
- Regresiones de OPD/profundidad, aliases con índice `0`, índices negativos,
  tolerancias anisotrópicas, duplicados XY, shapes `(P, M, N_win)`, ventanas y
  proveniencia: verificadas.
- NPZ/HDF5 del Workbench: roundtrips focalizados verificados.
- Saver real de `OCT_Static_Software` con datos sintéticos: roundtrip NPZ/HDF5
  verificado.
- Smoke test GUI Qt offscreen: **52 passed**.
- Artefacto distribuible validado: `../archives/OCT_Workbench_plugins_math_inside.zip`.
- `OCT_Static_Software` no fue modificado.

Este resultado cierra la etapa de corrección del código y la aceptación
sintética de frontera, pero no constituye todavía una aprobación científica con
archivos OCT reales ni una validación de hardware.

## Alcance congelado y trabajo pendiente

El proyecto queda congelado hasta disponer de mediciones reales. No se deben
iniciar refactors estructurales, nuevas rondas de renombrado ni cambios
funcionales del saver externo durante este intervalo.

### Para reabrir el proyecto

1. Cargar una medición real NPZ/HDF5 producida por `OCT_Static_Software`.
2. Verificar `depth_m`, conversión a `depth_mm`, ventanas, amplitud, `NaN`,
   shapes, cardinalidad, metadata y provenance.
3. Ejecutar roundtrip Workbench → NPZ/HDF5 → Workbench.
4. Probar GUI A/B, filtros, geometría, comparación, perfiles, cortes, B-scan,
   ensamblado, reapertura y exportación.
5. Validar mediciones 2D, Multi-Z/3D y casos con ventanas sin pico.
6. Validar hardware físico cuando esté disponible.
7. Actualizar el veredicto científico-operativo y el ZIP final.

### Deuda diferida, no bloqueante para el congelamiento

- Extracción incremental de `WorkbenchSession`.
- Adelgazamiento de `MainWindow` y separación de renderers.
- Migración de writers de tests para usar exclusivamente `tmp_path`.
- Revisión futura de opciones tipadas en plugins GUI.
- Revisión futura de redraws duplicados y controles ante coordenadas totalmente
  `NaN`.
- Fijación completa de versiones en `requirements.txt`.

Cortes e Histograma. Soporta mediciones 2D como un único nivel y
mediciones Multi-Z/3D como niveles físicos navegables. En Cortes, cada fuente
puede seleccionar un plano XY, XZ o YZ sin convertir una nube irregular en un
volumen voxelado artificial. Para todos los mapas, superficies y perfiles X/Y,
los objetos derivados, la calidad visible y la comparación A/B, las transformaciones
conservan proveniencia.
La coordinación A/B es explícita y opt-in: por defecto cada fuente conserva nivel,
ventana, medición, cortes y orientación independientes. La coordinación sólo está
disponible para nivel, ventana y medición; Cortes nunca se sincroniza. Las transformaciones y
máscaras son reversibles y se exportan con proveniencia.
En **Cortes**, los payloads del saver con `profile_mod_wN` o `profile_real_wN` y
`profile_depth_m_wN` se muestran como perfil axial físico; si falta el eje persistido,
la vista informa que no está disponible.
La vista puede cambiar explícitamente a **B-scan espectral** cuando el archivo contiene
`spectra` y `wavelengths_nm`; muestra longitud de onda contra posición X de la línea
seleccionada y permanece no disponible para payloads incompletos.
Topografía y Reflectividad son suficientes para la visualización principal: la primera
representa OPD y la segunda amplitud, sin un modo adicional de mapa doble.
La navegación común de preparación mantiene disponibles **Filtros** y
**Geometría** en todas las pestañas de análisis; cambiar de vista no oculta ni
deshabilita esas herramientas. Cada canvas gráfico incorpora una toolbar de navegación:
la rueda hace zoom centrado en el cursor, **Zoom rect.** permite seleccionar un área,
**Pan/Zoom** desplaza la vista y **Home** restaura la extensión original. En 3D, la
la rueda acerca/aleja la cámara sin transformar las coordenadas físicas ni los datos. La superficie ensamblada 3D usa proyección ortográfica para evitar deformaciones de perspectiva al acercar; el **Zoom rect.** conserva el rango Z y la orientación de la cámara, mientras **Pan/Zoom** permite desplazar la vista y estudiar cada parche por separado.
El nivelado por regiones se aplica de forma reversible sobre el nivel Z activo y conserva proveniencia.
Para construir una **Muestra derivada** desde una misma Muestra/medición, el botón
**Crear Muestra derivada…** permite activar o excluir cada Nivel, definir una región
X/Y y aplicar un `ΔZ` físico por Nivel. El resultado, por ejemplo `Muestra 1*`, se guarda
como NPZ reabrible, conserva huecos como `NaN`, advertencias y proveniencia, y puede
cargarse con **Abrir B…** para compararlo dentro del Workbench. La reconstrucción de
niveles agrupa el jitter de adquisición con la tolerancia física declarada; no expande
una grilla cartesiana artificial cuando se recorta una medición.

Para crear una **superficie compuesta** desde A y B, el botón **Ensamblar superficies…** permite agregar parches, elegir de manera independiente la fuente y el nivel Z, y definir límites X/Y y `ΔZ` por parche. El resultado conserva las mallas nativas, los pasos `X/Y`, las extensiones diferentes, los huecos y la proveniencia de ambas fuentes; no remuestrea ni interpola.

Para crear un paquete distribuible reproducible:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path('.').resolve()
out = root.parent / 'OCT_Workbench_depth_migration.zip'
excluded_dirs = {'.venv', '__pycache__', '.pytest_cache', '.git'}

with ZipFile(out, 'w', ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if not path.is_file():
            continue
        if any(part in excluded_dirs for part in rel.parts):
            continue
        if path.suffix == '.pyc' or path.name.startswith('core'):
            continue
        archive.write(path, Path(root.name) / rel)

print(out)
PY
```

El paquete de esta iteración conserva código, documentación, tests y `test_data/`;
excluye `.venv`, bytecode, `.pytest_cache`, `.git` y volcados `core*`. Los módulos
históricos retirados (`crop.py`, `depth.py`, `geometric.py` y `surface.py`) se
conservan fuera del árbol activo en `../archives/OCT_Workbench_historical_transforms-20260826-194343/`.
El artefacto validado actualmente es `../archives/OCT_Workbench_plugins_math_inside.zip`.

