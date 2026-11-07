"""Buscador de archivos duplicados (mismo contenido, aunque tengan otro nombre)."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from .cleaner import norm
from .fsutil import IS_WINDOWS, is_cloud_placeholder, walk_files
from .largefiles import SKIP_DIR_NAMES

CHUNK = 1024 * 1024
PARTIAL = 64 * 1024


@dataclass
class DupFile:
    path: str
    mtime: float

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


@dataclass
class DuplicateGroup:
    size: int
    files: list = field(default_factory=list)  # DupFile, del más antiguo al más nuevo

    @property
    def wasted(self) -> int:
        return self.size * (len(self.files) - 1)


ProgressFn = Optional[Callable[[str, int, int], None]]


def _hash(path: str, limit: Optional[int], cancel: Optional[threading.Event]) -> Optional[str]:
    digest = hashlib.blake2b(digest_size=20)
    remaining = limit
    try:
        with open(path, "rb") as fh:
            while True:
                if cancel is not None and cancel.is_set():
                    return None
                size = CHUNK if remaining is None else min(CHUNK, remaining)
                if size <= 0:
                    break
                block = fh.read(size)
                if not block:
                    break
                digest.update(block)
                if remaining is not None:
                    remaining -= len(block)
    except OSError:
        return None
    return digest.hexdigest()


def find_duplicates(
    folder: str,
    min_size: int = 1024 * 1024,
    *,
    cancel: Optional[threading.Event] = None,
    progress: ProgressFn = None,
) -> tuple[list[DuplicateGroup], int]:
    """Grupos de archivos idénticos, ordenados por espacio desperdiciado."""
    windir = norm(os.environ.get("SystemRoot", r"C:\Windows")) if IS_WINDOWS else None

    def skip_dir(path: str, name: str) -> bool:
        return name.lower() in SKIP_DIR_NAMES or (windir is not None and norm(path) == windir)

    by_size: dict[int, list] = defaultdict(list)
    scanned = 0
    last = 0.0
    for path, st in walk_files(folder, strict=False, cancel=cancel, skip_dir=skip_dir):
        scanned += 1
        if st.st_size >= min_size and not is_cloud_placeholder(st):
            by_size[st.st_size].append(DupFile(path, st.st_mtime))
        if progress and time.monotonic() - last > 0.2:
            last = time.monotonic()
            progress("buscar", scanned, 0)

    candidates = [files for files in by_size.values() if len(files) > 1]
    total = sum(len(files) for files in candidates)
    done = 0
    groups: list[DuplicateGroup] = []
    for files in candidates:
        if cancel is not None and cancel.is_set():
            break
        size = os.path.getsize(files[0].path) if os.path.exists(files[0].path) else 0
        # 1) primeros 64 KB, 2) archivo completo: solo para los que siguen coincidiendo.
        partial: dict[str, list] = defaultdict(list)
        for item in files:
            key = _hash(item.path, PARTIAL, cancel)
            if key:
                partial[key].append(item)
        for same_start in partial.values():
            if len(same_start) < 2:
                continue
            full: dict[str, list] = defaultdict(list)
            for item in same_start:
                key = _hash(item.path, None, cancel) if size > PARTIAL else "parcial-completo"
                if key:
                    full[key].append(item)
            for same in full.values():
                if len(same) > 1:
                    groups.append(DuplicateGroup(size, sorted(same, key=lambda f: f.mtime)))
        done += len(files)
        if progress:
            progress("comparar", done, total)
    groups.sort(key=lambda g: g.wasted, reverse=True)
    return groups, scanned
