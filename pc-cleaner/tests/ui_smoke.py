"""Recorre toda la interfaz con datos falsos y hace capturas de pantalla.

Uso:  python tests/ui_smoke.py <carpeta_base> <carpeta_capturas>

Todo lo que se limpia, organiza o borra está dentro de <carpeta_base>/fake: el script
aborta si alguna categoría de limpieza apunta fuera de ahí. Sale con código 1 si algo falla.
"""

import os
import subprocess
import sys
import tempfile
import time
import traceback
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from limpiapc import cleaner, organizer  # noqa: E402
from limpiapc.platform_utils import IS_WINDOWS  # noqa: E402

BASE = os.path.abspath(sys.argv[1])
SHOTS = os.path.abspath(sys.argv[2])
os.makedirs(SHOTS, exist_ok=True)
FAKE = tempfile.mkdtemp(prefix="fake-", dir=BASE)
HOME = os.path.join(FAKE, "Users", "ana")
LOCAL = os.path.join(HOME, "AppData", "Local")
ROAMING = os.path.join(HOME, "AppData", "Roaming")
WINDIR = os.path.join(FAKE, "Windows")
TMP = os.path.join(LOCAL, "Temp")
DOWNLOADS = os.path.join(HOME, "Downloads")
OLD = time.time() - 5 * 86400

FAKE_ENV = {
    "LOCALAPPDATA": LOCAL, "APPDATA": ROAMING, "SystemRoot": WINDIR, "windir": WINDIR,
    "ProgramData": os.path.join(FAKE, "ProgramData"), "TEMP": TMP, "TMP": TMP,
    "HOME": HOME, "USERPROFILE": HOME,
    "XDG_CACHE_HOME": os.path.join(HOME, ".cache"), "XDG_DATA_HOME": os.path.join(HOME, ".local", "share"),
}
os.environ["LIMPIAPC_DATA_DIR"] = os.path.join(FAKE, "datos-limpiapc")
os.environ["LIMPIAPC_NO_GIO"] = "1"

# --- Las categorías de limpieza se construyen SIEMPRE con rutas falsas ---
_real_build = cleaner.build_categories


def _fake_build():
    with mock.patch.dict(os.environ, FAKE_ENV), mock.patch.object(tempfile, "tempdir", TMP):
        categories = _real_build()
    for category in categories:
        for target in category.targets:
            if not cleaner.is_within(cleaner.norm(target.base), cleaner.norm(FAKE)):
                raise SystemExit(f"ABORTADO: {category.id} apunta fuera de la carpeta falsa: {target.base}")
        if category.kind == "recycle_bin":
            assert not category.default_on, "la papelera real no debe venir marcada"
    return categories


cleaner.build_categories = _fake_build
organizer.RECENT_SECONDS = -1  # los archivos de prueba se acaban de crear


def mk(path, size, sparse=False, old=False, data=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        if data is not None:
            fh.write(data)
        elif sparse:
            fh.truncate(size)
        else:
            fh.write(b"\0" * size)
    if old:
        os.utime(path, (OLD, OLD))


# --- Datos de prueba -------------------------------------------------------
chrome = os.path.join(LOCAL, "Google", "Chrome", "User Data", "Default")
for i in range(40):
    mk(os.path.join(chrome, "Cache", "Cache_Data", f"f_{i:04x}"), 300_000)
    mk(os.path.join(HOME, ".cache", "google-chrome", "Default", "Cache", f"f_{i}"), 300_000)
mk(os.path.join(chrome, "Login Data"), 40_000)
mk(os.path.join(chrome, "Bookmarks"), 20_000)
for i in range(20):
    mk(os.path.join(LOCAL, "Microsoft", "Edge", "User Data", "Default", "Code Cache", "js", str(i)), 250_000)
    mk(os.path.join(ROAMING, "discord", "Cache", "Cache_Data", str(i)), 120_000)
for i in range(12):
    mk(os.path.join(LOCAL, "Microsoft", "Windows", "Explorer", f"thumbcache_{i}.db"), 80_000)
    mk(os.path.join(HOME, ".cache", "thumbnails", "large", f"{i}.png"), 80_000)
mk(os.path.join(WINDIR, "System32", "kernel32.dll"), 50_000)
mk(os.path.join(HOME, "Documents", "tesis.docx"), 300_000)
mk(os.path.join(HOME, "Documents", "presupuesto.xlsx"), 90_000)
mk(os.path.join(HOME, "Videos", "vacaciones_2023.mp4"), 180_000_000, sparse=True)
mk(os.path.join(HOME, "Videos", "boda", "ceremonia.mov"), 120_000_000, sparse=True)
mk(os.path.join(DOWNLOADS, "instalador_juego.iso"), 350_000_000, sparse=True, old=True)
mk(os.path.join(DOWNLOADS, "backup_movil.zip"), 90_000_000, sparse=True, old=True)
for name, size in (("factura_luz.pdf", 200_000), ("foto_dni.jpg", 900_000), ("setup_zoom.exe", 30_000_000),
                   ("cancion.mp3", 6_000_000), ("notas.txt", 2_000), ("captura.png", 400_000),
                   ("Discord.lnk", 1_000)):
    mk(os.path.join(DOWNLOADS, name), size, old=True)
mk(os.path.join(FAKE, "Games", "steamapps", "common", "Aventura", "data.pak"), 260_000_000, sparse=True)
photo = os.urandom(2_500_000)
for path in ("Pictures/IMG_2041.jpg", "Pictures/Copia/IMG_2041.jpg", "Downloads/IMG_2041 (1).jpg"):
    mk(os.path.join(HOME, *path.split("/")), 0, data=photo)
song = os.urandom(4_000_000)
for path in ("Music/tema.mp3", "Desktop/tema - copia.mp3"):
    mk(os.path.join(HOME, *path.split("/")), 0, data=song)

# --- Interfaz ---------------------------------------------------------------
from tkinter import messagebox  # noqa: E402

from limpiapc.gui import app as app_module  # noqa: E402

dialogs = []
messagebox.askyesno = lambda title, msg, **kw: (dialogs.append(("ask", title, msg)), True)[1]
messagebox.showinfo = lambda title, msg, **kw: dialogs.append(("info", title, msg))
messagebox.showwarning = lambda title, msg, **kw: dialogs.append(("warn", title, msg))
messagebox.showerror = lambda title, msg, **kw: dialogs.append(("error", title, msg))

app_module._prepare_windows_process()
app = app_module.App()
failures = []


def check(condition, text):
    print(("OK   " if condition else "FAIL ") + text, flush=True)
    if not condition:
        failures.append(text)


def shot(name):
    app.update_idletasks()
    app.update()
    path = os.path.join(SHOTS, name + ".png")
    try:
        if IS_WINDOWS:
            from PIL import ImageGrab

            x, y = app.winfo_rootx(), app.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height())).save(path)
        else:
            subprocess.run(["import", "-window", "root", path], check=True)
        print("captura", name, flush=True)
    except Exception as exc:  # noqa: BLE001
        print("sin captura", name, exc, flush=True)


def wait(cond, then, timeout=120, start=None):
    start = start or time.time()
    if cond():
        app.after(400, then)
        return
    if time.time() - start > timeout:
        check(False, "tiempo de espera agotado")
        app.after(10, then)
        return
    app.after(100, lambda: wait(cond, then, timeout, start))


pages = app.pages


def step(fn):
    def wrapper():
        try:
            fn()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            failures.append(f"excepción en {fn.__name__}")
            finish()
    return wrapper


@step
def s_dashboard():
    shot("01_resumen")
    app.analyze_space(FAKE)
    wait(lambda: not pages["space"].busy, s_space)


@step
def s_space():
    page = pages["space"]
    analysis = page.analysis
    check(analysis is not None and analysis.total_files > 100, "análisis de espacio con resultados")
    check(analysis.by_type["games"][0] == 260_000_000, "juegos detectados por carpeta (steamapps)")
    check(analysis.largest[0].name == "instalador_juego.iso", "el archivo más grande es la ISO")
    users = next(iid for iid, node in page.node_by_iid.items() if node.name == "Users")
    page.folder_tree.item(users, open=True)
    page.folder_tree.focus(users)
    page._expand(users)
    ana = next(iid for iid, node in page.node_by_iid.items() if node.name == "ana")
    page.folder_tree.item(ana, open=True)
    page._expand(ana)
    page.folder_tree.selection_set(ana)
    shot("02_espacio_carpetas")
    page.show_view("types")
    shot("03_espacio_tipos")
    page._show_type("video")
    check(all(f.type_id == "video" for f in page.file_by_iid.values()) and page.file_by_iid, "filtro por tipo")
    page._set_type_filter("all")
    first = page.files_tree.get_children()[0]
    page.files_tree.selection_set(first)
    shot("04_espacio_archivos")
    app.show("clean")
    pages["clean"].start_scan()
    wait(lambda: not pages["clean"].busy, s_clean_scanned)


@step
def s_clean_scanned():
    shot("05_limpieza_analizada")
    pages["clean"].start_clean()
    wait(lambda: not pages["clean"].busy, s_clean_done)


@step
def s_clean_done():
    shot("06_limpieza_hecha")
    if IS_WINDOWS:
        check(os.listdir(os.path.join(chrome, "Cache", "Cache_Data")) == [], "caché de Chrome vaciada")
        check(os.path.exists(os.path.join(chrome, "Login Data")), "contraseñas de Chrome intactas")
        check(os.path.exists(os.path.join(WINDIR, "System32", "kernel32.dll")), "System32 intacto")
    else:
        check(os.listdir(os.path.join(HOME, ".cache", "google-chrome", "Default", "Cache")) == [],
              "caché de Chrome vaciada")
    check(os.path.exists(os.path.join(HOME, "Documents", "tesis.docx")), "documentos intactos")
    check(not any(d[0] == "error" for d in dialogs), "sin errores durante la limpieza")
    page = pages["organize"]
    app.show("organize")
    page._set_folder(DOWNLOADS)
    check(len(page.plan) == 9, f"propuesta de organización con 9 archivos (hay {len(page.plan)})")
    shot("07_organizar_propuesta")
    page.apply()
    wait(lambda: not page.busy, s_organized)


@step
def s_organized():
    check(os.path.exists(os.path.join(DOWNLOADS, "Documentos", "factura_luz.pdf")), "PDF movido a Documentos")
    check(os.path.exists(os.path.join(DOWNLOADS, "Discord.lnk")), "accesos directos no se mueven")
    shot("08_organizar_hecho")
    page = pages["organize"]
    page.undo()
    wait(lambda: not page.busy, s_undone)


@step
def s_undone():
    check(os.path.exists(os.path.join(DOWNLOADS, "factura_luz.pdf")), "deshacer devuelve los archivos")
    check(not os.path.exists(os.path.join(DOWNLOADS, "Documentos")), "deshacer quita carpetas vacías creadas")
    page = pages["duplicates"]
    app.show("duplicates")
    page.folder = HOME
    page.size_var.set("1 MB")
    page.toggle()
    wait(lambda: not page.busy, s_duplicates)


@step
def s_duplicates():
    page = pages["duplicates"]
    check(len(page.groups) == 2, f"2 grupos de duplicados (hay {len(page.groups)})")
    check(len(page.drop) == 3, "se marcan para borrar todas las copias menos una")
    shot("09_duplicados")
    app.show("startup")
    app.after(500, s_startup)


@step
def s_startup():
    shot("10_inicio")
    app.show("tools")
    app.after(500, s_tools)


@step
def s_tools():
    shot("11_herramientas")
    app.show("dashboard")
    app.after(2500, s_final)


@step
def s_final():
    shot("12_resumen_final")
    finish()


def finish():
    for kind, title, message in dialogs:
        print("DIÁLOGO", kind, title, "|", message.replace("\n", " / ")[:200])
    print("RESULTADO:", "OK" if not failures else f"{len(failures)} fallos: {failures}", flush=True)
    app.destroy()


app.after(2500, s_dashboard)
app.mainloop()
sys.exit(1 if failures else 0)
