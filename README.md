# OCT Workbench

Aplicación de escritorio en Python para abrir, inspeccionar, visualizar, comparar,
preparar de forma reversible y exportar mediciones OCT ya adquiridas. La adquisición
se realiza en un software externo; Workbench consume archivos NPZ y HDF5.

## Flujo de trabajo

Abrir una medición → inspeccionar sus datos → visualizar → preparar → comparar,
extraer o ensamblar → exportar.

Las seis pestañas de visualización son:

- **Niveles:** navegación y exclusión reversible de niveles físicos Z.
- **Superficie:** representación 3D de OPD. X e Y conservan su proporción física;
  la OPD utiliza una escala vertical independiente para apreciar el relieve.
- **Topografía:** mapa de OPD con coordenadas físicas X/Y.
- **Reflectividad:** mapa de amplitud registrada; no implica una calibración de
  reflectancia absoluta.
- **Cortes:** perfiles X/Y, selección de planos XY/XZ/YZ y, cuando el archivo lo
  permite, perfiles axiales con eje físico o B-scan espectral.
- **Histograma:** distribución de los valores de la vista seleccionada.

A y B son independientes por defecto. La coordinación de nivel, ventana y medición
se activa explícitamente. La diferencia A − B y sus estadísticas usan los puntos
compatibles de ambas fuentes; no se interpola para inventar correspondencias.

## Controles y preparación

La columna izquierda tiene las etapas **Selección**, **Filtros** y **Geometría**.
Las acciones de Selección están ordenadas así:

| Columna izquierda | Columna derecha |
| --- | --- |
| Abrir A | Abrir B |
| Metadata | Cerrar B |
| Exportar | Comparar A − B |
| Crear derivada | Ensamblar |

Los controles numéricos y las etiquetas de los gráficos utilizan punto decimal.
La altura de las tarjetas A/B se recalcula al mostrar la ventana y al cambiar los
controles visibles, para evitar huecos innecesarios en el panel.

Las operaciones de preparación conservan la medición original y pueden deshacerse.
Entre las operaciones integradas están el recorte X/Y, la máscara OPD, la mediana
2D, el nivelado por plano o regiones, los offsets, la inversión de OPD y las
transformaciones geométricas.

- **Máscara OPD:** marca como inválidos los valores fuera del rango, conservando
  la grilla. No es un ajuste del contraste de la imagen.
- **Nivelar plano:** ajusta un plano por mínimos cuadrados a la ventana y medición
  elegidas y calcula `OPD_corregido = OPD_plano − OPD_medido`. Este convenio invierte
  el signo respecto del residuo habitual `medido − plano`.
- **Mediana 2D:** suaviza los datos sobre la malla; su tamaño se expresa en puntos,
  por lo que el área física depende de los pasos X/Y del barrido.
- **Recorte X/Y:** conserva los mismos puntos en coordenadas, OPD, amplitud,
  espectros y perfiles. Los ejes axiales de los perfiles se conservan completos.

No hay filtro gaussiano integrado ni detección automática de marcas de fatiga.
La identificación científica de rasgos requiere evaluar la medición original,
la resolución y las condiciones de adquisición.

## Derivadas y exportación

**Crear derivada** permite seleccionar niveles de una misma medición, definir
regiones X/Y y aplicar un desplazamiento Z por nivel.

**Ensamblar** permite combinar parches de A y B, con fuente, nivel, región X/Y y
posición Z independientes. Se conservan las coordenadas y mallas nativas; no se
remuestrea ni se crea una grilla común implícita.

Se exportan datos a NPZ, HDF5 o CSV y gráficos a PNG, según las opciones de la vista.
Los archivos NPZ/HDF5 usan el contrato Schema 6.0: profundidad persistida en
`depth_m` y normalizada en memoria a `depth_mm`. Los objetos derivados incluyen
información de origen y las operaciones aplicadas.

## Instalación y arranque

En Windows:

1. Instalar Python 3.12.
2. Ejecutar `Instalador.bat` para crear `.venv` e instalar las dependencias.
3. Ejecutar `Setup.bat` para abrir Workbench.

El instalador también puede usar `installers\python-3.12.10-amd64.exe` si ese
instalador local se agrega al proyecto. El paquete no requiere que esté incluido.

Instalación manual desde PowerShell, en la carpeta del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

`requirements.txt` contiene las dependencias de ejecución: NumPy, Matplotlib,
PyQt5, h5py y SciPy. `requirements-dev.txt` incluye las anteriores y agrega pytest
como herramienta opcional de desarrollo. Para usar el programa alcanza con las
dependencias de ejecución.

## Organización del código

| Archivo o carpeta | Responsabilidad |
| --- | --- |
| `main.py` | Lanzador: crea la aplicación Qt y abre la ventana principal |
| `gui/main_window.py` | Ventana principal, controles, gráficos y coordinación de las vistas |
| `gui/` | Ventana principal y componentes de interfaz y presentación |
| `gui/display_state.py` | Estado de visualización y coordinación A/B |
| `gui/metadata.py` | Preparación de metadata y resumen de calidad |
| `gui/level_assembly_dialog.py` | Diálogo para crear derivadas de niveles |
| `gui/surface_assembly_dialog.py` | Diálogo para ensamblar parches A/B |
| `gui/aspect.py` | Proporción X/Y y escala vertical independiente de superficies |
| `model/` | Dataset, grillas y estructuras de niveles y superficies |
| `work_io/` | Carga y normalización de NPZ/HDF5 |
| `transforms/` | Pipeline reversible, contrato y descubrimiento de plugins |
| `extract/` | Perfiles, cortes y objetos derivados |
| `compare/` | Compatibilidad, correspondencia de puntos y comparación A/B |
| `export/` | Escritura de datos y gráficos |
| `assets/` | Recursos gráficos de la interfaz |
| `docs/` | Documentación de diseño y auditorías previas |
| `Barridos Guardados/` | Mediciones de ejemplo incluidas |
| `legacy_converter.py` | Conversor auxiliar de archivos antiguos |

`main.py` permanece en la raíz como punto de entrada y es ejecutado por
`Setup.bat`. La ventana principal vive en `gui/main_window.py` y utiliza los demás
componentes del paquete `gui/`. Las rutas de plugins y recursos se resuelven desde
la ubicación del código, sin depender del directorio desde el que se inicia la
aplicación. Para abrirla manualmente se ejecuta `python main.py`.

## Plugins locales

Para agregar una operación:

1. Copiar `transforms/filters/_plantilla_filtro.py` o
   `transforms/geometry/_plantilla_geometria.py` con un nombre nuevo.
2. Completar el diccionario `PLUGIN` y la función `aplicar`.
3. Reiniciar Workbench para descubrir la operación.

Los módulos cuyo nombre empieza con `_` son plantillas y no se cargan. Los plugins
reciben una fachada `Superficie`; deben respetar formas de arrays, unidades y
metadata. Si modifican amplitud deben declararlo con `"modifica_amplitud": true`.
Si cambian la cantidad de puntos deben declarar `"cambia_numero_puntos": true`
y conservar la correspondencia entre los canales.

## Verificación y límites

Documentación actualizada el **2026-09-30** para la versión corregida.

La compilación del código y las comprobaciones internas de recorte/exportación
NPZ y proporción X/Y han pasado en el entorno de edición. Estos resultados no
constituyen una validación completa de la aplicación en Windows ni del instrumento.
La comprobación visual de PyQt5 y el ciclo completo de exportación HDF5 quedan
pendientes en un entorno con esas dependencias disponibles.

Para comprobar la sintaxis desde la carpeta del proyecto:

```bash
python -m compileall -q main.py compare export extract gui model work_io transforms
```

Las auditorías en `docs/` son registros de etapas anteriores y pueden describir
resultados o decisiones históricas. Este README describe la distribución actual;
no se trasladan a ella los conteos de pruebas de paquetes anteriores.

El software no controla la adquisición ni incorpora calibraciones ópticas no
declaradas, interpolación automática, voxelización, cálculo de rugosidad o análisis
automático de mecanismos de fractura.
