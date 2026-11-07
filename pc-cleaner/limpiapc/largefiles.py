"""Buscador de archivos grandes."""

from __future__ import annotations

import heapq
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .cleaner import norm
from .fsutil import is_cloud_placeholder, walk_files
from .platform_utils import IS_WINDOWS

# Carpetas internas del sistema que no tiene sentido (ni es seguro) tocar a mano.
SKIP_DIR_NAMES = {
    "$recycle.bin", "system volume information", "$windows.~bt", "$windows.~ws",
    "$winreagent", "windows.old", "config.msi", "recovery",
}
SKIP_FILE_NAMES = {"pagefile.sys", "hiberfil.sys", "swapfile.sys", "dumpstack.log.tmp"}


@dataclass
class LargeFile:
    path: str
    size: int
    mtime: float

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)


def system_folders() -> list[str]:
    """Carpetas donde borrar a mano puede romper Windows o programas instalados."""
    if not IS_WINDOWS:
        return ["/usr", "/bin", "/sbin", "/lib", "/etc", "/System", "/Applications"]
    names = ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData")
    return [os.environ[n] for n in names if os.environ.get(n)]


def is_system_path(path: str) -> bool:
    key = norm(path)
    for folder in system_folders():
        root = norm(folder)
        if key == root or key.startswith(root.rstrip(os.sep) + os.sep):
            return True
    return False


def find_large_files(
    folder: str,
    min_size: int,
    *,
    limit: int = 500,
    cancel: Optional[threading.Event] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> tuple[list[LargeFile], int]:
    """Los `limit` archivos más grandes (>= min_size) de `folder`, de mayor a menor.

    Devuelve (archivos, nº de archivos revisados).
    """
    windir = norm(os.environ.get("SystemRoot", r"C:\Windows")) if IS_WINDOWS else None

    def skip_dir(path: str, name: str) -> bool:
        if name.lower() in SKIP_DIR_NAMES:
            return True
        return windir is not None and norm(path) == windir

    heap: list[tuple[int, str, float]] = []
    scanned = 0
    last_report = 0.0
    for path, st in walk_files(folder, strict=False, cancel=cancel, skip_dir=skip_dir):
        scanned += 1
        if progress and time.monotonic() - last_report > 0.2:
            last_report = time.monotonic()
            progress(scanned, len(heap))
        if st.st_size < min_size or is_cloud_placeholder(st):
            continue
        if os.path.basename(path).lower() in SKIP_FILE_NAMES:
            continue
        item = (st.st_size, path, st.st_mtime)
        if len(heap) < limit:
            heapq.heappush(heap, item)
        elif item[0] > heap[0][0]:
            heapq.heapreplace(heap, item)
    files = [LargeFile(path, size, mtime) for size, path, mtime in sorted(heap, reverse=True)]
    return files, scanned
