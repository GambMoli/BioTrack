"""Programas que arrancan con Windows."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .. import APP_NAME, startup
from ..platform_utils import IS_WINDOWS
from .theme import C, F, px
from .tools import launch
from .widgets import FlatButton, Page, label, make_table


class StartupPage(Page):
    title = "Programas al iniciar"
    subtitle = ("Cuantos menos programas arranquen con el equipo, antes estará listo para usar. "
                "Deshabilitar no desinstala nada y puedes volver a activarlos cuando quieras.")

    def __init__(self, app):
        super().__init__(app)
        self.items: dict[str, startup.StartupItem] = {}

        table_box = tk.Frame(self.body, bg=C.bg)
        table_box.pack(fill="both", expand=True)
        self.tree = make_table(table_box, [("name", "Programa", 220, "w", True), ("state", "Estado", 110, "w", False),
                                           ("scope", "Para", 140, "w", False), ("command", "Comando", 420, "w", True)],
                               selectmode="browse")
        self.tree.tag_configure("disabled", foreground=C.faint)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_buttons())
        self.tree.bind("<Double-1>", lambda e: self._toggle())

        actions = tk.Frame(self.body, bg=C.bg)
        actions.pack(fill="x", pady=(px(10), 0))
        self.toggle_btn = FlatButton(actions, "Deshabilitar", self._toggle)
        self.toggle_btn.pack(side="left")
        FlatButton(actions, "Actualizar", self.refresh, kind="secondary").pack(side="left", padx=(px(10), 0))
        if IS_WINDOWS:
            FlatButton(actions, "Abrir Administrador de tareas", lambda: launch(["taskmgr", "/0", "/startup"]),
                       kind="secondary").pack(side="left", padx=(px(10), 0))
        self.note = label(actions, "", F.small, C.muted)
        self.note.pack(side="right")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        try:
            items = startup.list_startup_items(self.app.admin)
        except Exception as exc:  # noqa: BLE001
            self.note.configure(text=f"No se pudo leer la lista: {exc}")
            items = []
        for index, item in enumerate(items):
            iid = f"item{index}"
            self.items[iid] = item
            self.tree.insert("", "end", iid=iid, tags=() if item.enabled else ("disabled",),
                             values=(item.name, "Habilitado" if item.enabled else "Deshabilitado",
                                     item.scope, item.command))
        enabled = sum(1 for i in items if i.enabled)
        if not IS_WINDOWS:
            self.note.configure(text="Fuera de Windows esta lista es solo informativa.")
        elif items:
            self.note.configure(text=f"{enabled} de {len(items)} programas arrancan con Windows.")
        else:
            self.note.configure(text="No hay programas configurados para iniciar.")
        self._update_buttons()

    def _current(self) -> startup.StartupItem | None:
        selection = self.tree.selection()
        return self.items.get(selection[0]) if selection else None

    def _update_buttons(self):
        item = self._current()
        if item is None:
            self.toggle_btn.configure(text="Deshabilitar")
            self.toggle_btn.set_enabled(False)
            return
        self.toggle_btn.configure(text="Habilitar" if not item.enabled else "Deshabilitar")
        self.toggle_btn.set_enabled(item.can_toggle)

    def _toggle(self):
        item = self._current()
        if item is None:
            return
        if not item.can_toggle:
            message = ("Este programa está configurado para todos los usuarios: abre LimpiaPC como "
                       "administrador para cambiarlo.") if IS_WINDOWS else "No se puede cambiar desde aquí."
            messagebox.showinfo(APP_NAME, message, parent=self)
            return
        try:
            startup.set_enabled(item, not item.enabled)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"No se pudo cambiar:\n{exc}", parent=self)
            return
        iid = self.tree.selection()[0]
        self.tree.item(iid, tags=() if item.enabled else ("disabled",),
                       values=(item.name, "Habilitado" if item.enabled else "Deshabilitado", item.scope, item.command))
        self._update_buttons()
        self.note.configure(text="Hecho. El cambio se aplicará la próxima vez que inicies sesión.")
