# LimpiaPC para Windows

Programa para **ver qué ocupa tu PC, organizar tus archivos y limpiarlo** de forma segura.
Sin publicidad, sin instalar nada raro y sin enviar datos a ningún sitio.

## Qué hace

| Pantalla | Para qué sirve |
|---|---|
| **Resumen** | CPU y RAM en tiempo real, espacio libre de cada disco (con botón «¿Qué ocupa?») y los programas que más memoria usan. |
| **Análisis de espacio** | Analiza un disco o carpeta y te enseña **qué carpetas pesan más** (árbol desplegable con barras), **por tipo** (vídeos, fotos, juegos, instaladores, comprimidos, AppData…) y los **1000 archivos más grandes**, que puedes abrir, **mover a otro disco** o enviar a la papelera. |
| **Limpieza** | Borra temporales y cachés: Windows (Temp, miniaturas, informes de errores, Windows Update, papelera), navegadores (Chrome, Edge, Brave, Vivaldi, Opera, Firefox), Discord, VS Code, Steam y cachés de programación (npm, Yarn, pip, NuGet). |
| **Organizar** | Ordena carpetas desordenadas (Descargas, Escritorio…) en subcarpetas **por tipo** (Imágenes, Vídeos, Documentos, Instaladores…) o **por fecha** (2024 › 03 - Marzo). Primero te enseña la propuesta y luego se puede **deshacer**. |
| **Duplicados** | Encuentra archivos repetidos aunque tengan otro nombre (compara el contenido) y deja una sola copia. |
| **Programas al iniciar** | Activa o desactiva lo que arranca con Windows, igual que el Administrador de tareas. |
| **Herramientas** | Atajos a las herramientas oficiales de Windows: desinstalar programas, Liberador de espacio, Sensor de almacenamiento, Optimizar unidades, vaciar DNS, `sfc /scannow`… |

## Cómo conseguirlo

### Opción A: descargar el `.exe` (sin instalar nada)

Cada cambio en esta carpeta se compila y se prueba automáticamente en Windows con GitHub Actions:

1. Abre la pestaña **Actions** del repositorio → **LimpiaPC (Windows)** → la ejecución más reciente con ✅.
2. Abajo, en **Artifacts**, descarga **LimpiaPC-Windows** (hay que tener sesión iniciada en GitHub).
3. Descomprime el `.zip` y abre `LimpiaPC.exe`.

> Windows SmartScreen puede avisar la primera vez porque el programa no está firmado:
> pulsa **«Más información» → «Ejecutar de todas formas»**.

### Opción B: con Python

1. Instala Python 3.9 o superior desde <https://www.python.org/downloads/>
   (marca **"Add python.exe to PATH"**).
2. Descarga esta carpeta (`pc-cleaner`) y haz doble clic en **`LimpiaPC.pyw`**
   (o en **`Abrir LimpiaPC.bat`**). Para crear tu propio `.exe`: **`crear_exe.bat`**.

Para analizar o limpiar carpetas del sistema pulsa **«Abrir como administrador»** en la barra lateral.

## Seguridad

- **Nada se borra ni se mueve sin enseñártelo antes y pedirte confirmación.**
- El análisis de espacio **solo lee**.
- Lo que borras a mano (archivos grandes, duplicados) va a la **papelera**: se puede recuperar.
- **Mover** nunca sobrescribe: si ya existe un archivo con ese nombre se llama «foto (2).jpg».
  Entre discos distintos copia, comprueba la copia y solo entonces borra el original.
- **Organizar** solo mueve archivos sueltos de la carpeta elegida, no toca subcarpetas,
  accesos directos, archivos ocultos ni descargas a medias, y se puede deshacer.
  No deja organizar carpetas de Windows, de programas ni AppData.
- **Limpieza** solo actúa en carpetas conocidas de temporales y cachés, respeta los temporales
  de menos de 24 h, salta los archivos en uso y nunca sigue enlaces ni "junctions".
  De los navegadores solo borra la caché (no historial, contraseñas ni sesiones).
- No incluye «limpiador de registro» ni «liberador de RAM»: no aceleran el PC y pueden dar problemas.

## Para desarrolladores

```bat
python -m limpiapc                                 :: ejecutar
python -m unittest discover -s tests               :: pruebas
python tests\ui_smoke.py %TEMP%\prueba capturas    :: recorrido de la interfaz con datos falsos
```

```
limpiapc/
  analyzer.py        análisis de espacio (árbol de carpetas, tipos, archivos más grandes)
  organizer.py       organizar por tipo/fecha + deshacer
  duplicates.py      duplicados por contenido (tamaño → hash parcial → hash completo)
  cleaner.py         categorías de limpieza y borrado seguro
  fileops.py         mover sin sobrescribir
  filetypes.py       tipos de archivo
  startup.py         programas al iniciar (registro StartupApproved)
  system_info.py     CPU, RAM, discos
  trash.py           papelera de reciclaje
  gui/               interfaz (tkinter): una pantalla por archivo
tests/               pruebas automáticas + recorrido de la interfaz
```

La compilación de Windows está en `.github/workflows/limpiapc-windows.yml`: ejecuta las pruebas,
recorre toda la interfaz con datos de prueba aislados (con capturas), crea `LimpiaPC.exe` y comprueba que arranca.
