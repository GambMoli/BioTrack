"""«Liberar espacio en C:»: reúne todo lo que se puede borrar sin riesgo y lo limpia de una vez.

detect()  -> lista de tareas con lo que liberaría cada una (no borra nada).
execute() -> ejecuta una tarea y devuelve los bytes liberados.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import cleaner, winsys
from .fsutil import FILE_ATTRIBUTE_REPARSE_POINT, file_attributes
from .platform_utils import IS_WINDOWS, human_size

GROUPS = ("Recomendado", "Sistema de Windows", "Opcional")
SAY = Callable[[str], None]

CACHE_CATEGORIES_EXCLUDED = {"recycle_bin", "windows_update", "gpu_shaders", "npm", "yarn", "pip", "nuget"}
DEV_CATEGORIES = ("npm", "yarn", "pip", "nuget")
# Carpetas de la carpeta de usuario donde nunca se buscan node_modules: ahí viven programas
# instalados (npm global en AppData, extensiones de VS Code en .vscode…).
NODE_SEARCH_SKIP = {"appdata", "$recycle.bin", "library", "application data", "ntuser"}


@dataclass
class FreeTask:
    id: str
    group: str
    name: str
    description: str
    needs_admin: bool = False
    default_on: bool = True
    warning: str = ""
    slow: bool = False
    estimate: Optional[int] = None   # bytes que se liberarían (None = se sabe al terminar)
    note: str = ""
    payload: list = field(default_factory=list)


@dataclass
class NodeModulesDir:
    path: str
    size: int
    last_activity: float

    @property
    def project(self) -> str:
        return os.path.basename(os.path.dirname(self.path))


def free_bytes(drive: Optional[str] = None) -> int:
    return shutil.disk_usage(drive or winsys.system_drive()).free


# --------------------------------------------------------------------------- #
# node_modules de proyectos abandonados
# --------------------------------------------------------------------------- #
def default_dev_root() -> str:
    return os.path.expanduser("~")


def _is_link_dir(entry: os.DirEntry) -> bool:
    try:
        if entry.is_symlink():
            return True
        return bool(file_attributes(entry.stat(follow_symlinks=False)) & FILE_ATTRIBUTE_REPARSE_POINT) \
            if IS_WINDOWS else False
    except OSError:
        return True


def find_old_node_modules(root: str, min_age_days: float = 30, cancel: Optional[threading.Event] = None,
                          say: Optional[SAY] = None) -> list[NodeModulesDir]:
    """node_modules de proyectos (con package.json) que no se tocan desde hace `min_age_days`."""
    found: list[NodeModulesDir] = []
    limit = time.time() - min_age_days * 86400
    stack = [root]
    while stack:
        if cancel is not None and cancel.is_set():
            break
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = list(iterator)
        except OSError:
            continue
        names = {e.name.lower() for e in entries}
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False) or _is_link_dir(entry):
                    continue
            except OSError:
                continue
            lowered = entry.name.lower()
            if lowered == "node_modules":
                if "package.json" in names:
                    last = _last_activity(entries)
                    if last < limit:
                        if say:
                            say(f"Midiendo node_modules de «{os.path.basename(current)}»…")
                        found.append(NodeModulesDir(entry.path, winsys.folder_size(entry.path), last))
                continue  # nunca se busca dentro de un node_modules
            if lowered.startswith(".") or lowered in NODE_SEARCH_SKIP:
                continue
            stack.append(entry.path)
    found.sort(key=lambda n: n.size, reverse=True)
    return found


def _last_activity(entries: list) -> float:
    """Última modificación de lo que hay en la carpeta del proyecto (sin contar node_modules)."""
    newest = 0.0
    for entry in entries:
        if entry.name.lower() == "node_modules":
            continue
        try:
            newest = max(newest, entry.stat(follow_symlinks=False).st_mtime)
        except OSError:
            continue
    return newest


# --------------------------------------------------------------------------- #
# Detección
# --------------------------------------------------------------------------- #
def _scan(categories: list, cancel) -> list:
    return [(c, cleaner.scan_category(c, cancel=cancel)) for c in categories]


def _top_note(scans: list, limit: int = 3) -> str:
    parts = sorted(((s.size, c.name) for c, s in scans if s.size), reverse=True)[:limit]
    return ", ".join(f"{name}: {human_size(size)}" for size, name in parts)


def detect(admin: bool, *, dev_root: Optional[str] = None, cancel: Optional[threading.Event] = None,
           say: Optional[SAY] = None) -> list[FreeTask]:
    """Qué se puede liberar y cuánto (no borra nada)."""
    say = say or (lambda _text: None)
    tasks: list[FreeTask] = []
    categories = {c.id: c for c in cleaner.available_categories()}

    say("Buscando temporales y cachés…")
    caches = [c for cid, c in categories.items() if c.kind == "files" and c.default_on
              and cid not in CACHE_CATEGORIES_EXCLUDED and (admin or not c.needs_admin)]
    scans = _scan(caches, cancel)
    note = _top_note(scans)
    if not admin and IS_WINDOWS and any(c.needs_admin for c in categories.values() if c.default_on):
        note = (note + ". " if note else "") + "Como administrador también se limpian los temporales de Windows."
    tasks.append(FreeTask(
        "caches", "Recomendado", "Temporales y cachés",
        "Temporales de Windows y de tus programas, cachés de navegadores (no historial ni contraseñas), "
        "miniaturas e informes de errores. Se vuelven a crear solos.",
        estimate=sum(s.size for _, s in scans), note=note, payload=scans))

    if "recycle_bin" in categories:
        say("Mirando la papelera…")
        scans = _scan([categories["recycle_bin"]], cancel)
        tasks.append(FreeTask(
            "recycle_bin", "Recomendado", "Vaciar la papelera de reciclaje",
            "Lo que ya borraste sigue ocupando espacio hasta que vacías la papelera.",
            warning="Lo que haya en la papelera se borrará para siempre.",
            estimate=scans[0][1].size, payload=scans))

    if IS_WINDOWS:
        _detect_windows(tasks, categories, admin, cancel, say)

    dev = [categories[cid] for cid in DEV_CATEGORIES if cid in categories]
    if dev:
        say("Mirando cachés de programación…")
        scans = _scan(dev, cancel)
        tasks.append(FreeTask(
            "dev_caches", "Opcional", "Cachés de programación (npm, Yarn, pip, NuGet)",
            "Paquetes descargados que se vuelven a bajar solos la próxima vez que instales algo.",
            default_on=False, estimate=sum(s.size for _, s in scans), note=_top_note(scans), payload=scans))

    say("Buscando node_modules de proyectos olvidados…")
    projects = find_old_node_modules(dev_root or default_dev_root(), cancel=cancel, say=say)
    if projects:
        names = ", ".join(p.project for p in projects[:4]) + ("…" if len(projects) > 4 else "")
        tasks.append(FreeTask(
            "node_modules", "Opcional",
            f"node_modules de {len(projects)} proyecto{'s' if len(projects) != 1 else ''} sin tocar hace más de 30 días",
            "Las dependencias se recuperan con «npm install» cuando vuelvas al proyecto. Tu código no se toca.",
            default_on=False, estimate=sum(p.size for p in projects), note=names, payload=projects))

    if "gpu_shaders" in categories:
        scans = _scan([categories["gpu_shaders"]], cancel)
        tasks.append(FreeTask(
            "gpu_shaders", "Opcional", "Caché de sombreadores de la GPU",
            "DirectX, NVIDIA y AMD la vuelven a generar.",
            default_on=False, warning="Los juegos pueden tardar un poco más en cargar la primera vez.",
            estimate=scans[0][1].size, payload=scans))
    return tasks


def _detect_windows(tasks, categories, admin, cancel, say) -> None:
    drive = winsys.system_drive()
    if "windows_update" in categories:
        scans = _scan([categories["windows_update"]], cancel) if admin else []
        tasks.append(FreeTask(
            "windows_update", "Sistema de Windows", "Descargas de Windows Update",
            "Instaladores de actualizaciones que ya se aplicaron.", needs_admin=True,
            estimate=scans[0][1].size if scans else None, payload=scans))

    size = winsys.hibernation_file_size(drive)
    if size:
        laptop = winsys.has_battery()
        tasks.append(FreeTask(
            "hibernation", "Sistema de Windows", "Archivo de hibernación (hiberfil.sys)",
            "Desactiva la hibernación y el «inicio rápido». El PC se apaga y enciende igual; solo el arranque "
            "desde apagado tarda unos segundos más. Se puede volver a activar con «powercfg /hibernate on».",
            needs_admin=True, default_on=not laptop, estimate=size,
            warning="En un portátil, la hibernación guarda tu trabajo si se agota la batería." if laptop else ""))

    say("Midiendo restos de Windows (versiones anteriores, instalaciones)…")
    leftovers, notes, has_old = winsys.windows_leftovers(drive)
    tasks.append(FreeTask(
        "windows_cleanup", "Sistema de Windows", "Restos de Windows y de actualizaciones",
        "Usa el Liberador de espacio de Windows en modo «archivos del sistema»: versión anterior de Windows, "
        "actualizaciones ya sustituidas, Optimización de distribución, registros de instalación… "
        "Verás su ventana de progreso.",
        needs_admin=True, slow=True, estimate=leftovers or None,
        note="; ".join(notes) if notes else "El resto se calcula al terminar.",
        warning="Después ya no podrás volver a tu versión anterior de Windows." if has_old else ""))

    tasks.append(FreeTask(
        "components", "Sistema de Windows", "Componentes antiguos de Windows (DISM)",
        "La limpieza oficial de Microsoft para la carpeta WinSxS. No impide desinstalar actualizaciones.",
        needs_admin=True, slow=True, note="Se calcula al terminar. Puede tardar 5-20 minutos."))

    if admin:
        say("Mirando puntos de restauración…")
        shadows = winsys.shadow_copies(drive)
        if shadows and shadows[0] > 1:
            count, used = shadows
            tasks.append(FreeTask(
                "restore_points", "Sistema de Windows", "Puntos de restauración antiguos",
                f"Tienes {count} puntos de restauración. Se borran todos menos el más reciente.",
                needs_admin=True, estimate=used * (count - 1) // count))
        if winsys.reserved_storage_enabled():
            tasks.append(FreeTask(
                "reserved_storage", "Opcional", "Almacenamiento reservado de Windows",
                "Windows aparta unos 7 GB para que las actualizaciones siempre tengan sitio.",
                needs_admin=True, default_on=False, note="Unos 7 GB.",
                warning="Si el disco se llena, alguna actualización de Windows podría fallar."))
    else:
        tasks.append(FreeTask(
            "restore_points", "Sistema de Windows", "Puntos de restauración antiguos",
            "Se borran todos menos el más reciente.", needs_admin=True,
            note="Abre LimpiaPC como administrador para ver cuánto ocupan."))

    tasks.append(FreeTask(
        "compact_os", "Opcional", "Comprimir los archivos de Windows (CompactOS)",
        "Herramienta oficial de Microsoft: Windows ocupa 2-5 GB menos y en un PC moderno casi no se nota.",
        needs_admin=True, default_on=False, slow=True, note="Unos 2-5 GB. Tarda 10-20 minutos."))


# --------------------------------------------------------------------------- #
# Ejecución
# --------------------------------------------------------------------------- #
ORDER = ("caches", "recycle_bin", "windows_update", "dev_caches", "node_modules", "gpu_shaders",
         "hibernation", "restore_points", "reserved_storage", "windows_cleanup", "components", "compact_os")


@dataclass
class TaskResult:
    task_id: str
    freed: int = 0
    skipped: int = 0
    error: str = ""
    reboot: bool = False             # hecho, pero Windows termina de liberar al reiniciar


def _clean_scans(scans: list, cancel) -> TaskResult:
    result = TaskResult("")
    for category, scan in scans:
        if cancel is not None and cancel.is_set():
            break
        outcome = cleaner.clean_category(category, scan, cancel=cancel)
        result.freed += outcome.freed
        result.skipped += outcome.skipped
        if outcome.error:
            result.error = outcome.error
    return result


def _clean_node_modules(projects: list, cancel) -> TaskResult:
    result = TaskResult("")
    for project in projects:
        if cancel is not None and cancel.is_set():
            break
        category = cleaner.Category("node_modules", "Opcional", project.project, "",
                                    (cleaner.Target(project.path, remove_empty_dirs=True),))
        outcome = cleaner.clean_category(category, cleaner.scan_category(category, cancel=cancel), cancel=cancel)
        result.freed += outcome.freed
        result.skipped += outcome.skipped
        try:
            os.rmdir(project.path)  # solo si quedó vacía
        except OSError:
            pass
    return result


def execute(task: FreeTask, *, cancel: Optional[threading.Event] = None,
            say: Optional[SAY] = None) -> TaskResult:
    """Ejecuta una tarea. Para las de Windows, lo liberado se mide con el espacio libre de C:."""
    say = say or (lambda _text: None)
    if task.id in ("caches", "recycle_bin", "windows_update", "dev_caches", "gpu_shaders"):
        result = _clean_scans(task.payload, cancel)
    elif task.id == "node_modules":
        result = _clean_node_modules(task.payload, cancel)
    else:
        result = _execute_windows(task, say)
    result.task_id = task.id
    return result


def _execute_windows(task: FreeTask, say: SAY) -> TaskResult:
    result = TaskResult(task.id)
    if not IS_WINDOWS:
        result.error = "Solo disponible en Windows."
        return result
    before = free_bytes()
    if task.id == "hibernation":
        code, output = winsys.disable_hibernation()
    elif task.id == "restore_points":
        code, output = winsys.delete_old_shadow_copies()
    elif task.id == "reserved_storage":
        code, output = winsys.disable_reserved_storage()
    elif task.id == "windows_cleanup":
        say("Liberador de espacio de Windows en marcha (mira su ventana)…")
        code, output = winsys.run_disk_cleanup(), ""
    elif task.id == "components":
        code, output = winsys.component_cleanup(lambda pct: say(f"Limpiando componentes de Windows… {pct}")), ""
    elif task.id == "compact_os":
        say("Comprimiendo Windows… (tarda un rato)")
        code, output = winsys.compact_os()
    else:
        result.error = "Tarea desconocida."
        return result
    result.freed = max(0, free_bytes() - before)
    if code == 3010:  # ERROR_SUCCESS_REBOOT_REQUIRED
        code, result.reboot = 0, True
    if task.id in ("windows_cleanup", "components") and code == 0:
        result.reboot = True  # parte del espacio se libera al reiniciar
    if task.id == "hibernation" and code == 0:
        result.freed = max(result.freed, task.estimate or 0)
    if code != 0:
        last_line = output.strip().splitlines()[-1] if output.strip() else ""
        result.error = f"terminó con el código {code}" + (f": {last_line[:120]}" if last_line else "")
    return result
