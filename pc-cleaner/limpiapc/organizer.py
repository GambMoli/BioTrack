"""Organizar una carpeta (p. ej. Descargas) en subcarpetas por tipo o por fecha.

Solo se mueven los archivos sueltos de esa carpeta (no se tocan sus subcarpetas),
nunca se sobrescribe nada y cada organización se puede deshacer.
"""

from __future__ import annotations

import glob
import json
import os
import stat
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from .cleaner import is_protected, is_within, norm
from .filetypes import TYPES_BY_ID, type_for_extension
from .fileops import unique_path
from .fsutil import FILE_ATTRIBUTE_REPARSE_POINT, IS_WINDOWS, file_attributes
from .largefiles import is_system_path

MONTHS = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
          "Septiembre", "Octubre", "Noviembre", "Diciembre")
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
# Descargas a medias y accesos directos: no se mueven nunca.
SKIP_EXTENSIONS = {".crdownload", ".part", ".partial", ".download", ".opdownload", ".tmp", ".!ut",
                   ".lnk", ".url"}
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
RECENT_SECONDS = 120


@dataclass
class PlannedMove:
    src: str
    dest_dir: str
    size: int
    type_id: str

    @property
    def name(self) -> str:
        return os.path.basename(self.src)


def data_dir() -> str:
    override = os.environ.get("LIMPIAPC_DATA_DIR")
    if override:
        return override
    if IS_WINDOWS and os.environ.get("LOCALAPPDATA"):
        return os.path.join(os.environ["LOCALAPPDATA"], "LimpiaPC")
    return os.path.join(os.path.expanduser("~"), ".local", "share", "limpiapc")


def check_folder(folder: str) -> str:
    """Devuelve un motivo si la carpeta no se debe organizar, o "" si se puede."""
    if not os.path.isdir(folder):
        return "La carpeta no existe."
    key = norm(folder)
    home = norm(os.path.expanduser("~"))
    if key == home or is_protected(folder) and not _is_user_folder(key, home):
        return "Elige una carpeta concreta, como Descargas, Escritorio o Documentos."
    if is_system_path(folder):
        return "Esa carpeta es de Windows o de programas instalados: organizarla podría romperlos."
    for part in key.split(os.sep):
        if part.lower() in ("appdata", ".config", ".local", "library"):
            return "Esa carpeta guarda datos internos de programas: mejor no tocarla."
    return ""


def _is_user_folder(key: str, home: str) -> bool:
    return is_within(key, home) and key != home


def plan_organize(folder: str, mode: str = "type") -> list[PlannedMove]:
    """Qué se movería y adónde (no mueve nada). mode: "type" | "date"."""
    moves: list[PlannedMove] = []
    now = time.time()
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name.lower())
    except OSError:
        return moves
    for entry in entries:
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode):
            continue
        attributes = file_attributes(st)
        if attributes & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM | FILE_ATTRIBUTE_REPARSE_POINT):
            continue
        lowered = entry.name.lower()
        if lowered in SKIP_NAMES or lowered.startswith(".") or os.path.splitext(lowered)[1] in SKIP_EXTENSIONS:
            continue
        if now - max(st.st_mtime, st.st_ctime) < RECENT_SECONDS:
            continue  # quizá se está descargando ahora mismo
        type_id = type_for_extension(entry.name)
        if mode == "date":
            stamp = datetime.fromtimestamp(st.st_mtime)
            dest = os.path.join(folder, str(stamp.year), f"{stamp.month:02d} - {MONTHS[stamp.month - 1]}")
        else:
            dest = os.path.join(folder, TYPES_BY_ID[type_id].folder or "Otros")
        moves.append(PlannedMove(entry.path, dest, st.st_size, type_id))
    return moves


def apply_plan(
    folder: str,
    moves: list[PlannedMove],
    mode: str,
    cancel: Optional[threading.Event] = None,
    progress: Optional[Callable[[int], None]] = None,
) -> dict:
    """Mueve los archivos y guarda un registro para poder deshacerlo."""
    record = {"folder": folder, "mode": mode, "date": datetime.now().isoformat(timespec="seconds"),
              "moves": [], "created_dirs": [], "errors": []}
    for index, move in enumerate(moves, 1):
        if cancel is not None and cancel.is_set():
            break
        try:
            missing = []
            current = move.dest_dir
            while not os.path.isdir(current) and norm(current) != norm(folder):
                missing.append(current)
                current = os.path.dirname(current)
            os.makedirs(move.dest_dir, exist_ok=True)
            record["created_dirs"].extend(reversed(missing))
            dest = unique_path(os.path.join(move.dest_dir, move.name))
            os.rename(move.src, dest)  # misma carpeta = misma unidad
            record["moves"].append([move.src, dest])
        except OSError as exc:
            record["errors"].append(f"{move.name}: {exc.strerror or exc}")
        if progress:
            progress(index)
    if record["moves"]:
        _save_record(record)
    return record


def _history_dir() -> str:
    return os.path.join(data_dir(), "historial")


def _save_record(record: dict) -> None:
    os.makedirs(_history_dir(), exist_ok=True)
    name = "organizar-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
    path = os.path.join(_history_dir(), name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)
    record["_file"] = path


def last_record() -> Optional[dict]:
    files = sorted(glob.glob(os.path.join(glob.escape(_history_dir()), "organizar-*.json")))
    for path in reversed(files):
        try:
            with open(path, encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            continue
        record["_file"] = path
        return record
    return None


def undo(record: dict) -> tuple[int, list[str]]:
    """Devuelve los archivos a su sitio. (restaurados, errores)."""
    restored, errors = 0, []
    for src, dest in reversed(record.get("moves", [])):
        if not os.path.lexists(dest):
            errors.append(f"{os.path.basename(dest)}: ya no está donde se movió.")
            continue
        if os.path.lexists(src):
            errors.append(f"{os.path.basename(src)}: ya hay otro archivo con ese nombre.")
            continue
        try:
            os.rename(dest, src)
            restored += 1
        except OSError as exc:
            errors.append(f"{os.path.basename(dest)}: {exc.strerror or exc}")
    for directory in sorted(record.get("created_dirs", []), key=len, reverse=True):
        try:
            os.rmdir(directory)  # solo si quedó vacía
        except OSError:
            pass
    path = record.get("_file")
    if path:
        try:
            os.remove(path)
        except OSError:
            pass
    return restored, errors
