"""Clasificación de archivos por tipo (para analizar y organizar)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FileType:
    id: str
    name: str
    color: str
    folder: str           # carpeta destino al organizar ("" = no se organiza por tipo)
    extensions: frozenset = frozenset()


FILE_TYPES = (
    FileType("video", "Vídeos", "#f472b6", "Vídeos", frozenset(
        ".mp4 .mkv .avi .mov .wmv .flv .webm .m4v .mpg .mpeg .3gp .mts .m2ts .vob .ts".split())),
    FileType("image", "Imágenes y fotos", "#60a5fa", "Imágenes", frozenset(
        ".jpg .jpeg .png .gif .bmp .tif .tiff .webp .heic .heif .raw .cr2 .cr3 .nef .arw .dng "
        ".psd .svg .ico .avif .jfif".split())),
    FileType("audio", "Música y audio", "#a78bfa", "Música", frozenset(
        ".mp3 .wav .flac .aac .ogg .m4a .wma .opus .aiff .mid .midi".split())),
    FileType("docs", "Documentos", "#fbbf24", "Documentos", frozenset(
        ".pdf .doc .docx .xls .xlsx .xlsm .ppt .pptx .odt .ods .odp .txt .rtf .csv .epub .md "
        ".pages .numbers .key .xps .one".split())),
    FileType("archives", "Comprimidos e imágenes de disco", "#fb923c", "Comprimidos", frozenset(
        ".zip .rar .7z .tar .gz .tgz .bz2 .xz .zst .iso .img .vhd .vhdx .vmdk .cab .dmg".split())),
    FileType("programs", "Programas e instaladores", "#34d399", "Instaladores", frozenset(
        ".exe .msi .msix .msixbundle .appx .appxbundle .dll .sys .ocx .drv .mui .apk".split())),
    FileType("games", "Juegos", "#f87171", ""),
    FileType("dev", "Programación (node_modules, .git…)", "#22d3ee", ""),
    FileType("appdata", "Datos de programas (AppData)", "#a3e635", ""),
    FileType("system", "Windows y sistema", "#94a3b8", ""),
    FileType("other", "Otros", "#64748b", "Otros"),
)
TYPES_BY_ID = {t.id: t for t in FILE_TYPES}
_EXTENSION_INDEX = {ext: t.id for t in FILE_TYPES for ext in t.extensions}

# Carpetas que, por su nombre, indican qué hay dentro.
GAME_DIRS = {"steamapps", "epic games", "xboxgames", "riot games", "gog games", "ea games",
             "ubisoft game launcher", "rockstar games", "battle.net", "games"}
DEV_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".gradle", ".m2", ".nuget",
            ".cargo", ".rustup", ".npm", ".yarn", "site-packages", "androidsdk", ".android"}
SYSTEM_FILES = {"pagefile.sys", "hiberfil.sys", "swapfile.sys", "dumpstack.log.tmp"}


def type_for_extension(filename: str) -> str:
    return _EXTENSION_INDEX.get(os.path.splitext(filename)[1].lower(), "other")
