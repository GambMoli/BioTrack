# LimpiaPC para Windows

Programa para **liberar espacio en C:, ver qué ocupa tu disco y organizar tus archivos**.
Sin publicidad, sin instalar nada raro y sin enviar datos a ningún sitio.

## Crear el `.exe`

1. Instala Python 3.9 o superior desde <https://www.python.org/downloads/>
   (en el instalador marca **"Add python.exe to PATH"**).
2. Descarga esta carpeta (`pc-cleaner`).
3. Doble clic en **`crear_exe.bat`**.

El `.bat` prepara un entorno aislado (no toca tu Python), instala PyInstaller, comprueba que la
app abre bien (verás la ventana unos segundos) y crea **`dist\LimpiaPC.exe`**: un solo archivo
que funciona sin Python y que puedes copiar donde quieras.

- Al abrirlo pide **permisos de administrador**: los necesita para limpiar lo del sistema.
- La primera vez Windows SmartScreen puede avisar porque no está firmado:
  **«Más información» → «Ejecutar de todas formas»**.

¿Sin crear el `.exe`? Doble clic en **`LimpiaPC.pyw`** (o en `Abrir LimpiaPC.bat`); para lo del
sistema pulsa «Abrir como administrador» en la barra lateral.

## Qué hace

### Liberar espacio en C: (pantalla principal)

Al abrirse analiza todo lo que se puede borrar sin riesgo y lo limpia **con un solo botón**:

| Qué | Cuánto suele ocupar | Por defecto |
|---|---|---|
| Temporales y cachés (Windows, navegadores, Discord, VS Code, Steam, miniaturas, informes de errores) | 1-10 GB | ✅ |
| Papelera de reciclaje | lo que tengas | ✅ |
| Descargas de Windows Update | 0,5-5 GB | ✅ |
| **Archivo de hibernación** (`hiberfil.sys`) | 40-75 % de tu RAM (6-25 GB) | ✅ en sobremesa, ❌ en portátil |
| **Restos de Windows**: versión anterior (`Windows.old`), actualizaciones ya sustituidas, Optimización de distribución, registros de instalación (con el Liberador de espacio oficial de Windows) | 5-30 GB | ✅ |
| **Componentes antiguos de Windows** (DISM, carpeta WinSxS) | 1-5 GB | ✅ |
| **Puntos de restauración antiguos** (se conserva el más reciente) | 2-20 GB | ✅ |
| Cachés de programación (npm, Yarn, pip, NuGet) | 1-10 GB | ❌ |
| `node_modules` de proyectos sin tocar hace más de 30 días | 0,2-1 GB por proyecto | ❌ |
| Almacenamiento reservado de Windows | ~7 GB | ❌ |
| Comprimir Windows (CompactOS) | 2-5 GB | ❌ |
| Caché de sombreadores de la GPU | 0,1-2 GB | ❌ |

Al terminar te dice cuánto espacio libre ganó C: (medido de verdad, antes y después).

### Las demás pantallas

| Pantalla | Para qué sirve |
|---|---|
| **Análisis de espacio** | Qué carpetas pesan más (árbol con barras), reparto por tipo (vídeos, fotos, juegos, instaladores, AppData…) y los 1000 archivos más grandes: abrir, **mover a otro disco** o enviar a la papelera. |
| **Limpieza a medida** | Lo mismo que la limpieza de temporales y cachés, pero eligiendo categoría por categoría. |
| **Organizar** | Ordena Descargas, Escritorio, etc. en subcarpetas por tipo (Imágenes, Vídeos, Documentos, Instaladores…) o por fecha. Enseña la propuesta antes y se puede **deshacer**. |
| **Duplicados** | Archivos repetidos aunque tengan otro nombre (compara el contenido). Deja una copia. |
| **Programas al iniciar** | Activa o desactiva lo que arranca con Windows (igual que el Administrador de tareas). |
| **Estado del PC** | CPU, RAM, discos y los programas que más memoria usan. |
| **Herramientas** | Atajos a herramientas de Windows: desinstalar programas, Sensor de almacenamiento, Optimizar unidades, vaciar DNS, `sfc /scannow`… |

## Seguridad

- **Nada se borra ni se mueve sin enseñártelo antes y pedirte confirmación.**
- Tus documentos, fotos, vídeos y programas no se tocan. Los archivos grandes y duplicados los decides tú
  (y van a la papelera).
- Las tareas de sistema usan las herramientas oficiales de Microsoft: `powercfg`, el Liberador de espacio
  (`cleanmgr`), `DISM` y WMI. Del Liberador de espacio solo se activan opciones de una lista blanca:
  **nunca** la que vacía la carpeta Descargas, ni el Historial de archivos, ni los archivos para
  «Restablecer este PC». Al terminar se borran las marcas que deja en el registro.
- DISM se usa **sin** `/ResetBase`: puedes seguir desinstalando actualizaciones.
- La hibernación se puede volver a activar con `powercfg /hibernate on`.
- La limpieza de temporales respeta los archivos de menos de 24 h, salta los que están en uso y nunca
  sigue enlaces ni «junctions». De los navegadores solo borra la caché.
- **Organizar** no toca subcarpetas, accesos directos, ocultos ni descargas a medias, y no deja organizar
  carpetas de Windows, de programas ni AppData. **Mover** nunca sobrescribe.
- No incluye «limpiador de registro» ni «liberador de RAM»: no aceleran el PC y pueden dar problemas.

## Para desarrolladores

```bat
python -m limpiapc                                 :: ejecutar
python -m limpiapc --selftest                      :: abre todas las pantallas y se cierra (0 = bien)
python -m unittest discover -s tests               :: pruebas (algunas crean enlaces simbólicos:
                                                   ::   en Windows hace falta administrador o modo desarrollador)
python tests\ui_smoke.py %TEMP%\prueba capturas    :: recorrido de la interfaz con datos falsos
```

```
limpiapc/
  freeup.py          «Liberar espacio en C:»: detecta y ejecuta todas las tareas
  winsys.py          hibernación, Liberador de espacio, DISM, puntos de restauración… (Windows)
  analyzer.py        análisis de espacio (árbol de carpetas, tipos, archivos más grandes)
  organizer.py       organizar por tipo/fecha + deshacer
  duplicates.py      duplicados por contenido (tamaño → hash parcial → hash completo)
  cleaner.py         categorías de temporales/cachés y borrado seguro
  fileops.py         mover sin sobrescribir
  filetypes.py       tipos de archivo
  startup.py         programas al iniciar (registro StartupApproved)
  system_info.py     CPU, RAM, discos
  trash.py           papelera de reciclaje
  gui/               interfaz (tkinter): una pantalla por archivo
tests/               pruebas automáticas + recorrido de la interfaz
crear_exe.bat        crea dist\LimpiaPC.exe
```
