"""Operaciones de sistema de Windows para liberar espacio en C:.

Todo usa herramientas oficiales de Microsoft (powercfg, Liberador de espacio, DISM,
WMI/CIM) y necesita permisos de administrador. En otros sistemas no hace nada.
"""

from __future__ import annotations

import base64
import os
import platform
import re
import subprocess
from typing import Callable, Optional

from .fsutil import walk_files
from .platform_utils import CREATE_NO_WINDOW, IS_WINDOWS, decode_output, human_size

# Número de "perfil" de /sageset:/sagerun: con el que LimpiaPC marca lo que limpia.
SAGE_SET = 7717
VOLUME_CACHES = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches"

# Lista blanca de manejadores del Liberador de espacio que LimpiaPC activa.
# NUNCA se incluyen: "DownloadsFolder" (¡borra tu carpeta de Descargas!), "Recycle Bin"
# (la papelera se trata aparte), "User file versions" (Historial de archivos),
# "Windows ESD installation files" (necesarios para «Restablecer este PC»),
# "Language Pack" ni "Device Driver Packages".
SAFE_CLEANUP_HANDLERS = frozenset(name.lower() for name in (
    "Previous Installations",            # Windows.old
    "Update Cleanup",                    # actualizaciones ya sustituidas
    "Delivery Optimization Files",
    "Temporary Setup Files",             # $WINDOWS.~BT, $WINDOWS.~WS
    "Windows Upgrade Log Files",
    "Setup Log Files",
    "Upgrade Discarded Files",
    "Windows Error Reporting Files",
    "Windows Error Reporting Archive Files",
    "Windows Error Reporting Queue Files",
    "Windows Error Reporting System Archive Files",
    "Windows Error Reporting System Queue Files",
    "Windows Error Reporting Temp Files",
    "System error memory dump files",
    "System error minidump files",
    "Memory Dump Files",
    "Old ChkDsk Files",
    "Downloaded Program Files",
    "Windows Defender",
    "RetailDemo Offline Content",
    "Feedback Hub Archive log files",
    "Diagnostic Data Viewer database files",
    "Active Setup Temp Folders",
    "Content Indexer Cleaner",
    "Offline Pages Files",
    "Temporary Sync Files",
    "BranchCache",
    "Service Pack Cleanup",
))


def system_drive() -> str:
    """'C:\\' en Windows (o la unidad donde esté instalado); '/' en otros sistemas."""
    if IS_WINDOWS:
        return (os.environ.get("SystemDrive") or "C:").rstrip("\\") + "\\"
    return "/"


def system32(exe: str) -> str:
    """Ruta a un programa de System32 (con Python de 32 bits se usa Sysnative)."""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    sysnative = os.path.join(root, "Sysnative")
    if platform.architecture()[0] == "32bit" and os.path.isdir(sysnative):
        return os.path.join(sysnative, exe)
    return os.path.join(root, "System32", exe)


def _run(args: list[str], timeout: Optional[float] = None) -> tuple[int, str]:
    result = subprocess.run(args, capture_output=True, timeout=timeout,
                            creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0)
    return result.returncode, decode_output(result.stdout + result.stderr).strip()


def powershell(script: str, timeout: float = 180) -> tuple[int, str]:
    """Ejecuta un script de PowerShell (codificado, sin problemas de comillas)."""
    full = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';"
            + script)
    encoded = base64.b64encode(full.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [system32(r"WindowsPowerShell\v1.0\powershell.exe"), "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
        capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0)
    return result.returncode, result.stdout.decode("utf-8", errors="replace").strip()


def folder_size(path: str) -> int:
    return sum(st.st_size for _, st in walk_files(path, strict=False))


# --------------------------------------------------------------------------- #
# Hibernación
# --------------------------------------------------------------------------- #
def hibernation_file_size(drive: Optional[str] = None) -> Optional[int]:
    """Tamaño de hiberfil.sys (leído del listado de la unidad: funciona aunque esté en uso)."""
    try:
        with os.scandir(drive or system_drive()) as entries:
            for entry in entries:
                if entry.name.lower() == "hiberfil.sys":
                    return entry.stat(follow_symlinks=False).st_size
    except OSError:
        return None
    return None


def has_battery() -> bool:
    """True en portátiles (o si no se puede saber)."""
    if not IS_WINDOWS:
        return False
    import ctypes
    from ctypes import wintypes

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]

    status = SYSTEM_POWER_STATUS()
    try:
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return True
    except Exception:  # noqa: BLE001
        return True
    return status.BatteryFlag != 128  # 128 = "no hay batería"


def disable_hibernation() -> tuple[int, str]:
    """Borra hiberfil.sys. Se deshace con: powercfg /hibernate on"""
    return _run([system32("powercfg.exe"), "/hibernate", "off"], timeout=120)


# --------------------------------------------------------------------------- #
# Puntos de restauración (instantáneas de volumen)
# --------------------------------------------------------------------------- #
def _volume_filter(drive: str) -> str:
    letter = drive.rstrip("\\")[:2]
    return f"$v = Get-CimInstance Win32_Volume -Filter \"DriveLetter='{letter}'\";"


def shadow_copies(drive: Optional[str] = None) -> Optional[tuple[int, int]]:
    """(nº de puntos de restauración, bytes que ocupan) en la unidad, o None si no se puede saber."""
    script = ("$ErrorActionPreference='Stop';" + _volume_filter(drive or system_drive()) +
              "$c=@(Get-CimInstance Win32_ShadowCopy | Where-Object { $_.VolumeName -eq $v.DeviceID });"
              "$u=[int64]0;"
              "foreach($s in @(Get-CimInstance Win32_ShadowStorage)){"
              " if($s.DiffVolume.DeviceID -eq $v.DeviceID){ $u += [int64]$s.UsedSpace } };"
              "Write-Output \"$($c.Count) $u\"")
    try:
        code, out = powershell(script, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\s+(\d+)\s*$", out)
    if code != 0 or not match:
        return None
    return int(match.group(1)), int(match.group(2))


def delete_old_shadow_copies(drive: Optional[str] = None) -> tuple[int, str]:
    """Borra todos los puntos de restauración de la unidad menos el más reciente."""
    script = ("$ErrorActionPreference='Stop';" + _volume_filter(drive or system_drive()) +
              "$c=@(Get-CimInstance Win32_ShadowCopy | Where-Object { $_.VolumeName -eq $v.DeviceID }"
              " | Sort-Object InstallDate);"
              "$n=0; if($c.Count -gt 1){ foreach($x in $c[0..($c.Count-2)]){ Remove-CimInstance -InputObject $x; $n++ } };"
              "Write-Output $n")
    return powershell(script, timeout=600)


# --------------------------------------------------------------------------- #
# Almacenamiento reservado y CompactOS
# --------------------------------------------------------------------------- #
def reserved_storage_enabled() -> Optional[bool]:
    try:
        code, out = powershell("(Get-WindowsReservedStorageState).ReservedStorageState", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if code != 0:
        return None
    if "Enabled" in out:
        return True
    if "Disabled" in out:
        return False
    return None


def disable_reserved_storage() -> tuple[int, str]:
    return powershell("$ErrorActionPreference='Stop'; Set-WindowsReservedStorageState -State Disabled",
                      timeout=600)


def compact_os() -> tuple[int, str]:
    return _run([system32("compact.exe"), "/CompactOS:always"])


# --------------------------------------------------------------------------- #
# Liberador de espacio de Windows (modo "archivos del sistema") y DISM
# --------------------------------------------------------------------------- #
def run_disk_cleanup(winreg_module=None, runner: Optional[Callable[[list[str]], int]] = None) -> int:
    """Marca SOLO los manejadores de la lista blanca y ejecuta cleanmgr /sagerun.

    Antes de empezar quita la marca de LimpiaPC de cualquier otro manejador (por si alguien
    la dejó puesta) y al terminar borra todas sus marcas del registro.
    """
    winreg = winreg_module
    if winreg is None:
        import winreg  # noqa: PLC0415
    value_name = f"StateFlags{SAGE_SET:04d}"
    hklm = winreg.HKEY_LOCAL_MACHINE
    view = winreg.KEY_WOW64_64KEY
    handlers: list[str] = []
    with winreg.OpenKey(hklm, VOLUME_CACHES, 0, winreg.KEY_READ | view) as root:
        index = 0
        while True:
            try:
                handlers.append(winreg.EnumKey(root, index))
            except OSError:
                break
            index += 1

    def clear(name: str) -> None:
        try:
            with winreg.OpenKey(hklm, f"{VOLUME_CACHES}\\{name}", 0, winreg.KEY_SET_VALUE | view) as key:
                winreg.DeleteValue(key, value_name)
        except OSError:
            pass

    selected = [h for h in handlers if h.lower() in SAFE_CLEANUP_HANDLERS]
    for name in handlers:
        if name not in selected:
            clear(name)
    try:
        for name in selected:
            with winreg.OpenKey(hklm, f"{VOLUME_CACHES}\\{name}", 0, winreg.KEY_SET_VALUE | view) as key:
                winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, 2)
        command = [system32("cleanmgr.exe"), f"/sagerun:{SAGE_SET}"]
        if runner is not None:
            return runner(command)
        return subprocess.run(command).returncode  # muestra la ventana de progreso de Windows
    finally:
        for name in handlers:
            clear(name)


def component_cleanup(progress: Optional[Callable[[str], None]] = None) -> int:
    """DISM /StartComponentCleanup (sin /ResetBase: se pueden seguir desinstalando actualizaciones)."""
    process = subprocess.Popen(
        [system32("dism.exe"), "/Online", "/Cleanup-Image", "/StartComponentCleanup", "/NoRestart"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0)
    tail = b""
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(256)
        if not chunk:
            break
        tail = (tail + chunk)[-4000:]
        percents = re.findall(rb"(\d{1,3}(?:[.,]\d)?)\s?%", tail)
        if progress and percents:
            progress(percents[-1].decode("ascii").replace(".", ",") + " %")
    return process.wait()


# --------------------------------------------------------------------------- #
# Estimación de restos de Windows
# --------------------------------------------------------------------------- #
def windows_leftovers(drive: Optional[str] = None) -> tuple[int, list[str], bool]:
    """(bytes, detalles, hay Windows.old) de lo que el Liberador de espacio puede borrar."""
    drive = drive or system_drive()
    total, notes, has_old = 0, [], False
    old = os.path.join(drive, "Windows.old")
    if os.path.isdir(old):
        has_old = True
        size = folder_size(old)
        total += size
        notes.append(f"versión anterior de Windows (Windows.old): {human_size(size)}")
    setup = sum(folder_size(os.path.join(drive, name)) for name in ("$WINDOWS.~BT", "$WINDOWS.~WS")
                if os.path.isdir(os.path.join(drive, name)))
    if setup:
        total += setup
        notes.append(f"archivos de instalación de Windows: {human_size(setup)}")
    windir = os.environ.get("SystemRoot") or os.path.join(drive, "Windows")
    delivery = os.path.join(windir, "ServiceProfiles", "NetworkService", "AppData", "Local", "Microsoft",
                            "Windows", "DeliveryOptimization", "Cache")
    if os.path.isdir(delivery):
        size = folder_size(delivery)
        if size:
            total += size
            notes.append(f"Optimización de distribución: {human_size(size)}")
    return total, notes, has_old
