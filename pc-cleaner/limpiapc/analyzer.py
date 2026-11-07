"""Análisis de espacio: qué carpetas y qué tipos de archivo ocupan el disco.

Solo lee: nunca modifica nada.
"""

from __future__ import annotations

import heapq
import os
import stat
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .filetypes import DEV_DIRS, FILE_TYPES, GAME_DIRS, SYSTEM_FILES, type_for_extension
from .fsutil import FILE_ATTRIBUTE_REPARSE_POINT, IS_WINDOWS, file_attributes, is_cloud_placeholder
from .fsutil import IO_REPARSE_TAG_MOUNT_POINT, IO_REPARSE_TAG_SYMLINK


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


class DirNode:
    __slots__ = ("path", "name", "parent", "children", "size", "files", "own_size", "own_files",
                 "zone", "denied")

    def __init__(self, path: str, name: str, parent: Optional["DirNode"], zone: Optional[str]):
        self.path = path
        self.name = name
        self.parent = parent
        self.children: list[DirNode] = []
        self.size = 0          # total, incluidas subcarpetas
        self.files = 0
        self.own_size = 0      # solo archivos directamente aquí
        self.own_files = 0
        self.zone = zone       # tipo forzado por la ubicación (juegos, sistema…)
        self.denied = False

    def sorted_children(self) -> list["DirNode"]:
        return sorted(self.children, key=lambda n: n.size, reverse=True)


@dataclass
class FoundFile:
    path: str
    size: int
    mtime: float
    type_id: str

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)


@dataclass
class Analysis:
    root: DirNode
    by_type: dict = field(default_factory=dict)       # id -> [bytes, archivos]
    largest: list = field(default_factory=list)       # FoundFile, de mayor a menor
    total_size: int = 0
    total_files: int = 0
    total_dirs: int = 0
    denied: int = 0
    cancelled: bool = False
    seconds: float = 0.0


def _special_roots() -> tuple[set, set, set]:
    env = os.environ.get
    system, programs, appdata = set(), set(), set()
    if IS_WINDOWS:
        for var in ("SystemRoot",):
            if env(var):
                system.add(_norm(env(var)))
        for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            if env(var):
                programs.add(_norm(env(var)))
                programs.add(_norm(os.path.join(env(var), "WindowsApps")))
        if env("ProgramData"):
            appdata.add(_norm(env("ProgramData")))
    else:
        system.update(_norm(p) for p in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/etc",
                                          "/var", "/proc", "/sys", "/System", "/Library"))
        programs.update(_norm(p) for p in ("/opt", "/Applications", "/snap"))
    return system, programs, appdata


def _skip_dir(entry: os.DirEntry, st: os.stat_result) -> bool:
    """No entrar en enlaces ni junctions (evita contar dos veces la misma carpeta)."""
    if entry.is_symlink():
        return True
    if IS_WINDOWS and file_attributes(st) & FILE_ATTRIBUTE_REPARSE_POINT:
        tag = getattr(st, "st_reparse_tag", None)
        return tag is None or tag in (IO_REPARSE_TAG_MOUNT_POINT, IO_REPARSE_TAG_SYMLINK)
    return False


def analyze(
    folder: str,
    *,
    cancel: Optional[threading.Event] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
    top: int = 1000,
) -> Analysis:
    started = time.monotonic()
    folder = os.path.abspath(folder)
    system_roots, program_roots, appdata_roots = _special_roots()

    def zone_for(path: str, name: str, parent_zone: Optional[str]) -> Optional[str]:
        if parent_zone in ("games", "dev", "system"):
            return parent_zone
        lowered = name.lower()
        if lowered in GAME_DIRS:
            return "games"
        if lowered in DEV_DIRS:
            return "dev"
        key = _norm(path)
        if key in system_roots:
            return "system"
        if lowered == "$recycle.bin" or lowered == "system volume information":
            return "system"
        if key in program_roots:
            return "programs"
        if lowered == "appdata" or key in appdata_roots:
            return "appdata"
        return parent_zone

    root_name = os.path.basename(folder.rstrip("\\/")) or folder
    root = DirNode(folder, root_name, None, zone_for(folder, root_name, None))
    analysis = Analysis(root, {t.id: [0, 0] for t in FILE_TYPES})
    nodes = [root]
    heap: list[tuple[int, str, float, str]] = []
    last_report = 0.0

    stack = [root]
    while stack:
        if cancel is not None and cancel.is_set():
            analysis.cancelled = True
            break
        node = stack.pop()
        try:
            with os.scandir(node.path) as iterator:
                entries = list(iterator)
        except OSError:
            node.denied = True
            analysis.denied += 1
            continue
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            mode = st.st_mode
            if stat.S_ISDIR(mode):
                if _skip_dir(entry, st):
                    continue
                child = DirNode(entry.path, entry.name, node, zone_for(entry.path, entry.name, node.zone))
                node.children.append(child)
                nodes.append(child)
                stack.append(child)
            elif stat.S_ISREG(mode):
                if is_cloud_placeholder(st):
                    continue  # OneDrive "solo en línea": no ocupa disco
                size = st.st_size
                node.own_size += size
                node.own_files += 1
                if node.zone:
                    type_id = node.zone
                elif entry.name.lower() in SYSTEM_FILES:
                    type_id = "system"
                else:
                    type_id = type_for_extension(entry.name)
                bucket = analysis.by_type[type_id]
                bucket[0] += size
                bucket[1] += 1
                analysis.total_files += 1
                analysis.total_size += size
                item = (size, entry.path, st.st_mtime, type_id)
                if len(heap) < top:
                    heapq.heappush(heap, item)
                elif size > heap[0][0]:
                    heapq.heapreplace(heap, item)
        if progress and time.monotonic() - last_report > 0.2:
            last_report = time.monotonic()
            progress(analysis.total_files, analysis.total_size, node.path)

    # Los hijos siempre se crean después que su padre: recorriendo al revés,
    # cada carpeta suma sus subcarpetas antes de sumarse a su padre.
    for node in reversed(nodes):
        node.size += node.own_size
        node.files += node.own_files
        if node.parent is not None:
            node.parent.size += node.size
            node.parent.files += node.files
    analysis.total_dirs = len(nodes)
    analysis.largest = [FoundFile(p, s, m, t) for s, p, m, t in sorted(heap, reverse=True)]
    analysis.seconds = time.monotonic() - started
    return analysis
