"""Archivos duplicados: encontrar copias exactas y quedarse con una."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from .. import APP_NAME, duplicates, trash
from ..platform_utils import format_count, human_size, reveal_in_file_manager
from .theme import C, F, px
from .widgets import FlatButton, Page, elide, label, make_table, plural


class DuplicatesPage(Page):
    title = "Archivos duplicados"
    subtitle = ("Encuentra copias exactas del mismo archivo (aunque tengan otro nombre) y quédate solo con una. "
                "Las copias van a la papelera, así que puedes recuperarlas.")
    SIZES = {"1 MB": 1, "10 MB": 10, "50 MB": 50, "100 MB": 100}

    def __init__(self, app):
        super().__init__(app)
        self.folder = os.path.expanduser("~")
        self.cancel = threading.Event()
        self.busy = False
        self.groups: list[duplicates.DuplicateGroup] = []
        self.file_rows: dict[str, tuple[int, int]] = {}   # iid -> (grupo, índice)
        self.drop: set[tuple[int, int]] = set()            # archivos marcados para la papelera

        row = tk.Frame(self.body, bg=C.bg)
        row.pack(fill="x")
        label(row, "Carpeta:", F.body, C.muted).pack(side="left")
        self.search_btn = FlatButton(row, "Buscar", self.toggle)
        self.search_btn.pack(side="right")
        self.size_var = tk.StringVar(value="1 MB")
        ttk.Combobox(row, textvariable=self.size_var, values=list(self.SIZES), state="readonly", width=7,
                     font=F.body).pack(side="right", padx=(0, px(14)))
        label(row, "Mayores de:", F.body, C.muted).pack(side="right", padx=(px(16), px(6)))
        FlatButton(row, "Cambiar…", self._choose, kind="secondary", small=True).pack(side="right")
        self.folder_label = label(row, elide(self.folder, 52), F.body_bold, anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True, padx=(px(6), px(10)))

        status = tk.Frame(self.body, bg=C.bg)
        status.pack(fill="x", pady=(px(12), px(8)))
        self.progress = ttk.Progressbar(status, style="Accent.Horizontal.TProgressbar", mode="determinate")
        self.status = label(status, "Pulsa «Buscar». Revisar muchos archivos grandes puede tardar unos minutos.",
                            F.small, C.muted, anchor="w", justify="left")
        self.status.pack(fill="x")

        table_box = tk.Frame(self.body, bg=C.bg)
        table_box.pack(fill="both", expand=True)
        self.tree = make_table(table_box, [("action", "Qué hacer", 120, "w", False),
                                           ("size", "Tamaño", 90, "e", False),
                                           ("modified", "Modificado", 100, "w", False),
                                           ("folder", "Carpeta", 380, "w", True)],
                               tree_column=("Archivo", 300), selectmode="browse")
        self.tree.tag_configure("group", foreground=C.text)
        self.tree.tag_configure("keep", foreground=C.accent)
        self.tree.tag_configure("drop", foreground=C.danger_hover)
        self.tree.bind("<ButtonRelease-1>", self._clicked)
        self.tree.bind("<Double-1>", self._reveal)

        actions = tk.Frame(self.body, bg=C.bg)
        actions.pack(fill="x", pady=(px(10), 0))
        self.trash_btn = FlatButton(actions, "Enviar copias a la papelera", self._trash, kind="danger")
        self.trash_btn.pack(side="left")
        self.auto_btn = FlatButton(actions, "Conservar el más antiguo de cada grupo", self._auto_mark,
                                   kind="secondary")
        self.auto_btn.pack(side="left", padx=(px(10), 0))
        self._update_buttons()

    def _choose(self) -> None:
        if self.busy:
            return
        chosen = filedialog.askdirectory(initialdir=self.folder, title="¿Dónde busco duplicados?", parent=self)
        if chosen:
            self.folder = os.path.normpath(chosen)
            self.folder_label.configure(text=elide(self.folder, 52))

    # ---------------------------------------------------------------- búsqueda
    def toggle(self) -> None:
        if self.busy:
            self.cancel.set()
            self.status.configure(text="Deteniendo…")
            return
        self.busy = True
        self.cancel.clear()
        self.search_btn.configure(text="Detener")
        self.tree.delete(*self.tree.get_children())
        self.groups, self.drop = [], set()
        self.file_rows.clear()
        self._update_buttons()
        self.progress.configure(value=0, maximum=1)
        self.progress.pack(fill="x", pady=(0, px(6)), before=self.status)
        folder, min_size = self.folder, self.SIZES[self.size_var.get()] * 1024 * 1024

        def progress(phase, done, total):
            if phase == "buscar":
                self.app.post(self.status.configure, text=f"Buscando archivos… {format_count(done)} revisados")
            else:
                self.app.post(self.progress.configure, maximum=max(1, total), value=done)
                self.app.post(self.status.configure,
                              text=f"Comparando contenido… {format_count(done)} de {format_count(total)} candidatos")

        self.app.run_bg(lambda: duplicates.find_duplicates(folder, min_size, cancel=self.cancel, progress=progress),
                        self._done, self._failed)

    def _finish(self) -> None:
        self.busy = False
        self.search_btn.configure(text="Buscar")
        self.progress.pack_forget()

    def _failed(self, exc: Exception) -> None:
        self._finish()
        self.status.configure(text=f"Error: {exc}")

    def _done(self, result) -> None:
        self._finish()
        self.groups, scanned = result
        stopped = " (búsqueda detenida)" if self.cancel.is_set() else ""
        if not self.groups:
            self.status.configure(text=f"No hay duplicados aquí. Revisados {format_count(scanned)} archivos{stopped}.")
            return
        wasted = sum(g.wasted for g in self.groups)
        self.status.configure(
            text=f"{plural(len(self.groups), 'grupo', 'grupos')} de archivos repetidos: {human_size(wasted)} "
                 f"ocupados por copias (revisados {format_count(scanned)} archivos{stopped}). "
                 "Se propone conservar el más antiguo; haz clic en un archivo para cambiarlo.")
        self._auto_mark()

    # ----------------------------------------------------------------- marcas
    def _auto_mark(self) -> None:
        self.drop = {(g, i) for g, group in enumerate(self.groups[:500]) for i in range(1, len(group.files))}
        self._fill()

    def _fill(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.file_rows.clear()
        for g, group in enumerate(self.groups[:500]):
            first = group.files[0]
            parent = self.tree.insert(
                "", "end", open=g < 30, tags=("group",),
                text=f"  {first.name}",
                values=(f"{len(group.files)} copias", human_size(group.size), "",
                        f"{human_size(group.wasted)} se pueden liberar"))
            for i, item in enumerate(group.files):
                iid = f"g{g}f{i}"
                self.file_rows[iid] = (g, i)
                dropping = (g, i) in self.drop
                self.tree.insert(parent, "end", iid=iid, text=f"  {item.name}",
                                 tags=("drop" if dropping else "keep",),
                                 values=("✗ A la papelera" if dropping else "✓ Conservar", human_size(group.size),
                                         datetime.fromtimestamp(item.mtime).strftime("%d/%m/%Y"),
                                         os.path.dirname(item.path)))
        self._update_buttons()

    def _clicked(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid not in self.file_rows or self.tree.identify_region(event.x, event.y) == "heading":
            return
        g, i = self.file_rows[iid]
        if (g, i) in self.drop:
            self.drop.discard((g, i))
        else:
            kept = [j for j in range(len(self.groups[g].files)) if (g, j) not in self.drop and j != i]
            if not kept:
                messagebox.showinfo(APP_NAME, "Hay que conservar al menos una copia de cada archivo.", parent=self)
                return
            self.drop.add((g, i))
        dropping = (g, i) in self.drop
        self.tree.item(iid, tags=("drop" if dropping else "keep",))
        self.tree.set(iid, "action", "✗ A la papelera" if dropping else "✓ Conservar")
        self._update_buttons()

    def _reveal(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid in self.file_rows:
            g, i = self.file_rows[iid]
            try:
                reveal_in_file_manager(self.groups[g].files[i].path)
            except OSError:
                pass

    def _update_buttons(self) -> None:
        size = sum(self.groups[g].size for g, _ in self.drop)
        self.trash_btn.set_enabled(bool(self.drop) and not self.busy)
        self.auto_btn.set_enabled(bool(self.groups))
        self.trash_btn.configure(text=f"Enviar copias a la papelera ({human_size(size)})" if self.drop
                                 else "Enviar copias a la papelera")

    # ------------------------------------------------------------------ borrar
    def _trash(self) -> None:
        if not self.drop:
            return
        items = sorted(self.drop)
        size = sum(self.groups[g].size for g, _ in items)
        if not messagebox.askyesno(
                "Enviar copias a la papelera",
                f"¿Enviar {plural(len(items), 'copia', 'copias')} ({human_size(size)}) a la papelera?\n\n"
                "De cada archivo se conserva al menos una copia.", icon="warning", parent=self):
            return
        targets = [(g, i, self.groups[g].files[i].path) for g, i in items]

        def work():
            done, errors = [], []
            for g, i, path in targets:
                try:
                    trash.send_to_trash(path)
                    done.append((g, i))
                except OSError as exc:
                    errors.append(f"{os.path.basename(path)}: {exc}")
            return done, errors

        self.app.run_bg(work, self._trashed)

    def _trashed(self, result) -> None:
        done, errors = result
        freed = sum(self.groups[g].size for g, _ in done)
        removed = set(done)
        new_groups = []
        for g, group in enumerate(self.groups):
            remaining = [f for i, f in enumerate(group.files) if (g, i) not in removed]
            if len(remaining) > 1:
                new_groups.append(duplicates.DuplicateGroup(group.size, remaining))
        self.groups = new_groups
        self.drop = set()
        self._fill()
        self.status.configure(text=f"Enviadas a la papelera {plural(len(done), 'copia', 'copias')} "
                                   f"({human_size(freed)}). Vacía la papelera para liberar el espacio.")
        if errors:
            messagebox.showwarning(APP_NAME, "Algunas copias no se pudieron mover:\n\n" + "\n".join(errors[:10]),
                                   parent=self)
