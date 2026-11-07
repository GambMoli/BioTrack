# LimpiaPC

App de escritorio para **limpiar y optimizar tu PC con Windows** de forma segura.
Hecha en Python con la librería estándar (tkinter): no instala nada raro, no tiene
publicidad y no envía datos a ningún sitio.

## Qué hace

| Pantalla | Para qué sirve |
|---|---|
| **Resumen** | Uso de CPU y RAM en tiempo real, espacio libre de cada disco y qué programas consumen más memoria. |
| **Limpieza** | Analiza y borra temporales y cachés: Windows (Temp, miniaturas, informes de errores, Windows Update, papelera), navegadores (Chrome, Edge, Brave, Vivaldi, Opera, Firefox), apps (Discord, VS Code, Steam) y cachés de desarrollo (npm, Yarn, pip, NuGet). |
| **Archivos grandes** | Busca los archivos que más ocupan en la carpeta que elijas y los manda a la **papelera** (recuperables). |
| **Programas al iniciar** | Habilita o deshabilita programas que arrancan con Windows, igual que el Administrador de tareas (reversible). |
| **Herramientas** | Accesos directos a herramientas oficiales de Windows: desinstalar programas, Liberador de espacio, Sensor de almacenamiento, Optimizar unidades, vaciar DNS, `sfc /scannow`… |

## Cómo usarla

1. Instala Python 3.9 o superior desde <https://www.python.org/downloads/>
   (marca **"Add python.exe to PATH"** durante la instalación).
2. Descarga esta carpeta (`pc-cleaner`).
3. Haz doble clic en **`LimpiaPC.pyw`** (o en **`Abrir LimpiaPC.bat`**).

Para limpiar también las carpetas del sistema (Temp de Windows, Windows Update,
volcados de memoria) pulsa **"Abrir como administrador"** en la barra lateral.

### Crear un `.exe`

Doble clic en **`crear_exe.bat`**. Instala PyInstaller y genera `dist\LimpiaPC.exe`,
un único archivo que funciona sin tener Python instalado.

> Windows SmartScreen puede avisar la primera vez porque el `.exe` no está firmado.

## Seguridad: qué NO hace

- **No toca tus archivos personales.** Solo borra dentro de carpetas conocidas de
  temporales y cachés (lista blanca en `limpiapc/cleaner.py`).
- **No borra historial, contraseñas, cookies ni sesiones** de los navegadores: solo la caché.
- **Respeta los temporales recientes** (menos de 24 h) por si un instalador los está usando.
- **Salta los archivos en uso** sin forzar nada.
- **Nunca sigue enlaces ni "junctions"**, así que no puede salirse de la carpeta que limpia.
- Siempre **analiza primero y pide confirmación** antes de borrar.
- Lo que borras en "Archivos grandes" va a la **papelera**.
- La papelera, Windows Update, la caché de la GPU y las cachés de desarrollo vienen
  **desmarcadas** por defecto.

Tampoco incluye "limpiador de registro" ni "liberador de RAM": no aceleran el equipo
y pueden causar problemas. Lo que de verdad ayuda es desinstalar lo que no usas,
quitar programas del inicio y tener espacio libre en disco.

## Para desarrolladores

```bash
python -m limpiapc                       # ejecutar
python -m unittest discover -s tests     # pruebas
```

Estructura:

```
limpiapc/
  cleaner.py         categorías, análisis y borrado seguro
  fsutil.py          recorrido de carpetas sin seguir enlaces/junctions
  largefiles.py      buscador de archivos grandes
  startup.py         programas al iniciar (registro StartupApproved)
  system_info.py     CPU, RAM, discos, tiempo encendido
  trash.py           papelera de reciclaje (consultar, vaciar, enviar)
  platform_utils.py  utilidades de sistema (admin, procesos, abrir carpetas)
  ui.py              interfaz tkinter
tests/test_core.py   pruebas del motor
```

### Estado de las pruebas

El motor de limpieza, el buscador de archivos grandes y la interfaz se han probado
en Linux (pruebas automáticas y recorrido completo de la interfaz en una pantalla
virtual). El catálogo de rutas de Windows y la lógica del registro de inicio se
prueban con un entorno y un registro simulados. Las llamadas nativas de Windows
(papelera, memoria, CPU, discos y el registro real) **todavía no se han ejecutado
en un Windows real**. Si algo falla, la app muestra el error en lugar de cerrarse.
