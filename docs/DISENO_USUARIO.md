# OCT Workbench — Diseño desde el usuario
# Referencia principal del proyecto
# 2026-06-21 (documento base; estado de implementación actualizado al 2026-08-10)

> **Estado actual:** la etapa de corrección del código está cerrada y verificada
> con 219 tests. La aceptación sintética del flujo normal del saver externo
> (NPZ/HDF5) y el smoke test GUI también están verificados. La aceptación con
> archivos OCT reales y hardware físico permanece pendiente.

## Principio de diseño

La GUI refleja un flujo de trabajo continuo, no una colección de
herramientas aisladas:

    Abrir → Inspeccionar → Transformar → Extraer → Comparar → Exportar

Cada paso alimenta al siguiente. Los datos fluyen por el pipeline.
En cualquier punto el usuario puede volver atrás, cambiar algo,
y todo lo que sigue se actualiza.

## Concepto central: objetos de trabajo

El Workbench opera sobre objetos de trabajo.
Un objeto de trabajo puede ser:

- Un dataset cargado desde archivo.
- Un dataset transformado (pipeline aplicado).
- Un objeto derivado (perfil, región, corte, subconjunto).

Los objetos derivados son ciudadanos de primera clase.
No son resultados temporales ni intermedios.
El usuario puede:

- Visualizarlos (con la misma calidad que un dataset).
- Transformarlos (aplicar un pipeline propio).
- Compararlos (entre sí o contra datasets).
- Exportarlos (con proveniencia completa).

La proveniencia de cada objeto registra:
de dónde salió, qué transformaciones se aplicaron, cuándo se extrajo.


## 1. ABRIR

### ¿Qué quiere hacer?
Traer una medición al programa.

### ¿Qué pregunta?
- ¿Es el archivo correcto?
- ¿Es la medición que busco?

### ¿Qué necesita ver?
- Nombre, muestra, fecha, tipo, vista previa rápida.

### Estado: RESUELTO


## 2. INSPECCIONAR

### ¿Qué quiere hacer?
Entender qué contiene el archivo antes de trabajar.

### ¿Qué pregunta?
- ¿Qué tipo de medición es?
- ¿Se completó o se abortó?
- ¿Qué configuración se usó?
- ¿Los datos tienen buena calidad?

### ¿Qué necesita ver?
- Clasificación automática.
- Grilla, ventanas, metadata.
- Indicadores de calidad (% NaN, rango de amplitudes).
- Datos disponibles.

### Estado: RESUELTO
La tarjeta de cada dataset muestra validez de OPD/amplitud, puntos finitos,
adquiridos versus esperados y estado completo/incompleto/abortado.


## 3. TRANSFORMAR

### ¿Qué quiere hacer?
Preparar los datos para interpretarlos, sin modificar el archivo.

### Situaciones:
- Topografía inclinada → nivelar por plano o por regiones.
- Eje invertido → invertir OPD o ejes espaciales.
- Orientación incorrecta → espejar, rotar, desplazar o centrar origen.
- Ruido local → mediana 2D secundaria.
- Máscara OPD → conservar la grilla y marcar puntos como `NaN`.
- Probar distintas preparaciones → pipeline reversible.

No se incluyen filtro gaussiano, outliers automáticos, nivelado por media ni `CropOPDRange`.

### ¿Qué necesita?
- Resultado inmediato al aplicar cada transformación.
- Apilar, deshacer, limpiar.
- Saber qué transformaciones están activas.
- Volver a los datos originales en un click.

### Estado: RESUELTO


## 4. EXTRAER

### ¿Qué quiere hacer?
Aislar una parte de los datos para analizarla o compartirla.
La extracción trabaja sobre los datos TRANSFORMADOS.

### Situaciones:
- Zona interesante → extraer región.
- Perfil a una posición → extraer perfil.
- Multi-Z, un nivel → extraer Z-slice.
- Pasar perfil a script externo → extraer + exportar.

### ¿Qué necesita?
- Seleccionar interactivamente (click en el mapa).
- Ver el resultado inmediatamente.
- Lista de objetos extraídos.
- Proveniencia registrada.
- Volver al dataset completo.

### Estado: RESUELTO
Los controles de posición y el click en los mapas seleccionan el corte. La GUI
permite crear perfiles X/Y sobre A o B, conserva cada `DerivedObject` y muestra
su nombre, cantidad de puntos y tipo de proveniencia.


## 5. COMPARAR

### ¿Qué quiere hacer?
Inspeccionar dos mediciones simultáneamente para responder una pregunta.
Comparar NO es solamente calcular A-B.
Muchas veces es simplemente observar ambas al mismo tiempo.

### Caso 1 — Repetibilidad
"¿La medición es reproducible?"
Necesita: mismas escalas, mismos ejes, mismos colores.

### Caso 2 — Antes y después
"¿Qué cambió, dónde y cuánto?"
Necesita: lado a lado, perfiles superpuestos, A-B opcional.

### Caso 3 — Zonas distintas
"¿Son similares estas dos regiones?"
Necesita: inspección visual simultánea, escalas sincronizadas.

### Caso 4 — Configuraciones distintas
"¿Cómo afecta la configuración al resultado?"
Necesita: misma muestra, distintos archivos, lado a lado.

### ¿Qué necesita la GUI?
- Cargar dos fuentes (2 archivos, archivo + derivado, 2 derivados).
- Vista lado a lado.
- Escalas sincronizadas (mismo colormap, mismo rango, mismo zoom).
- Superposición de perfiles.
- Diferencia A-B como OPCIÓN, no como modo único.
- Estadísticas comparativas.

### Estado: RESUELTO / CIERRE DE ALCANCE
Backend y GUI cubren carga A/B independiente, vista lado a lado, escalas y rangos
cromáticos sincronizados, unidades compatibles, inspección visual y diferencia
cuantitativa opcional. Las estadísticas visibles corresponden únicamente a `A − B`;
no se muestran estadísticas individuales de A o B.


## 6. EXPORTAR

### ¿Qué quiere hacer?
Continuar el trabajo en otro programa.

### Situaciones:
- Perfil → procesamiento tabular externo (CSV).
- Región → intercambio con otra herramienta genérica (NPZ).
- Datos → hoja de cálculo o script (CSV).
- Gráfico → informe (PNG).
- Dataset preparado → colega o aplicación compatible (NPZ/HDF5).

### ¿Qué necesita?
- Elegir qué y en qué formato.
- Que conserve unidades, metadata y proveniencia.
- Que un NPZ exportado pueda re-abrirse en el Workbench.

### Estado: RESUELTO
Backend y GUI exportan datasets, derivados e imágenes. El CSV conserva unidades,
metadatos y proveniencia en comentarios; las estadísticas A/B declaran la unidad
OPD.


## 7. NIVELES Y VOLUMEN 2D/3D

La GUI trabaja con un layout físico común:

- Una medición 2D se representa como un volumen con `nz = 1`.
- Una medición Multi-Z/3D se agrupa por coordenadas Z físicas tolerantes.
- A y B pueden tener niveles diferentes; por defecto la navegación permanece independiente.
  La coordinación explícita replica sólo nivel, ventana y medición; Cortes permanece
  independiente en todo momento.
- La pestaña **Niveles** muestra ambos prismas, resalta el nivel activo y permite
  excluir/restaurar niveles de forma reversible.
- Excluir un nivel crea una selección transformada; nunca modifica el archivo
  original.
- OPD, reflectividad, Superficie, Topografía, cortes e histogramas consumen el
  mismo estado de nivel activo.

| **Superficie** | Superficie OPD del nivel seleccionado |
| **Topografía** | OPD aplanado sobre XY con codificación cromática |
| **Reflectividad** | Amplitud de la señal reflejada sobre XY |
| **Cortes** | Perfiles X/Y seleccionados por fuente |
| **Histograma** | Distribución de OPD |

En la barra lateral, A y B mantienen columnas independientes y comparten una
navegación de preparación con tres etapas: **Selección**, **Filtros** y
**Geometría**. La etapa elegida controla el contenido visible y no repite su
título dentro de la tarjeta; las operaciones geométricas se muestran como
controles directos, sin un selector intermedio de **Acción**. La pestaña de análisis no bloquea ni oculta los
filtros o la geometría: esas herramientas permanecen disponibles aunque esté
activa Niveles, Superficie, Topografía, Reflectividad, Cortes o Histograma.
Los selectores de ventana/medición y cortes conservan su semántica por vista;
XZ/YZ sólo aparecen cuando el payload contiene información suficiente; no se
interpola ni voxeliza una nube irregular para fabricar un volumen.

La comparación A/B y los indicadores `OPD válido`, `Amplitud válida` y
`Adquiridos` son metadata. Se consultan mediante **Metadata**, no se repiten en
las columnas de las vistas. Dentro de **Filtros**, OPD, mediana y nivelado por
regiones conservan subtítulos internos para distinguir cada operación, pero no
se agrega otro encabezado exterior redundante.

## Frontera de alcance

El Workbench es un visor, comparador, preparador reversible, extractor, ensamblador
manual y exportador genérico. No incorpora análisis científicos específicos de
muestra, instrumento o aplicación, calibraciones no declaradas, interpolación,
voxelización ni control de adquisición.

## ROADMAP (prioridad definida por el usuario)

### Cerrado en esta iteración
1. Comparación visual A/B real con escalas, rangos y unidades sincronizados.
2. Comparación punto a punto opcional con alineamiento tolerante y diferencia `A − B`.
3. Estadísticas únicamente de la diferencia: puntos comunes, media, STD, PV, RMS y máximo absoluto.
4. Extracción interactiva de perfiles X/Y y objetos derivados con proveniencia.
5. Indicadores de calidad visibles en Metadata sin duplicación en las vistas.
6. Proveniencia y unidades en exportaciones CSV/NPZ/HDF5/PNG.
7. Cortes XZ/YZ condicionados por payload, perfil axial y B-scan espectral en Cortes.
8. Coordinación A/B opt-in y preparación reversible con proveniencia.
9. Nivelado de plano global y desde regiones seleccionadas.
10. Mediana 2D secundaria sólo en Superficie y Topografía.
11. Ensamblado de Niveles de una misma Muestra/medición para crear una Muestra derivada
    guardable, con selección X/Y y `ΔZ` independiente por Nivel.
12. Ensamblado de superficies A/B mediante parches nativos independientes: cada parche
    puede conservar dominios XY, pasos de muestreo, cantidad de puntos y Z físico
    diferentes; no se crea una grilla común ni se interpola implícitamente.
13. Retiro de `CropOPDRange` del producto y del backend.

### Siguiente / aceptación pendiente

La implementación del Workbench, sus regresiones de código y la aceptación
sintética de frontera están cerradas. La siguiente fase no es una
refactorización nominal, sino la aceptación con datos reales:

1. ejecutar aceptación manual con archivos OCT reales: 2D, Multi-Z/3D,
   comparación A/B, cortes, perfiles, B-scan, ensamblado, reapertura y
   exportación;
2. validar hardware físico cuando esté disponible;
3. actualizar el veredicto de auditoría después de esa campaña.

Hasta entonces, el alcance queda congelado: no se agregan funcionalidades, no
se hacen nuevos renombrados globales, no se modifica funcionalmente el saver
externo y no se inicia la extracción de `WorkbenchSession` ni el adelgazamiento
de `MainWindow`.

La deuda diferida para una fase posterior incluye la separación de renderers,
la migración de writers de tests a `tmp_path`, la revisión de opciones tipadas
en plugins GUI, redraws duplicados, controles ante coordenadas totalmente
`NaN` y el fijado completo de versiones de `requirements.txt`.


## Referencias

- Este documento es la REFERENCIA PRINCIPAL del proyecto.
- `docs/CAPACIDADES.md` es la referencia funcional histórica.
- `Visualizador_OCT_V43_Compatible.py` fue una referencia funcional externa y no está incluido en este árbol.
- `saver.py` se menciona sólo como referencia histórica del formato de entrada; el cargador canónico actual es `work_io/loader.py`.
