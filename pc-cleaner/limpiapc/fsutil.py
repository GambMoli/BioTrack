"""Recorrido seguro de carpetas.

Nunca entra en enlaces simbólicos ni en "junctions" de Windows: así una limpieza
no puede salirse de la carpeta que se está limpiando.
"""

from __future__ import annotations

import os
import stat
import threading
from typing import Callable, Iterator, Optional

IS_WINDOWS = os.name == "nt"

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003  # junction
IO_REPARSE_TAG_SYMLINK = 0xA000000C

ErrorFn = Optional[Callable[[str], None]]
SkipDirFn = Optional[Callable[[str, str], bool]]


def file_attributes(st: os.stat_result) -> int:
    return getattr(st, "st_file_attributes", 0)


def is_cloud_placeholder(st: os.stat_result) -> bool:
    """Archivos de OneDrive "solo en línea": no ocupan disco y leerlos los descarga."""
    return bool(
        file_attributes(st)
        & (FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)
    )


def _is_link_dir(entry: os.DirEntry, st: os.stat_result, strict: bool) -> bool:
    if entry.is_symlink():
        return True
    if IS_WINDOWS and file_attributes(st) & FILE_ATTRIBUTE_REPARSE_POINT:
        if strict:
            return True
        tag = getattr(st, "st_reparse_tag", None)
        if tag is None:
            return True
        return tag in (IO_REPARSE_TAG_MOUNT_POINT, IO_REPARSE_TAG_SYMLINK)
    return False


def walk_files(
    root: str,
    *,
    recursive: bool = True,
    strict: bool = True,
    cancel: Optional[threading.Event] = None,
    on_error: ErrorFn = None,
    skip_dir: SkipDirFn = None,
) -> Iterator[tuple[str, os.stat_result]]:
    """Devuelve (ruta, stat) de cada archivo normal bajo `root`.

    strict=True  -> ignora cualquier punto de reanálisis de Windows (para borrar).
    strict=False -> solo ignora enlaces y junctions (para buscar archivos grandes).
    """
    stack = [root]
    while stack:
        if cancel is not None and cancel.is_set():
            return
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = list(iterator)
        except OSError:
            if on_error:
                on_error(current)
            continue
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                if on_error:
                    on_error(entry.path)
                continue
            mode = st.st_mode
            if stat.S_ISDIR(mode):
                if not recursive or _is_link_dir(entry, st, strict):
                    continue
                if skip_dir is not None and skip_dir(entry.path, entry.name):
                    continue
                stack.append(entry.path)
            elif stat.S_ISREG(mode):
                if strict and IS_WINDOWS and file_attributes(st) & FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                yield entry.path, st
            # Enlaces simbólicos, sockets, dispositivos...: se ignoran.
