"""Motor de limpieza: qué se puede borrar, cuánto ocupa y cómo borrarlo con seguridad.

Reglas de seguridad:
  * Solo se tocan carpetas conocidas de temporales y cachés (lista blanca).
  * Nunca se entra en enlaces simbólicos ni junctions.
  * Nunca se borra una carpeta "importante" entera (unidad raíz, perfil, Windows...).
  * Los temporales recientes (menos de 24 h) se respetan por si un instalador los usa.
  * Los archivos en uso simplemente se saltan.
"""

from __future__ import annotations

import fnmatch
import glob
import os
import stat
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from . import trash
from .fsutil import walk_files
from .platform_utils import IS_MAC, IS_WINDOWS

ProgressFn = Optional[Callable[[int], None]]
GROUPS = ("Sistema", "Navegadores", "Aplicaciones", "Desarrollo")


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #
def norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def is_within(path: str, root: str) -> bool:
    """True si `path` está dentro de `root` (o es `root`). Ambos ya normalizados."""
    if path == root:
        return True
    prefix = root if root.endswith(os.sep) else root + os.sep
    return path.startswith(prefix)


def _protected_paths() -> list[str]:
    home = os.path.expanduser("~")
    paths = [home, os.path.dirname(home)]
    for sub in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", "OneDrive",
                "Escritorio", "Documentos", "Descargas", "Imágenes", "Música", "Vídeos"):
        paths.append(os.path.join(home, sub))
    if IS_WINDOWS:
        for var in ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                    "ProgramData", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "PUBLIC", "ALLUSERSPROFILE"):
            value = os.environ.get(var)
            if value:
                paths.append(value)
    else:
        paths += ["/", "/home", "/root", "/usr", "/etc", "/var", "/bin", "/sbin", "/lib", "/opt",
                  "/boot", "/srv", "/Users", "/System", "/Library", "/Applications", "/private"]
        for sub in (".cache", ".config", ".local", ".local/share", "Library", "Library/Caches"):
            paths.append(os.path.join(home, sub))
    return paths


def is_protected(path: str) -> bool:
    """Carpetas que jamás se vacían por completo."""
    candidates = {norm(path)}
    try:
        candidates.add(norm(os.path.realpath(path)))
    except OSError:
        pass
    protected = {norm(p) for p in _protected_paths()}
    for candidate in candidates:
        if os.path.dirname(candidate) == candidate or candidate in protected:
            return True
    return False


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Target:
    """Una carpeta (o conjunto de carpetas vía comodín) que se puede vaciar."""

    base: str                         # ruta literal (sin comodines)
    sub: str = ""                     # comodín relativo, p. ej. "*/Cache"
    patterns: tuple = ()              # filtros de nombre de archivo; vacío = todos
    min_age_hours: float = 0.0        # respeta archivos más nuevos que esto
    recursive: bool = True
    remove_empty_dirs: bool = False   # borrar subcarpetas que queden vacías
    owned_only: bool = False          # (Linux/macOS) solo archivos del usuario actual

    @property
    def allows_protected_root(self) -> bool:
        # Ej.: C:\Windows\MEMORY.DMP -> solo un archivo concreto, nunca la carpeta.
        return bool(self.patterns) and not self.recursive

    def roots(self) -> list[str]:
        if not self.base:
            return []
        if self.sub:
            candidates = glob.glob(os.path.join(glob.escape(self.base), self.sub))
        else:
            candidates = [self.base]
        return sorted({os.path.normpath(os.path.abspath(c)) for c in candidates if os.path.isdir(c)})


@dataclass
class Category:
    id: str
    group: str
    name: str
    description: str
    targets: tuple = ()
    kind: str = "files"               # "files" | "recycle_bin"
    needs_admin: bool = False
    default_on: bool = True
    warning: str = ""
    processes: tuple = ()             # programas que conviene cerrar antes

    def iter_roots(self) -> Iterator[tuple[Target, str]]:
        """Carpetas a analizar, sin duplicados ni carpetas anidadas."""
        pairs = [(t, r) for t in self.targets for r in t.roots()]
        pairs.sort(key=lambda pair: len(pair[1]))
        seen: list[str] = []
        for target, root in pairs:
            key = norm(root)
            if any(is_within(key, s) for s in seen):
                continue
            if is_protected(root) and not target.allows_protected_root:
                continue
            seen.append(key)
            yield target, root

    def is_available(self) -> bool:
        if self.kind == "recycle_bin":
            return trash.recycle_bin_supported()
        return any(True for _ in self.iter_roots())


@dataclass
class RootScan:
    root: str
    remove_empty_dirs: bool
    files: list = field(default_factory=list)  # [(ruta, tamaño)]


@dataclass
class ScanResult:
    category_id: str
    size: int = 0
    count: int = 0
    errors: int = 0
    cancelled: bool = False
    roots: list = field(default_factory=list)


@dataclass
class CleanResult:
    category_id: str
    freed: int = 0
    deleted: int = 0
    skipped: int = 0
    error: str = ""


# --------------------------------------------------------------------------- #
# Análisis y limpieza
# --------------------------------------------------------------------------- #
def _matches(name: str, patterns: tuple) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, p.lower()) for p in patterns)


def _newest_time(st: os.stat_result) -> float:
    # En Windows st_ctime es la fecha de creación; en Linux, el último cambio.
    # Un instalador que extrae archivos "viejos" ahora mismo tiene ctime reciente.
    return max(st.st_mtime, st.st_ctime, getattr(st, "st_birthtime", 0) or 0)


def scan_category(
    category: Category,
    cancel: Optional[threading.Event] = None,
    progress: ProgressFn = None,
) -> ScanResult:
    """Calcula qué archivos se borrarían, sin borrar nada."""
    result = ScanResult(category.id)
    if category.kind == "recycle_bin":
        info = trash.recycle_bin_info()
        if info:
            result.size, result.count = info
        return result

    now = time.time()
    last_report = 0.0
    uid = os.getuid() if hasattr(os, "getuid") else None

    def on_error(_path: str) -> None:
        result.errors += 1

    for target, root in category.iter_roots():
        scan = RootScan(root, target.remove_empty_dirs)
        threshold = now - target.min_age_hours * 3600 if target.min_age_hours else None
        for path, st in walk_files(root, recursive=target.recursive, strict=True,
                                   cancel=cancel, on_error=on_error):
            if target.patterns and not _matches(os.path.basename(path), target.patterns):
                continue
            if threshold is not None and _newest_time(st) > threshold:
                continue
            if target.owned_only and uid is not None and st.st_uid != uid:
                continue
            scan.files.append((path, st.st_size))
            result.size += st.st_size
            result.count += 1
            if progress and time.monotonic() - last_report > 0.25:
                last_report = time.monotonic()
                progress(result.count)
        if scan.files:
            result.roots.append(scan)
        if cancel is not None and cancel.is_set():
            result.cancelled = True
            break
    return result


def _delete_file(path: str) -> tuple[str, int]:
    """Devuelve ("ok" | "gone" | "fail", bytes liberados)."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "gone", 0
    except OSError:
        return "fail", 0
    if not stat.S_ISREG(st.st_mode):
        return "fail", 0
    try:
        os.remove(path)
    except FileNotFoundError:
        return "gone", 0
    except PermissionError:
        # Windows no deja borrar archivos de solo lectura: se les quita el atributo.
        if IS_WINDOWS and not st.st_mode & stat.S_IWRITE:
            try:
                os.chmod(path, stat.S_IWRITE)
                os.remove(path)
            except OSError:
                return "fail", 0
        else:
            return "fail", 0
    except OSError:
        return "fail", 0
    return "ok", st.st_size


def _prune_empty_dirs(dirs: set, root: str) -> None:
    root_key = norm(root)
    for directory in sorted(dirs, key=len, reverse=True):
        current = directory
        while True:
            key = norm(current)
            if key == root_key or not is_within(key, root_key):
                break
            try:
                os.rmdir(current)  # solo funciona si está vacía
            except OSError:
                break
            current = os.path.dirname(current)


def clean_category(
    category: Category,
    scan: ScanResult,
    cancel: Optional[threading.Event] = None,
    progress: ProgressFn = None,
) -> CleanResult:
    """Borra los archivos encontrados por `scan_category`."""
    result = CleanResult(category.id)
    if category.kind == "recycle_bin":
        if scan.size == 0 and scan.count == 0:
            return result
        ok, message = trash.empty_recycle_bin()
        if ok:
            result.freed, result.deleted = scan.size, scan.count
        else:
            result.error = message
        return result

    done = 0
    last_report = 0.0
    for root_scan in scan.roots:
        root_key = norm(root_scan.root)
        touched: set = set()
        for path, _size in root_scan.files:
            if cancel is not None and cancel.is_set():
                break
            done += 1
            key = norm(path)
            if key == root_key or not is_within(key, root_key):
                result.skipped += 1
                continue
            status, freed = _delete_file(path)
            if status == "ok":
                result.freed += freed
                result.deleted += 1
                touched.add(os.path.dirname(path))
            elif status == "fail":
                result.skipped += 1
            if progress and time.monotonic() - last_report > 0.1:
                last_report = time.monotonic()
                progress(done)
        if root_scan.remove_empty_dirs and touched:
            _prune_empty_dirs(touched, root_scan.root)
        if cancel is not None and cancel.is_set():
            break
    return result


# --------------------------------------------------------------------------- #
# Catálogo de categorías
# --------------------------------------------------------------------------- #
def _j(base: str, *parts: str) -> str:
    return os.path.join(base, *parts) if base else ""


_CHROMIUM_CACHE_DIRS = (
    "*/Cache", "*/Code Cache", "*/GPUCache", "*/DawnCache", "*/DawnGraphiteCache",
    "*/DawnWebGPUCache", "ShaderCache", "GrShaderCache", "GraphiteDawnCache",
)
_BROWSER_NOTE = "Solo la caché: no se borran historial, contraseñas ni sesiones abiertas."


def _chromium(user_data: str) -> tuple:
    return tuple(Target(user_data, sub) for sub in _CHROMIUM_CACHE_DIRS)


def _subdirs(base: str, *names: str) -> tuple:
    return tuple(Target(_j(base, name)) for name in names)


def _windows_categories() -> list[Category]:
    env = os.environ.get
    local = env("LOCALAPPDATA", "")
    roaming = env("APPDATA", "")
    windir = env("SystemRoot") or env("windir") or r"C:\Windows"
    programdata = env("ProgramData") or r"C:\ProgramData"
    temp = env("TEMP") or tempfile.gettempdir()
    ff_profiles = _j(local, "Mozilla", "Firefox", "Profiles")

    return [
        # ---------------------------- Sistema ----------------------------
        Category("temp_user", "Sistema", "Archivos temporales",
                 "Restos que dejan instaladores y programas en tu carpeta temporal. "
                 "Solo se borran los de hace más de 24 horas.",
                 (Target(temp, min_age_hours=24, remove_empty_dirs=True),)),
        Category("temp_windows", "Sistema", "Temporales de Windows",
                 r"La carpeta temporal del sistema (C:\Windows\Temp). Solo archivos de hace más de 24 horas.",
                 (Target(_j(windir, "Temp"), min_age_hours=24, remove_empty_dirs=True),),
                 needs_admin=True),
        Category("recycle_bin", "Sistema", "Papelera de reciclaje",
                 "Vacía la papelera de todas tus unidades.",
                 kind="recycle_bin", default_on=False,
                 warning="Lo que haya en la papelera se borrará para siempre."),
        Category("thumbnails", "Sistema", "Caché de miniaturas",
                 "Vistas previas de imágenes del Explorador. Windows las vuelve a crear al abrir cada carpeta.",
                 (Target(_j(local, "Microsoft", "Windows", "Explorer"),
                         patterns=("thumbcache_*.db",), recursive=False),)),
        Category("error_reports", "Sistema", "Informes de errores",
                 "Informes de fallos de programas y volcados de memoria de tu usuario.",
                 (Target(_j(local, "CrashDumps")),
                  Target(_j(local, "Microsoft", "Windows", "WER", "ReportArchive")),
                  Target(_j(local, "Microsoft", "Windows", "WER", "ReportQueue")))),
        Category("error_reports_system", "Sistema", "Informes de errores del sistema",
                 "Volcados de memoria de pantallazos azules e informes de error de Windows.",
                 (Target(_j(programdata, "Microsoft", "Windows", "WER", "ReportArchive")),
                  Target(_j(programdata, "Microsoft", "Windows", "WER", "ReportQueue")),
                  Target(_j(windir, "Minidump")),
                  Target(_j(windir, "LiveKernelReports"), patterns=("*.dmp",)),
                  Target(windir, patterns=("MEMORY.DMP",), recursive=False)),
                 needs_admin=True),
        Category("windows_update", "Sistema", "Descargas de Windows Update",
                 "Instaladores de actualizaciones ya descargados. Puede ocupar varios GB.",
                 (Target(_j(windir, "SoftwareDistribution", "Download"), min_age_hours=24,
                         remove_empty_dirs=True),),
                 needs_admin=True, default_on=False,
                 warning="Si hay una actualización pendiente, Windows la volverá a descargar."),
        Category("gpu_shaders", "Sistema", "Caché de sombreadores de la GPU",
                 "Cachés de DirectX, NVIDIA y AMD. Se regeneran solas.",
                 (Target(_j(local, "D3DSCache")),
                  Target(_j(local, "NVIDIA", "DXCache")), Target(_j(local, "NVIDIA", "GLCache")),
                  Target(_j(local, "AMD", "DxCache")), Target(_j(local, "AMD", "DxcCache")),
                  Target(_j(local, "AMD", "GLCache")), Target(_j(local, "AMD", "VkCache"))),
                 default_on=False,
                 warning="Los juegos pueden tardar un poco más en cargar la primera vez."),
        # --------------------------- Navegadores --------------------------
        Category("chrome", "Navegadores", "Google Chrome", _BROWSER_NOTE,
                 _chromium(_j(local, "Google", "Chrome", "User Data")), processes=("chrome.exe",)),
        Category("edge", "Navegadores", "Microsoft Edge", _BROWSER_NOTE,
                 _chromium(_j(local, "Microsoft", "Edge", "User Data")), processes=("msedge.exe",)),
        Category("brave", "Navegadores", "Brave", _BROWSER_NOTE,
                 _chromium(_j(local, "BraveSoftware", "Brave-Browser", "User Data")),
                 processes=("brave.exe",)),
        Category("vivaldi", "Navegadores", "Vivaldi", _BROWSER_NOTE,
                 _chromium(_j(local, "Vivaldi", "User Data")), processes=("vivaldi.exe",)),
        Category("opera", "Navegadores", "Opera", _BROWSER_NOTE,
                 _subdirs(_j(local, "Opera Software", "Opera Stable"), "Cache", "Default/Cache")
                 + _subdirs(_j(local, "Opera Software", "Opera GX Stable"), "Cache", "Default/Cache"),
                 processes=("opera.exe",)),
        Category("firefox", "Navegadores", "Mozilla Firefox", _BROWSER_NOTE,
                 tuple(Target(ff_profiles, sub) for sub in
                       ("*/cache2", "*/startupCache", "*/thumbnails", "*/jumpListCache")),
                 processes=("firefox.exe",)),
        # --------------------------- Aplicaciones -------------------------
        Category("discord", "Aplicaciones", "Discord", "Imágenes y datos en caché de Discord.",
                 _subdirs(_j(roaming, "discord"), "Cache", "Code Cache", "GPUCache"),
                 processes=("discord.exe",)),
        Category("vscode", "Aplicaciones", "Visual Studio Code", "Cachés internas del editor.",
                 _subdirs(_j(roaming, "Code"), "Cache", "CachedData", "Code Cache", "GPUCache",
                          "CachedExtensionVSIXs"),
                 processes=("code.exe",)),
        Category("steam", "Aplicaciones", "Steam", "Caché del navegador integrado de Steam (tienda y comunidad).",
                 (Target(_j(local, "Steam", "htmlcache")),), processes=("steam.exe", "steamwebhelper.exe")),
        # ---------------------------- Desarrollo --------------------------
        Category("npm", "Desarrollo", "Caché de npm",
                 "Paquetes descargados por npm. Se vuelven a bajar cuando hagan falta.",
                 (Target(_j(local, "npm-cache")), Target(_j(roaming, "npm-cache"))), default_on=False),
        Category("yarn", "Desarrollo", "Caché de Yarn", "Paquetes descargados por Yarn.",
                 (Target(_j(local, "Yarn", "Cache")),), default_on=False),
        Category("pip", "Desarrollo", "Caché de pip", "Paquetes de Python descargados por pip.",
                 (Target(_j(local, "pip", "cache")),), default_on=False),
        Category("nuget", "Desarrollo", "Caché HTTP de NuGet", "Descargas temporales de paquetes .NET.",
                 (Target(_j(local, "NuGet", "v3-cache")),), default_on=False),
    ]


def _unix_categories() -> list[Category]:
    home = os.path.expanduser("~")
    xdg_cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache")
    xdg_data = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    caches = os.path.join(home, "Library", "Caches") if IS_MAC else xdg_cache
    temp = tempfile.gettempdir()

    categories = [
        Category("temp_user", "Sistema", "Archivos temporales",
                 "Tus archivos en la carpeta temporal con más de 24 horas.",
                 (Target(temp, min_age_hours=24, remove_empty_dirs=True, owned_only=True),)),
        Category("trash", "Sistema", "Papelera",
                 "Vacía la papelera de tu usuario.",
                 (Target(os.path.join(home, ".Trash") if IS_MAC else os.path.join(xdg_data, "Trash"),
                         remove_empty_dirs=True),),
                 default_on=False, warning="Lo que haya en la papelera se borrará para siempre."),
    ]
    if not IS_MAC:
        categories.append(Category("thumbnails", "Sistema", "Caché de miniaturas",
                                   "Vistas previas de imágenes. Se regeneran solas.",
                                   (Target(os.path.join(xdg_cache, "thumbnails")),)))
    categories += [
        Category("chrome", "Navegadores", "Google Chrome / Chromium", _BROWSER_NOTE,
                 (Target(os.path.join(caches, "google-chrome")), Target(os.path.join(caches, "chromium")),
                  Target(os.path.join(caches, "Google", "Chrome"))),
                 processes=("chrome", "chromium", "google chrome")),
        Category("brave", "Navegadores", "Brave", _BROWSER_NOTE,
                 (Target(os.path.join(caches, "BraveSoftware")),), processes=("brave", "brave browser")),
        Category("firefox", "Navegadores", "Mozilla Firefox", _BROWSER_NOTE,
                 (Target(os.path.join(caches, "mozilla", "firefox")), Target(os.path.join(caches, "Firefox"))),
                 processes=("firefox", "firefox-bin")),
        Category("pip", "Desarrollo", "Caché de pip", "Paquetes de Python descargados por pip.",
                 (Target(os.path.join(caches, "pip")),), default_on=False),
        Category("npm", "Desarrollo", "Caché de npm", "Paquetes descargados por npm.",
                 (Target(os.path.join(home, ".npm", "_cacache")),), default_on=False),
        Category("yarn", "Desarrollo", "Caché de Yarn", "Paquetes descargados por Yarn.",
                 (Target(os.path.join(caches, "yarn")), Target(os.path.join(caches, "Yarn"))),
                 default_on=False),
    ]
    return categories


def build_categories() -> list[Category]:
    return _windows_categories() if IS_WINDOWS else _unix_categories()


def available_categories() -> list[Category]:
    return [c for c in build_categories() if c.is_available()]
