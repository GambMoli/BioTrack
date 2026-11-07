"""Utilidades dependientes del sistema operativo (Windows, Linux y macOS)."""

from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
from collections import defaultdict

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"
CREATE_NO_WINDOW = 0x08000000


# --------------------------------------------------------------------------- #
# Formato
# --------------------------------------------------------------------------- #
def human_size(num: float) -> str:
    """Convierte bytes a texto legible usando coma decimal: 1536 -> '1,5 KB'."""
    size = float(num)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} B"
            text = f"{size:.1f}" if abs(size) < 100 else f"{size:.0f}"
            return f"{text.replace('.', ',')} {unit}"
        size /= 1024
    return f"{num} B"  # pragma: no cover


def format_count(value: int) -> str:
    """12345 -> '12.345'."""
    return f"{value:,}".replace(",", ".")


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 60 * 24)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


# --------------------------------------------------------------------------- #
# Procesos y comandos
# --------------------------------------------------------------------------- #
def run_quiet(args: list[str], timeout: float = 20) -> subprocess.CompletedProcess:
    """Ejecuta un comando sin abrir ventana de consola y captura su salida."""
    kwargs = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(args, capture_output=True, timeout=timeout, **kwargs)


def decode_output(data: bytes) -> str:
    if IS_WINDOWS:
        for encoding in ("oem", "mbcs"):
            try:
                return data.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
    return data.decode("utf-8", errors="replace")


def _windows_tasklist() -> list[list[str]]:
    out = decode_output(run_quiet(["tasklist", "/fo", "csv", "/nh"]).stdout)
    return [row for row in csv.reader(io.StringIO(out)) if len(row) >= 5]


def running_process_names() -> set[str]:
    """Nombres (en minúsculas) de los procesos que se están ejecutando."""
    names: set[str] = set()
    try:
        if IS_WINDOWS:
            names.update(row[0].strip().lower() for row in _windows_tasklist())
        elif os.path.isdir("/proc"):
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                try:
                    with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as fh:
                        names.add(fh.read().strip().lower())
                except OSError:
                    continue
        else:
            out = run_quiet(["ps", "-axco", "comm="]).stdout.decode("utf-8", errors="replace")
            names.update(line.strip().lower() for line in out.splitlines() if line.strip())
    except Exception:
        pass
    return names


def top_memory_processes(limit: int = 6) -> list[tuple[str, int, int]]:
    """Programas que más memoria usan: lista de (nombre, bytes, nº de procesos)."""
    usage: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    try:
        if IS_WINDOWS:
            for row in _windows_tasklist():
                digits = "".join(ch for ch in row[4] if ch.isdigit())
                if not digits:
                    continue
                name = row[0].strip()
                usage[name] += int(digits) * 1024
                counts[name] += 1
        elif os.path.isdir("/proc"):
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                name, rss = None, 0
                try:
                    with open(f"/proc/{pid}/status", encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            if line.startswith("Name:"):
                                name = line.split(":", 1)[1].strip()
                            elif line.startswith("VmRSS:"):
                                rss = int(line.split()[1]) * 1024
                                break
                except (OSError, ValueError, IndexError):
                    continue
                if name and rss:
                    usage[name] += rss
                    counts[name] += 1
        else:
            out = run_quiet(["ps", "-axo", "rss=,comm="]).stdout.decode("utf-8", errors="replace")
            for line in out.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    name = os.path.basename(parts[1])
                    usage[name] += int(parts[0]) * 1024
                    counts[name] += 1
    except Exception:
        return []
    ranked = sorted(usage.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [(name, size, counts[name]) for name, size in ranked]


# --------------------------------------------------------------------------- #
# Permisos
# --------------------------------------------------------------------------- #
def is_admin() -> bool:
    if IS_WINDOWS:
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def shell_open(executable: str, params: str = "") -> bool:
    """Abre un programa como lo haría el Explorador (muestra UAC si el programa lo pide)."""
    if not IS_WINDOWS:
        subprocess.Popen([executable] + ([params] if params else []))
        return True
    import ctypes

    result = ctypes.windll.shell32.ShellExecuteW(None, "open", executable, params or None, None, 1)
    return int(result) > 32


def run_elevated(executable: str, params: str = "", workdir: str | None = None) -> bool:
    """Lanza un programa pidiendo permisos de administrador (UAC). Solo Windows."""
    if not IS_WINDOWS:
        return False
    import ctypes

    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, workdir, 1)
    return int(result) > 32


def relaunch_as_admin() -> bool:
    """Vuelve a abrir LimpiaPC como administrador. Devuelve True si se lanzó."""
    if not IS_WINDOWS:
        return False
    if getattr(sys, "frozen", False):  # .exe creado con PyInstaller
        return run_elevated(sys.executable, "", os.path.dirname(sys.executable))
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        windowless = exe[: -len("python.exe")] + "pythonw.exe"
        if os.path.exists(windowless):
            exe = windowless
    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return run_elevated(exe, subprocess.list2cmdline(["-m", "limpiapc"]), package_parent)


# --------------------------------------------------------------------------- #
# Abrir archivos y carpetas
# --------------------------------------------------------------------------- #
def open_target(target: str) -> None:
    """Abre un archivo, carpeta o URI (p. ej. 'ms-settings:storagesense')."""
    if IS_WINDOWS:
        os.startfile(target)  # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])


def reveal_in_file_manager(path: str) -> None:
    """Abre el explorador de archivos con el archivo seleccionado."""
    path = os.path.normpath(path)
    if IS_WINDOWS:
        subprocess.Popen(["explorer", "/select,", path])
    elif IS_MAC:
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])
