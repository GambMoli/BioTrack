"""Operaciones de archivo seguras: mover sin sobrescribir nunca nada."""

from __future__ import annotations

import os
import shutil


def unique_path(path: str) -> str:
    """'foto.jpg' -> 'foto (2).jpg' si ya existe."""
    if not os.path.lexists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.lexists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def move_file(src: str, dest_dir: str) -> str:
    """Mueve `src` a `dest_dir` (creándola si hace falta). Devuelve la ruta final."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = unique_path(os.path.join(dest_dir, os.path.basename(src)))
    try:
        os.rename(src, dest)  # misma unidad: instantáneo
        return dest
    except OSError:
        if not os.path.exists(src) or os.path.lexists(dest):
            raise
    # Otra unidad: copiar, comprobar y solo entonces borrar el original.
    try:
        shutil.copy2(src, dest)
        if os.path.getsize(dest) != os.path.getsize(src):
            raise OSError("La copia no coincide con el original.")
    except BaseException:
        if os.path.exists(dest):
            os.remove(dest)
        raise
    os.remove(src)
    return dest
