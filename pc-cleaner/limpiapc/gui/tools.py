"""Accesos directos a herramientas oficiales de Windows."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .. import APP_NAME
from ..platform_utils import IS_WINDOWS, decode_output, open_target, run_elevated, run_quiet, shell_open
from .theme import C, F, px
from .widgets import FlatButton, Page, card, label


def launch(args: list[str]) -> None:
    try:
        ok = shell_open(args[0], " ".join(args[1:]))
    except OSError as exc:
        ok, detail = False, str(exc)
    else:
        detail = "Windows no pudo abrirlo o se canceló."
    if not ok:
        messagebox.showerror(APP_NAME, f"No se pudo abrir {args[0]}:\n{detail}")


def open_uri(uri: str) -> None:
    try:
        open_target(uri)
    except OSError as exc:
        messagebox.showerror(APP_NAME, f"No se pudo abrir:\n{exc}")


class ToolsPage(Page):
    title = "Herramientas de Windows"
    subtitle = "Accesos directos a las herramientas oficiales de Windows que de verdad ayudan."

    def __init__(self, app):
        super().__init__(app)
        if not IS_WINDOWS:
            label(self.body, "Estas herramientas solo están disponibles en Windows.", F.body, C.muted).pack(anchor="w")
            return
        tools = [
            ("Desinstalar programas", "Quitar lo que ya no usas es lo que más espacio y velocidad recupera.",
             "Abrir", lambda: open_uri("ms-settings:appsfeatures")),
            ("Liberador de espacio en disco", "La limpieza oficial de Windows: incluye restos de actualizaciones "
             "y versiones anteriores de Windows.", "Abrir", lambda: launch(["cleanmgr"])),
            ("Sensor de almacenamiento", "Haz que Windows borre temporales y vacíe la papelera automáticamente.",
             "Configurar", lambda: open_uri("ms-settings:storagesense")),
            ("Optimizar unidades", "Desfragmenta discos duros y aplica TRIM a los SSD.",
             "Abrir", lambda: launch(["dfrgui"])),
            ("Administrador de tareas", "Mira qué está usando la CPU, la memoria o el disco ahora mismo.",
             "Abrir", lambda: launch(["taskmgr"])),
            ("Vaciar caché DNS", "Puede arreglar páginas que no cargan después de cambiar de red.",
             "Vaciar", self._flush_dns),
            ("Reparar archivos de Windows", "Ejecuta «sfc /scannow» para buscar y reparar archivos del sistema "
             "dañados. Tarda varios minutos y pide permiso de administrador.", "Ejecutar", self._run_sfc),
            ("Opciones de energía", "En un PC de sobremesa, el plan «Alto rendimiento» puede dar algo más de velocidad.",
             "Abrir", lambda: launch(["control", "powercfg.cpl"])),
        ]
        grid = tk.Frame(self.body, bg=C.bg)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1, uniform="tools")
        grid.columnconfigure(1, weight=1, uniform="tools")
        for index, (title, description, action, command) in enumerate(tools):
            box = card(grid, padx=16, pady=14)
            box.grid(row=index // 2, column=index % 2, sticky="nsew",
                     padx=(0 if index % 2 == 0 else px(6), px(6) if index % 2 == 0 else 0), pady=(0, px(12)))
            box.columnconfigure(0, weight=1)
            label(box, title, F.body_bold).grid(row=0, column=0, sticky="w")
            desc = label(box, description, F.small, C.muted, justify="left", anchor="w")
            desc.grid(row=1, column=0, sticky="we", pady=(px(3), 0))
            box.bind("<Configure>", lambda e, d=desc: d.configure(wraplength=max(px(150), e.width - px(150))))
            FlatButton(box, action, command, kind="secondary", small=True).grid(
                row=0, column=1, rowspan=2, sticky="e", padx=(px(12), 0))

    def _flush_dns(self):
        def work():
            result = run_quiet(["ipconfig", "/flushdns"])
            return result.returncode, decode_output(result.stdout).strip()

        def done(result):
            code, output = result
            if code == 0:
                messagebox.showinfo(APP_NAME, "Caché DNS vaciada correctamente.", parent=self)
            else:
                messagebox.showwarning(APP_NAME, output or "No se pudo vaciar la caché DNS.", parent=self)

        self.app.run_bg(work, done)

    def _run_sfc(self):
        if not run_elevated("cmd.exe", "/k sfc /scannow"):
            messagebox.showinfo(APP_NAME, "No se concedieron permisos de administrador.", parent=self)
