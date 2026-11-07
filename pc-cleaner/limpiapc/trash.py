"""Papelera de reciclaje: consultar, vaciar y enviar archivos a ella."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.parse
from datetime import datetime
from typing import Optional

from .platform_utils import IS_MAC, IS_WINDOWS

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    class _SHQUERYRBINFO(ctypes.Structure):
        # En 32 bits la estructura está empaquetada a 1 byte.
        _pack_ = 1 if ctypes.sizeof(ctypes.c_void_p) == 4 else 8
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("i64Size", ctypes.c_longlong),
            ("i64NumItems", ctypes.c_longlong),
        ]

    class _SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    _FO_DELETE = 0x3
    _FOF_SILENT = 0x4
    _FOF_NOCONFIRMATION = 0x10
    _FOF_ALLOWUNDO = 0x40
    _FOF_NOERRORUI = 0x400
    _FOF_WANTNUKEWARNING = 0x4000  # avisa si el archivo no cabe en la papelera
    _SHERB_FLAGS = 0x1 | 0x2 | 0x4  # sin confirmación, sin barra de progreso, sin sonido
    _E_UNEXPECTED = 0x8000FFFF  # devuelto cuando la papelera ya está vacía


def recycle_bin_supported() -> bool:
    return IS_WINDOWS


def recycle_bin_info(drive: Optional[str] = None) -> Optional[tuple[int, int]]:
    """(bytes, nº de elementos) de la papelera de Windows, o None si no se puede saber."""
    if not IS_WINDOWS:
        return None
    try:
        info = _SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(info)
        hr = ctypes.windll.shell32.SHQueryRecycleBinW(drive, ctypes.byref(info))
        if hr != 0:
            return None
        return int(info.i64Size), int(info.i64NumItems)
    except Exception:
        return None


def empty_recycle_bin(drive: Optional[str] = None) -> tuple[bool, str]:
    if not IS_WINDOWS:
        return False, "Solo disponible en Windows."
    try:
        hr = ctypes.windll.shell32.SHEmptyRecycleBinW(None, drive, _SHERB_FLAGS)
    except Exception as exc:  # pragma: no cover - depende de Windows
        return False, str(exc)
    if hr == 0 or (hr & 0xFFFFFFFF) == _E_UNEXPECTED:
        return True, ""
    return False, f"Windows devolvió el código 0x{hr & 0xFFFFFFFF:08X}."


def send_to_trash(path: str) -> None:
    """Envía un archivo a la papelera (se puede recuperar). Lanza OSError si falla."""
    path = os.path.abspath(path)
    if not os.path.lexists(path):
        raise FileNotFoundError(path)
    if IS_WINDOWS:
        _windows_send_to_trash(path)
    elif IS_MAC:
        _move_to_trash_dir(path, os.path.expanduser("~/.Trash"))
    else:
        _freedesktop_send_to_trash(path)


def _windows_send_to_trash(path: str) -> None:
    op = _SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = _FO_DELETE
    op.pFrom = path + "\0"  # la lista debe terminar en doble carácter nulo
    op.pTo = None
    op.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_WANTNUKEWARNING | _FOF_SILENT
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if result != 0:
        raise OSError(f"Windows no pudo enviar el archivo a la papelera (código {result}).")
    if op.fAnyOperationsAborted:
        raise OSError("Operación cancelada.")
    if os.path.lexists(path):
        raise OSError("El archivo sigue en su sitio (¿está en uso?).")


def _unique_name(directory: str, name: str) -> str:
    base, ext = os.path.splitext(name)
    candidate, n = name, 1
    while os.path.lexists(os.path.join(directory, candidate)):
        n += 1
        candidate = f"{base} {n}{ext}"
    return candidate


def _move_to_trash_dir(path: str, trash_dir: str) -> str:
    os.makedirs(trash_dir, exist_ok=True)
    name = _unique_name(trash_dir, os.path.basename(path))
    shutil.move(path, os.path.join(trash_dir, name))
    return name


def _freedesktop_send_to_trash(path: str) -> None:
    if shutil.which("gio") and not os.environ.get("LIMPIAPC_NO_GIO"):
        result = subprocess.run(["gio", "trash", path], capture_output=True)
        if result.returncode == 0:
            return
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    trash = os.path.join(data_home, "Trash")
    files_dir, info_dir = os.path.join(trash, "files"), os.path.join(trash, "info")
    os.makedirs(files_dir, exist_ok=True)
    os.makedirs(info_dir, exist_ok=True)
    name = _unique_name(files_dir, os.path.basename(path))
    while os.path.exists(os.path.join(info_dir, name + ".trashinfo")):
        name = _unique_name(files_dir, f"{time.time_ns()}-{name}")
    info = (
        "[Trash Info]\n"
        f"Path={urllib.parse.quote(path)}\n"
        f"DeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n"
    )
    info_path = os.path.join(info_dir, name + ".trashinfo")
    with open(info_path, "w", encoding="utf-8") as fh:
        fh.write(info)
    try:
        shutil.move(path, os.path.join(files_dir, name))
    except OSError:
        os.remove(info_path)
        raise
