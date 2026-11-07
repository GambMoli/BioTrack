"""Información del equipo: discos, memoria, CPU y tiempo encendido."""

from __future__ import annotations

import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Optional

from .platform_utils import IS_MAC, IS_WINDOWS, run_quiet

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.windll.kernel32

    class _MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    _kernel32.GetTickCount64.restype = ctypes.c_ulonglong


@dataclass
class DiskInfo:
    label: str
    mount: str
    total: int
    used: int
    free: int

    @property
    def fraction(self) -> float:
        return self.used / self.total if self.total else 0.0


@dataclass
class MemoryInfo:
    total: int
    available: int

    @property
    def used(self) -> int:
        return max(0, self.total - self.available)

    @property
    def fraction(self) -> float:
        return self.used / self.total if self.total else 0.0


# --------------------------------------------------------------------------- #
def os_description() -> str:
    if IS_WINDOWS:
        build = sys.getwindowsversion().build
        name = "Windows 11" if build >= 22000 else f"Windows {platform.release()}"
        return f"{name} (compilación {build})"
    if IS_MAC:
        return f"macOS {platform.mac_ver()[0]}"
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


def _windows_volume_name(root: str) -> str:
    buffer = ctypes.create_unicode_buffer(261)
    ok = _kernel32.GetVolumeInformationW(ctypes.c_wchar_p(root), buffer, len(buffer),
                                         None, None, None, None, 0)
    return buffer.value if ok else ""


def get_disks() -> list[DiskInfo]:
    disks: list[DiskInfo] = []
    if IS_WINDOWS:
        mask = _kernel32.GetLogicalDrives()
        for index in range(26):
            if not mask & (1 << index):
                continue
            root = f"{chr(65 + index)}:\\"
            if _kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) not in (2, 3):  # extraíble, fija
                continue
            try:
                usage = shutil.disk_usage(root)
            except OSError:
                continue  # lector de tarjetas vacío, etc.
            name = _windows_volume_name(root) or ("Disco local" if index == 2 else "Unidad")
            disks.append(DiskInfo(f"{name} ({root[:2]})", root, usage.total, usage.used, usage.free))
        return disks

    mounts = ["/"]
    home = os.path.expanduser("~")
    try:
        if os.stat(home).st_dev != os.stat("/").st_dev:
            mounts.append(home)
    except OSError:
        pass
    for mount in mounts:
        try:
            usage = shutil.disk_usage(mount)
        except OSError:
            continue
        label = "Sistema (/)" if mount == "/" else f"Usuario ({mount})"
        disks.append(DiskInfo(label, mount, usage.total, usage.used, usage.free))
    return disks


def get_memory() -> Optional[MemoryInfo]:
    try:
        if IS_WINDOWS:
            status = _MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if not _kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return MemoryInfo(int(status.ullTotalPhys), int(status.ullAvailPhys))
        if os.path.exists("/proc/meminfo"):
            values = {}
            with open("/proc/meminfo", encoding="utf-8") as fh:
                for line in fh:
                    key, _, rest = line.partition(":")
                    values[key] = int(rest.split()[0]) * 1024
            return MemoryInfo(values["MemTotal"], values.get("MemAvailable", values.get("MemFree", 0)))
        if IS_MAC:
            total = int(run_quiet(["sysctl", "-n", "hw.memsize"]).stdout.strip())
            out = run_quiet(["vm_stat"]).stdout.decode("utf-8", errors="replace")
            page_size, free_pages = 4096, 0
            for line in out.splitlines():
                if "page size of" in line:
                    page_size = int("".join(ch for ch in line.split("page size of")[1] if ch.isdigit()))
                elif line.startswith(("Pages free", "Pages inactive", "Pages speculative")):
                    free_pages += int(line.split(":")[1].strip().rstrip("."))
            return MemoryInfo(total, free_pages * page_size)
    except Exception:
        return None
    return None


class CpuSampler:
    """Mide el uso de CPU entre dos llamadas consecutivas a `sample()`."""

    def __init__(self) -> None:
        self._last = self._read()

    @staticmethod
    def _read() -> Optional[tuple[float, float]]:
        """(tiempo inactivo, tiempo total) acumulados."""
        try:
            if IS_WINDOWS:
                idle, kernel, user = (wintypes.FILETIME() for _ in range(3))
                if not _kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                    return None

                def value(ft):
                    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime

                # El tiempo de kernel ya incluye el inactivo.
                return float(value(idle)), float(value(kernel) + value(user))
            if os.path.exists("/proc/stat"):
                with open("/proc/stat", encoding="utf-8") as fh:
                    fields = [float(x) for x in fh.readline().split()[1:]]
                idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
                return idle, sum(fields[:8])
        except Exception:
            return None
        return None

    def sample(self) -> Optional[float]:
        current = self._read()
        previous, self._last = self._last, current
        if not current or not previous:
            return None
        idle = current[0] - previous[0]
        total = current[1] - previous[1]
        if total <= 0:
            return None
        return max(0.0, min(1.0, 1.0 - idle / total))


def get_uptime_seconds() -> Optional[float]:
    try:
        if IS_WINDOWS:
            return _kernel32.GetTickCount64() / 1000.0
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", encoding="utf-8") as fh:
                return float(fh.read().split()[0])
        if IS_MAC:
            out = run_quiet(["sysctl", "-n", "kern.boottime"]).stdout.decode()
            seconds = int(out.split("sec =")[1].split(",")[0])
            return time.time() - seconds
    except Exception:
        return None
    return None
