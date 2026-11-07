"""Programas que se abren al iniciar sesión.

En Windows se habilitan/deshabilitan igual que lo hace el Administrador de tareas
(claves "StartupApproved"), así que no se borra nada y se puede deshacer
desde LimpiaPC o desde el propio Administrador de tareas.
"""

from __future__ import annotations

import configparser
import glob
import os
import time
from dataclasses import dataclass
from typing import Optional

from .platform_utils import IS_MAC, IS_WINDOWS

if IS_WINDOWS:
    import winreg

_BASE = r"Software\Microsoft\Windows\CurrentVersion"
_APPROVED = _BASE + r"\Explorer\StartupApproved"


@dataclass
class StartupItem:
    name: str
    command: str
    location: str
    scope: str            # "Usuario" | "Todos los usuarios"
    enabled: bool
    can_toggle: bool
    hive: Optional[int] = None
    approved_key: str = ""
    value_name: str = ""


def list_startup_items(admin: bool = False) -> list[StartupItem]:
    if IS_WINDOWS:
        return _windows_items(admin)
    if not IS_MAC:
        return _linux_items()
    return []


def set_enabled(item: StartupItem, enabled: bool) -> None:
    if not IS_WINDOWS or not item.can_toggle:
        raise OSError("Este elemento no se puede cambiar desde aquí.")
    if enabled:
        data = b"\x02" + b"\x00" * 11
    else:
        filetime = int((time.time() + 11644473600) * 10_000_000)
        data = b"\x03\x00\x00\x00" + filetime.to_bytes(8, "little")
    access = winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
    with winreg.CreateKeyEx(item.hive, item.approved_key, 0, access) as key:
        winreg.SetValueEx(key, item.value_name, 0, winreg.REG_BINARY, data)
    item.enabled = enabled


# --------------------------------------------------------------------------- #
# Windows
# --------------------------------------------------------------------------- #
def _read_values(hive: int, path: str) -> list[tuple[str, object]]:
    try:
        key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except OSError:
        return []
    values = []
    with key:
        index = 0
        while True:
            try:
                name, data, _kind = winreg.EnumValue(key, index)
            except OSError:
                break
            values.append((name, data))
            index += 1
    return values


def _approval_map(hive: int, kind: str) -> dict[str, bool]:
    states = {}
    for name, data in _read_values(hive, rf"{_APPROVED}\{kind}"):
        if isinstance(data, (bytes, bytearray)) and data:
            states[name.lower()] = not (data[0] & 1)  # impar = deshabilitado
    return states


def _windows_items(admin: bool) -> list[StartupItem]:
    hkcu, hklm = winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE
    items: list[StartupItem] = []
    registry_sources = [
        (hkcu, _BASE + r"\Run", "Run", "Usuario", "Registro"),
        (hklm, _BASE + r"\Run", "Run", "Todos los usuarios", "Registro"),
        (hklm, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "Run32",
         "Todos los usuarios", "Registro (32 bits)"),
    ]
    for hive, path, kind, scope, location in registry_sources:
        states = _approval_map(hive, kind)
        toggle = hive == hkcu or admin
        for name, data in _read_values(hive, path):
            if not name:
                continue
            items.append(StartupItem(
                name=name, command=str(data), location=location, scope=scope,
                enabled=states.get(name.lower(), True), can_toggle=toggle,
                hive=hive, approved_key=rf"{_APPROVED}\{kind}", value_name=name,
            ))

    folder_sources = [
        (hkcu, os.environ.get("APPDATA", ""), "Usuario"),
        (hklm, os.environ.get("ProgramData", ""), "Todos los usuarios"),
    ]
    for hive, base, scope in folder_sources:
        if not base:
            continue
        folder = os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        states = _approval_map(hive, "StartupFolder")
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            continue
        for filename in entries:
            if filename.lower() == "desktop.ini":
                continue
            items.append(StartupItem(
                name=os.path.splitext(filename)[0], command=os.path.join(folder, filename),
                location="Carpeta Inicio", scope=scope,
                enabled=states.get(filename.lower(), True), can_toggle=hive == hkcu or admin,
                hive=hive, approved_key=rf"{_APPROVED}\StartupFolder", value_name=filename,
            ))
    items.sort(key=lambda i: i.name.lower())
    return items


# --------------------------------------------------------------------------- #
# Linux (solo lectura)
# --------------------------------------------------------------------------- #
def _linux_items() -> list[StartupItem]:
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    items = []
    for path in sorted(glob.glob(os.path.join(glob.escape(config), "autostart", "*.desktop"))):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read(path, encoding="utf-8")
            entry = parser["Desktop Entry"]
        except (configparser.Error, KeyError, OSError, UnicodeDecodeError):
            continue
        disabled = entry.get("Hidden", "false").lower() == "true" or \
            entry.get("X-GNOME-Autostart-enabled", "true").lower() == "false"
        items.append(StartupItem(
            name=entry.get("Name", os.path.basename(path)), command=entry.get("Exec", ""),
            location="~/.config/autostart", scope="Usuario", enabled=not disabled, can_toggle=False,
        ))
    return items
