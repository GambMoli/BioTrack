"""Pruebas contra las APIs reales de Windows (papelera, registro, carpetas, sistema).

Pensado para la máquina desechable de GitHub Actions: envía un archivo de prueba a la
papelera y crea (y luego borra) una entrada de inicio de prueba en el registro del usuario.
No vacía la papelera ni toca nada más. Sale con código 1 si algo falla.
"""

import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from limpiapc import analyzer, startup, system_info, trash  # noqa: E402
from limpiapc.platform_utils import (  # noqa: E402
    IS_WINDOWS, is_admin, running_process_names, top_memory_processes, user_folders,
)

if not IS_WINDOWS:
    print("Solo para Windows.")
    sys.exit(0)

import winreg  # noqa: E402

failures = []


def check(condition, text):
    print(("OK   " if condition else "FAIL ") + text, flush=True)
    if not condition:
        failures.append(text)


# --- Sistema -------------------------------------------------------------------
print("Windows:", system_info.os_description(), "| administrador:", is_admin())
disks = system_info.get_disks()
check(bool(disks) and all(d.total > 0 for d in disks), f"discos: {[d.label for d in disks]}")
memory = system_info.get_memory()
check(memory is not None and memory.total > 0, f"memoria: {memory}")
sampler = system_info.CpuSampler()
time.sleep(0.5)
usage = sampler.sample()
check(usage is not None and 0 <= usage <= 1, f"uso de CPU: {usage}")
check((system_info.get_uptime_seconds() or 0) > 0, "tiempo encendido")
check("python.exe" in running_process_names(), "lista de procesos (tasklist)")
check(bool(top_memory_processes(3)), f"procesos que más memoria usan: {top_memory_processes(3)}")
folders = dict(user_folders())
check("Mi carpeta de usuario" in folders, f"carpetas del usuario: {folders}")

# --- Papelera -------------------------------------------------------------------
info = trash.recycle_bin_info()
check(info is not None, f"consultar la papelera (SHQueryRecycleBinW): {info}")
work = tempfile.mkdtemp(prefix="limpiapc-it-")  # en C:, que seguro tiene papelera
probe = os.path.join(work, "prueba papelera ñ.txt")
with open(probe, "w", encoding="utf-8") as fh:
    fh.write("x" * 5000)
try:
    trash.send_to_trash(probe)
    check(not os.path.exists(probe), "enviar a la papelera (SHFileOperationW)")
except OSError as exc:
    check(False, f"enviar a la papelera: {exc}")

# --- Programas al iniciar (registro real del usuario) -----------------------------
NAME = "LimpiaPC-Prueba-CI"
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as key:
    winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, r"C:\Windows\notepad.exe")
try:
    item = next((i for i in startup.list_startup_items(is_admin()) if i.name == NAME), None)
    check(item is not None and item.enabled and item.can_toggle, "leer programas de inicio")
    if item:
        startup.set_enabled(item, False)
        again = next(i for i in startup.list_startup_items(is_admin()) if i.name == NAME)
        check(not again.enabled, "deshabilitar un programa de inicio")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED) as key:
            data, kind = winreg.QueryValueEx(key, NAME)
        check(kind == winreg.REG_BINARY and len(data) == 12 and data[0] == 3, "formato StartupApproved")
        startup.set_enabled(again, True)
        check(next(i for i in startup.list_startup_items(is_admin()) if i.name == NAME).enabled,
              "volver a habilitarlo")
finally:
    for path in (RUN, APPROVED):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, NAME)
        except OSError:
            pass

# --- Análisis de una carpeta real ---------------------------------------------------
result = analyzer.analyze(sys.prefix)
check(result.total_files > 100 and result.root.size == result.total_size,
      f"análisis de {sys.prefix}: {result.total_files} archivos, {result.total_size} bytes")

print("RESULTADO:", "OK" if not failures else f"{len(failures)} fallos: {failures}")
sys.exit(1 if failures else 0)
