"""Organizar una carpeta en subcarpetas por tipo o por fecha (con deshacer)."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from collections import defaultdict
from datetime import datetime
from tkinter import filedialog, messagebox

from .. import APP_NAME, organizer
from ..platform_utils import format_count, human_size, open_target, user_folders
from .theme import C, F, px
from .widgets import FlatButton, Page, Segmented, elide, label, make_table, plural


class OrganizePage(Page):
    title = "Organizar archivos"
    subtitle = ("Ordena una carpeta desordenada (como Descargas o el Escritorio) en subcarpetas. Solo se mueven "
                "los archivos sueltos, no se borra nada, no se tocan accesos directos y puedes deshacerlo.")

    def __init__(self, app):
        super().__init__(app)
        self.cancel = threading.Event()
        self.busy = False
        self.mode = "type"
        self.plan: list[organizer.PlannedMove] = []
        folders = dict(user_folders())
        self.folder = folders.get("Descargas") or os.path.expanduser("~")

        row = tk.Frame(self.body, bg=C.bg)
        row.pack(fill="x")
        label(row, "Carpeta:", F.body, C.muted).pack(side="left")
        self.preview_btn = FlatButton(row, "Ver propuesta", self.preview)
        self.preview_btn.pack(side="right")
        self.mode_tabs = Segmented(row, [("type", "Por tipo"), ("date", "Por fecha")], self._set_mode)
        self.mode_tabs.pack(side="right", padx=(0, px(14)))
        label(row, "Ordenar:", F.body, C.muted).pack(side="right", padx=(px(16), px(8)))
        FlatButton(row, "Cambiar…", self._choose, kind="secondary", small=True).pack(side="right")
        self.folder_label = label(row, elide(self.folder, 52), F.body_bold, anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True, padx=(px(6), px(10)))

        shortcuts = user_folders()[1:]
        quick = tk.Frame(self.body, bg=C.bg)
        if shortcuts:
            quick.pack(fill="x", pady=(px(10), 0))
        label(quick, "Atajos:", F.small, C.faint).pack(side="left", padx=(0, px(6)))
        for name, path in shortcuts:
            FlatButton(quick, name, lambda p=path: self._set_folder(p), kind="secondary", small=True).pack(
                side="left", padx=(0, px(6)))

        self.status = label(self.body, "Elige una carpeta y pulsa «Ver propuesta». Todavía no se moverá nada.",
                            F.small, C.muted, anchor="w", justify="left")
        self.status.pack(fill="x", pady=(px(12), px(8)))

        table_box = tk.Frame(self.body, bg=C.bg)
        table_box.pack(fill="both", expand=True)
        self.tree = make_table(table_box, [("size", "Tamaño", 100, "e", False),
                                           ("modified", "Modificado", 110, "w", False)],
                               tree_column=("Destino y archivos", 520), selectmode="browse")
        self.tree.tag_configure("group", foreground=C.accent)

        actions = tk.Frame(self.body, bg=C.bg)
        actions.pack(fill="x", pady=(px(10), 0))
        self.apply_btn = FlatButton(actions, "Organizar ahora", self.apply)
        self.apply_btn.pack(side="left")
        self.undo_btn = FlatButton(actions, "Deshacer la última organización", self.undo, kind="secondary")
        self.undo_btn.pack(side="left", padx=(px(10), 0))
        self.open_btn = FlatButton(actions, "Abrir carpeta", lambda: open_target(self.folder), kind="secondary")
        self.open_btn.pack(side="right")
        self.apply_btn.set_enabled(False)
        self._refresh_undo()

    def on_show(self) -> None:
        self._refresh_undo()

    # ---------------------------------------------------------------- opciones
    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        if self.plan:
            self.preview()

    def _choose(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder, title="Elige la carpeta a organizar", parent=self)
        if chosen:
            self._set_folder(os.path.normpath(chosen))

    def _set_folder(self, path: str) -> None:
        self.folder = path
        self.folder_label.configure(text=elide(path, 52))
        self.plan = []
        self.tree.delete(*self.tree.get_children())
        self.apply_btn.set_enabled(False)
        self.preview()

    def _refresh_undo(self) -> None:
        record = organizer.last_record()
        self.undo_btn.set_enabled(record is not None and not self.busy)
        self._last_record = record

    # --------------------------------------------------------------- propuesta
    def preview(self) -> None:
        if self.busy:
            return
        problem = organizer.check_folder(self.folder)
        self.tree.delete(*self.tree.get_children())
        self.plan = []
        self.apply_btn.set_enabled(False)
        if problem:
            self.status.configure(text=problem, fg=C.warn)
            return
        self.plan = organizer.plan_organize(self.folder, self.mode)
        if not self.plan:
            self.status.configure(text="No hay archivos sueltos que ordenar en esta carpeta. ¡Ya está ordenada!",
                                  fg=C.muted)
            return
        groups: dict[str, list] = defaultdict(list)
        for move in self.plan:
            groups[move.dest_dir].append(move)
        for dest, moves in sorted(groups.items(), key=lambda kv: -sum(m.size for m in kv[1])):
            relative = os.path.relpath(dest, self.folder)
            text = f"  {relative}   ({plural(len(moves), 'archivo', 'archivos')})"
            group = self.tree.insert("", "end", text=text, open=len(groups) <= 3, tags=("group",),
                                     values=(human_size(sum(m.size for m in moves)), ""))
            for move in moves:
                try:
                    modified = datetime.fromtimestamp(os.path.getmtime(move.src)).strftime("%d/%m/%Y")
                except OSError:
                    modified = ""
                self.tree.insert(group, "end", text=f"  {move.name}", values=(human_size(move.size), modified))
        total = sum(m.size for m in self.plan)
        self.status.configure(
            text=f"Propuesta: mover {plural(len(self.plan), 'archivo', 'archivos')} ({human_size(total)}) a "
                 f"{plural(len(groups), 'carpeta', 'carpetas')}. Despliega cada carpeta para revisar. "
                 "Si te parece bien, pulsa «Organizar ahora».", fg=C.text)
        self.apply_btn.set_enabled(True)

    # ------------------------------------------------------------------ aplicar
    def apply(self) -> None:
        if self.busy or not self.plan:
            return
        if not messagebox.askyesno(
                "Organizar", f"¿Mover {plural(len(self.plan), 'archivo', 'archivos')} a sus nuevas carpetas "
                             f"dentro de\n{self.folder}?\n\nPodrás deshacerlo después.", parent=self):
            return
        self.busy = True
        self.apply_btn.set_enabled(False)
        self.undo_btn.set_enabled(False)
        plan, folder, mode = list(self.plan), self.folder, self.mode
        self.cancel.clear()

        def progress(done):
            if done % 25 == 0:
                self.app.post(self.status.configure, text=f"Moviendo… {done} de {len(plan)}")

        self.app.run_bg(lambda: organizer.apply_plan(folder, plan, mode, self.cancel, progress),
                        self._applied, self._failed)

    def _applied(self, record: dict) -> None:
        self.busy = False
        moved = len(record["moves"])
        text = f"¡Listo! Se ordenaron {plural(moved, 'archivo', 'archivos')}."
        if record["errors"]:
            text += f" {len(record['errors'])} no se pudieron mover (¿estaban abiertos?)."
        self.plan = []
        self.tree.delete(*self.tree.get_children())
        self.status.configure(text=text + " Si no te convence, pulsa «Deshacer».", fg=C.accent)
        self._refresh_undo()
        if record["errors"]:
            messagebox.showwarning(APP_NAME, "No se pudieron mover:\n\n" + "\n".join(record["errors"][:10]),
                                   parent=self)

    def _failed(self, exc: Exception) -> None:
        self.busy = False
        self.status.configure(text=f"Error: {exc}", fg=C.danger)
        self._refresh_undo()

    def undo(self) -> None:
        record = organizer.last_record()
        if record is None or self.busy:
            return
        count = len(record.get("moves", []))
        when = record.get("date", "").replace("T", " a las ")
        if not messagebox.askyesno(
                "Deshacer", f"¿Devolver {plural(count, 'archivo', 'archivos')} a su sitio original en\n"
                            f"{record.get('folder')}?\n\n(Organización del {when})", parent=self):
            return
        self.busy = True
        self.undo_btn.set_enabled(False)

        def done(result):
            restored, errors = result
            self.busy = False
            self.status.configure(text=f"Deshecho: {format_count(restored)} archivos han vuelto a su sitio.",
                                  fg=C.accent)
            self._refresh_undo()
            if errors:
                messagebox.showwarning(APP_NAME, "Algunos no se pudieron devolver:\n\n" + "\n".join(errors[:10]),
                                       parent=self)

        self.app.run_bg(lambda: organizer.undo(record), done, self._failed)
