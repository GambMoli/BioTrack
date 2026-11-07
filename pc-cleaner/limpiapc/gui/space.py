"""Análisis de espacio: qué carpetas, qué tipos de archivo y qué archivos ocupan el disco."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from .. import APP_NAME, analyzer, system_info, trash
from ..cleaner import is_within, norm
from ..filetypes import FILE_TYPES, TYPES_BY_ID
from ..fileops import move_file
from ..largefiles import is_system_path
from ..platform_utils import format_count, human_size, open_target, reveal_in_file_manager, user_folders
from .theme import C, F, bar_image, px
from .widgets import FlatButton, Page, Segmented, StackedBar, elide, label, make_table, plural

CHOOSE = "Elegir otra carpeta…"


class SpacePage(Page):
    title = "Análisis de espacio"
    subtitle = ("Descubre qué está llenando tu disco: carpetas, tipos de archivo y los archivos más pesados. "
                "Solo mira; no cambia nada hasta que tú lo decidas.")

    def __init__(self, app):
        super().__init__(app)
        self.analysis: analyzer.Analysis | None = None
        self.node_by_iid: dict[str, analyzer.DirNode] = {}
        self.file_by_iid: dict[str, analyzer.FoundFile] = {}
        self.cancel = threading.Event()
        self.busy = False
        self.type_filter = "all"
        self.folder_filter: str | None = None

        # ----------------------------------------------------------- controles
        controls = tk.Frame(self.body, bg=C.bg)
        controls.pack(fill="x")
        label(controls, "Analizar:", F.body, C.muted).pack(side="left")
        self.locations: dict[str, str] = {}
        self.location_var = tk.StringVar()
        self.location_box = ttk.Combobox(controls, textvariable=self.location_var, state="readonly",
                                         width=42, font=F.body)
        self.location_box.pack(side="left", padx=(px(8), px(10)))
        self.location_box.bind("<<ComboboxSelected>>", self._location_selected)
        self.start_btn = FlatButton(controls, "Analizar", self.toggle)
        self.start_btn.pack(side="left")
        self._fill_locations()

        status = tk.Frame(self.body, bg=C.bg)
        status.pack(fill="x", pady=(px(12), px(8)))
        self.progress = ttk.Progressbar(status, style="Accent.Horizontal.TProgressbar", mode="indeterminate")
        self.status = label(status, "Elige un disco o una carpeta y pulsa «Analizar». "
                                    "Un disco entero puede tardar uno o dos minutos.", F.small, C.muted,
                            anchor="w", justify="left")
        self.status.pack(fill="x")

        tabs_row = tk.Frame(self.body, bg=C.bg)
        tabs_row.pack(fill="x", pady=(0, px(10)))
        self.tabs = Segmented(tabs_row, [("folders", "Por carpetas"), ("types", "Por tipo"),
                                         ("files", "Archivos más grandes")], self.show_view)
        self.tabs.pack(side="left")
        self.summary = label(tabs_row, "", F.body_bold, C.accent)
        self.summary.pack(side="right")

        self.views_frame = tk.Frame(self.body, bg=C.bg)
        self.views_frame.pack(fill="both", expand=True)
        self.views = {"folders": self._build_folders_view(), "types": self._build_types_view(),
                      "files": self._build_files_view()}
        self.show_view("folders")

    # =================================================================== vistas
    def show_view(self, key: str) -> None:
        for name, frame in self.views.items():
            if name == key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        self.tabs.select(key)

    def _build_folders_view(self) -> tk.Frame:
        frame = tk.Frame(self.views_frame, bg=C.bg)
        table_box = tk.Frame(frame, bg=C.bg)
        table_box.pack(fill="both", expand=True)
        self.folder_tree = make_table(
            table_box,
            [("size", "Tamaño", 100, "e", False), ("pct", "% de su carpeta", 110, "e", False),
             ("files", "Archivos", 100, "e", False)],
            tree_column=("Carpeta", 380), selectmode="browse")
        self.folder_tree.tag_configure("denied", foreground=C.faint)
        self.folder_tree.tag_configure("loose", foreground=C.muted)
        self.folder_tree.bind("<<TreeviewOpen>>", self._on_open)
        self.folder_tree.bind("<Double-1>", lambda e: self._open_folder())
        actions = tk.Frame(frame, bg=C.bg)
        actions.pack(fill="x", pady=(px(10), 0))
        FlatButton(actions, "Abrir carpeta", self._open_folder, kind="secondary").pack(side="left")
        FlatButton(actions, "Ver sus archivos más grandes", self._files_of_folder, kind="secondary").pack(
            side="left", padx=(px(10), 0))
        label(actions, "Despliega las carpetas con ▸ para ver qué hay dentro.", F.small, C.muted).pack(side="right")
        return frame

    def _build_types_view(self) -> tk.Frame:
        frame = tk.Frame(self.views_frame, bg=C.bg)
        self.stacked = StackedBar(frame, C.bg, height=24)
        self.stacked.pack(fill="x", pady=(px(4), px(14)))
        self.types_list = tk.Frame(frame, bg=C.bg)
        self.types_list.pack(fill="both", expand=True)
        label(self.types_list, "Analiza un disco o carpeta para ver el reparto por tipo.", F.body, C.muted).pack(anchor="w")
        return frame

    def _build_files_view(self) -> tk.Frame:
        frame = tk.Frame(self.views_frame, bg=C.bg)
        filters = tk.Frame(frame, bg=C.bg)
        filters.pack(fill="x", pady=(0, px(8)))
        label(filters, "Tipo:", F.body, C.muted).pack(side="left")
        self.type_names = {"Todos": "all", **{t.name: t.id for t in FILE_TYPES}}
        self.type_var = tk.StringVar(value="Todos")
        type_box = ttk.Combobox(filters, textvariable=self.type_var, values=list(self.type_names),
                                state="readonly", width=30, font=F.body)
        type_box.pack(side="left", padx=(px(6), px(16)))
        type_box.bind("<<ComboboxSelected>>", lambda e: self._set_type_filter(self.type_names[self.type_var.get()]))
        self.folder_filter_label = label(filters, "", F.small, C.muted)
        self.folder_filter_label.pack(side="left")
        self.clear_folder_btn = FlatButton(filters, "Quitar filtro", lambda: self._set_folder_filter(None),
                                           kind="secondary", small=True)

        table_box = tk.Frame(frame, bg=C.bg)
        table_box.pack(fill="both", expand=True)
        self.files_tree = make_table(
            table_box,
            [("name", "Nombre", 240, "w", True), ("type", "Tipo", 185, "w", False),
             ("size", "Tamaño", 90, "e", False), ("modified", "Modificado", 100, "w", False),
             ("folder", "Carpeta", 330, "w", True)])
        self.files_tree.bind("<<TreeviewSelect>>", lambda e: self._update_file_buttons())
        self.files_tree.bind("<Double-1>", lambda e: self._reveal())
        self.files_tree.bind("<Delete>", lambda e: self._trash())

        actions = tk.Frame(frame, bg=C.bg)
        actions.pack(fill="x", pady=(px(10), 0))
        self.reveal_btn = FlatButton(actions, "Abrir ubicación", self._reveal, kind="secondary")
        self.reveal_btn.pack(side="left")
        self.move_btn = FlatButton(actions, "Mover a…", self._move, kind="secondary")
        self.move_btn.pack(side="left", padx=(px(10), 0))
        self.trash_btn = FlatButton(actions, "Enviar a la papelera", self._trash, kind="danger")
        self.trash_btn.pack(side="left", padx=(px(10), 0))
        self.selection_label = label(actions, "", F.body, C.muted)
        self.selection_label.pack(side="right")
        self._update_file_buttons()
        return frame

    # =============================================================== ubicación
    def _fill_locations(self, extra: str | None = None) -> None:
        self.locations.clear()
        for disk in system_info.get_disks():
            self.locations[f"{disk.label} — {human_size(disk.used)} usados"] = disk.mount
        for name, path in user_folders():
            self.locations[f"{name} ({elide(path, 40)})"] = path
        if extra:
            self.locations[elide(extra, 60)] = extra
        self.locations[CHOOSE] = ""
        self.location_box.configure(values=list(self.locations))
        if extra:
            self.location_var.set(elide(extra, 60))
        elif not self.location_var.get() or self.location_var.get() not in self.locations:
            self.location_var.set(next(iter(self.locations)))

    def _location_selected(self, _event=None) -> None:
        if self.location_var.get() == CHOOSE:
            chosen = filedialog.askdirectory(title="Elige la carpeta a analizar", parent=self)
            if chosen:
                self._fill_locations(os.path.normpath(chosen))
            else:
                self.location_var.set(next(iter(self.locations)))

    def set_location(self, path: str) -> None:
        for text, value in self.locations.items():
            if value and norm(value) == norm(path):
                self.location_var.set(text)
                return
        self._fill_locations(path)

    # ================================================================ análisis
    def toggle(self) -> None:
        if self.busy:
            self.cancel.set()
            self.status.configure(text="Deteniendo…")
            return
        path = self.locations.get(self.location_var.get())
        if not path:
            self._location_selected()
            return
        self.start(path)

    def start(self, path: str | None = None) -> None:
        if self.busy:
            return
        path = path or self.locations.get(self.location_var.get())
        if not path:
            return
        self.busy = True
        self.cancel.clear()
        self.start_btn.configure(text="Detener")
        self.progress.pack(fill="x", pady=(0, px(6)), before=self.status)
        self.progress.start(12)
        self.status.configure(text=f"Analizando {path}…")

        def progress(files, size, current):
            self.app.post(self.status.configure,
                          text=f"Analizando… {format_count(files)} archivos, {human_size(size)} — {elide(current, 70)}")

        self.app.run_bg(lambda: analyzer.analyze(path, cancel=self.cancel, progress=progress),
                        self._done, self._failed)

    def _finish(self) -> None:
        self.busy = False
        self.start_btn.configure(text="Analizar")
        self.progress.stop()
        self.progress.pack_forget()

    def _failed(self, exc: Exception) -> None:
        self._finish()
        self.status.configure(text=f"Error: {exc}")

    def _done(self, analysis: analyzer.Analysis) -> None:
        self._finish()
        self.analysis = analysis
        self.type_filter, self.folder_filter = "all", None
        self.type_var.set("Todos")
        text = (f"{format_count(analysis.total_files)} archivos en {format_count(analysis.total_dirs)} carpetas, "
                f"analizados en {analysis.seconds:.0f} s.")
        if analysis.cancelled:
            text = "Análisis detenido: resultados parciales. " + text
        if analysis.denied:
            text += (f" {plural(analysis.denied, 'carpeta', 'carpetas')} sin permiso de lectura"
                     " (abre LimpiaPC como administrador para incluirlas).")
        self.status.configure(text=text)
        self.summary.configure(text=f"Total: {human_size(analysis.total_size)}")
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._fill_folders()
        self._fill_types()
        self._fill_files()

    # ---------------------------------------------------------- por carpetas
    def _node_values(self, node: analyzer.DirNode, parent_size: int):
        fraction = node.size / parent_size if parent_size else 1.0
        return fraction, (human_size(node.size), f"{fraction * 100:.0f} %", format_count(node.files))

    def _insert_node(self, parent_iid: str, node: analyzer.DirNode, parent_size: int, open_: bool = False):
        fraction, values = self._node_values(node, parent_size)
        iid = f"d{len(self.node_by_iid)}"
        self.node_by_iid[iid] = node
        name = node.name + ("  (sin acceso)" if node.denied else "")
        self.folder_tree.insert(parent_iid, "end", iid=iid, text=f"  {name}", values=values, open=open_,
                                image=bar_image(fraction), tags=("denied",) if node.denied else ())
        if node.children:
            self.folder_tree.insert(iid, "end", iid=iid + ":ph", text="…")
        return iid

    def _fill_folders(self) -> None:
        tree = self.folder_tree
        tree.delete(*tree.get_children())
        self.node_by_iid.clear()
        if not self.analysis:
            return
        root_iid = self._insert_node("", self.analysis.root, self.analysis.root.size, open_=True)
        self._expand(root_iid)

    def _expand(self, iid: str) -> None:
        placeholder = iid + ":ph"
        if not self.folder_tree.exists(placeholder):
            return
        self.folder_tree.delete(placeholder)
        node = self.node_by_iid[iid]
        children = node.sorted_children()
        limit = 300
        for child in children[:limit]:
            if child.size or child.denied:
                self._insert_node(iid, child, node.size)
        if len(children) > limit:
            rest = children[limit:]
            self.folder_tree.insert(iid, "end", text=f"  … y {len(rest)} carpetas más",
                                    values=(human_size(sum(c.size for c in rest)), "", ""), tags=("loose",))
        if node.own_files:
            fraction = node.own_size / node.size if node.size else 0
            self.folder_tree.insert(iid, "end", text="  (archivos sueltos en esta carpeta)",
                                    image=bar_image(fraction, C.faint), tags=("loose",),
                                    values=(human_size(node.own_size), f"{fraction * 100:.0f} %",
                                            format_count(node.own_files)))

    def _on_open(self, _event=None) -> None:
        iid = self.folder_tree.focus()
        if iid in self.node_by_iid:
            self._expand(iid)

    def _selected_node(self) -> analyzer.DirNode | None:
        selection = self.folder_tree.selection()
        if not selection:
            return None
        iid = selection[0]
        if iid not in self.node_by_iid:
            parent = self.folder_tree.parent(iid)  # fila de "archivos sueltos"
            return self.node_by_iid.get(parent)
        return self.node_by_iid[iid]

    def _open_folder(self) -> None:
        node = self._selected_node()
        if node:
            try:
                open_target(node.path)
            except OSError as exc:
                messagebox.showerror(APP_NAME, f"No se pudo abrir la carpeta:\n{exc}", parent=self)

    def _files_of_folder(self) -> None:
        node = self._selected_node()
        if node:
            self._set_folder_filter(node.path)
            self.show_view("files")

    # --------------------------------------------------------------- por tipo
    def _fill_types(self) -> None:
        for child in self.types_list.winfo_children():
            child.destroy()
        if not self.analysis:
            return
        total = self.analysis.total_size or 1
        rows = sorted(((TYPES_BY_ID[tid], size, count) for tid, (size, count) in self.analysis.by_type.items()
                       if size > 0), key=lambda r: r[1], reverse=True)
        self.stacked.set([(size, ftype.color) for ftype, size, _ in rows])
        self.types_list.columnconfigure(1, weight=1)
        for index, (ftype, size, count) in enumerate(rows):
            swatch = tk.Frame(self.types_list, bg=ftype.color, width=px(14), height=px(14))
            swatch.grid(row=index, column=0, padx=(0, px(10)), pady=px(6))
            label(self.types_list, ftype.name, F.body_bold).grid(row=index, column=1, sticky="w")
            label(self.types_list, plural(count, "archivo", "archivos"), F.small, C.muted).grid(
                row=index, column=2, sticky="e", padx=px(14))
            label(self.types_list, f"{size / total * 100:.0f} %", F.small, C.muted, width=6, anchor="e").grid(
                row=index, column=3, sticky="e")
            label(self.types_list, human_size(size), F.body_bold, width=9, anchor="e").grid(
                row=index, column=4, sticky="e", padx=(px(10), px(14)))
            FlatButton(self.types_list, "Ver archivos", lambda t=ftype.id: self._show_type(t),
                       kind="secondary", small=True).grid(row=index, column=5, sticky="e")

    def _show_type(self, type_id: str) -> None:
        self._set_folder_filter(None, refresh=False)
        self._set_type_filter(type_id)
        self.show_view("files")

    # ------------------------------------------------------ archivos grandes
    def _set_type_filter(self, type_id: str) -> None:
        self.type_filter = type_id
        self.type_var.set("Todos" if type_id == "all" else TYPES_BY_ID[type_id].name)
        self._fill_files()

    def _set_folder_filter(self, folder: str | None, refresh: bool = True) -> None:
        self.folder_filter = folder
        if folder:
            self.folder_filter_label.configure(text=f"Carpeta: {elide(folder, 50)}")
            self.clear_folder_btn.pack(side="left", padx=(px(8), 0))
        else:
            self.folder_filter_label.configure(text="")
            self.clear_folder_btn.pack_forget()
        if refresh:
            self._fill_files()

    def _fill_files(self) -> None:
        tree = self.files_tree
        tree.delete(*tree.get_children())
        self.file_by_iid.clear()
        if not self.analysis:
            return
        folder_key = norm(self.folder_filter) if self.folder_filter else None
        for index, item in enumerate(self.analysis.largest):
            if self.type_filter != "all" and item.type_id != self.type_filter:
                continue
            if folder_key and not is_within(norm(item.path), folder_key):
                continue
            iid = f"f{index}"
            self.file_by_iid[iid] = item
            modified = datetime.fromtimestamp(item.mtime).strftime("%d/%m/%Y")
            tree.insert("", "end", iid=iid, values=(item.name, TYPES_BY_ID[item.type_id].name,
                                                    human_size(item.size), modified, item.folder))
        self._update_file_buttons()

    def _selected_files(self) -> list[analyzer.FoundFile]:
        return [self.file_by_iid[i] for i in self.files_tree.selection() if i in self.file_by_iid]

    def _update_file_buttons(self) -> None:
        selected = self._selected_files()
        self.reveal_btn.set_enabled(len(selected) == 1)
        self.move_btn.set_enabled(bool(selected))
        self.trash_btn.set_enabled(bool(selected))
        if selected:
            self.selection_label.configure(
                text=f"{len(selected)} seleccionados · {human_size(sum(f.size for f in selected))}")
        elif self.analysis:
            self.selection_label.configure(text=f"{len(self.file_by_iid)} archivos en la lista")
        else:
            self.selection_label.configure(text="")

    def _reveal(self) -> None:
        selected = self._selected_files()
        if selected:
            try:
                reveal_in_file_manager(selected[0].path)
            except OSError as exc:
                messagebox.showerror(APP_NAME, f"No se pudo abrir la carpeta:\n{exc}", parent=self)

    def _system_warning(self, files) -> str:
        if any(is_system_path(f.path) or f.type_id in ("system", "appdata", "programs") for f in files):
            return ("\n\nCuidado: algunos son de Windows o de programas instalados. Tocarlos puede hacer que "
                    "algo deje de funcionar; para quitar un programa, mejor desinstálalo desde Configuración.")
        return ""

    def _trash(self) -> None:
        selected = self._selected_files()
        if not selected:
            return
        names = "\n".join(f"•  {f.name}" for f in selected[:8])
        if len(selected) > 8:
            names += f"\n•  … y {len(selected) - 8} más"
        message = (f"¿Enviar {plural(len(selected), 'archivo', 'archivos')} "
                   f"({human_size(sum(f.size for f in selected))}) a la papelera?\n\n{names}"
                   + self._system_warning(selected))
        if not messagebox.askyesno("Enviar a la papelera", message, icon="warning", parent=self):
            return

        def work():
            done, errors = [], []
            for item in selected:
                try:
                    trash.send_to_trash(item.path)
                    done.append(item)
                except OSError as exc:
                    errors.append(f"{item.name}: {exc}")
            return done, errors

        self.app.run_bg(work, lambda r: self._after_change(r, "Enviados a la papelera",
                                                           " Vacía la papelera para liberar el espacio."))

    def _move(self) -> None:
        selected = self._selected_files()
        if not selected:
            return
        destination = filedialog.askdirectory(title="¿Adónde quieres mover los archivos?", parent=self)
        if not destination:
            return
        destination = os.path.normpath(destination)
        message = (f"¿Mover {plural(len(selected), 'archivo', 'archivos')} "
                   f"({human_size(sum(f.size for f in selected))}) a:\n{destination}?"
                   + self._system_warning(selected))
        if not messagebox.askyesno("Mover archivos", message, parent=self):
            return
        self.status.configure(text=f"Moviendo a {destination}… (a otro disco puede tardar)")

        def work():
            done, errors = [], []
            for item in selected:
                try:
                    move_file(item.path, destination)
                    done.append(item)
                except OSError as exc:
                    errors.append(f"{item.name}: {exc}")
            return done, errors

        self.app.run_bg(work, lambda r: self._after_change(r, f"Movidos a {elide(destination, 50)}", ""))

    def _after_change(self, result, verb: str, extra: str) -> None:
        done, errors = result
        if done and self.analysis:
            self._forget_files(done)
            self.summary.configure(text=f"Total: {human_size(self.analysis.total_size)}")
            self._refresh_all()
            self.status.configure(
                text=f"{verb}: {plural(len(done), 'archivo', 'archivos')} ({human_size(sum(f.size for f in done))}).{extra}")
        if errors:
            messagebox.showwarning(APP_NAME, "Algunos archivos no se pudieron cambiar:\n\n" + "\n".join(errors[:10]),
                                   parent=self)

    def _forget_files(self, files) -> None:
        """Descuenta los archivos movidos o borrados de los totales del análisis."""
        analysis = self.analysis
        removed = {f.path for f in files}
        analysis.largest = [f for f in analysis.largest if f.path not in removed]
        index = {}
        stack = [analysis.root]
        while stack:
            node = stack.pop()
            index[norm(node.path)] = node
            stack.extend(node.children)
        for item in files:
            analysis.total_size -= item.size
            analysis.total_files -= 1
            bucket = analysis.by_type[item.type_id]
            bucket[0] -= item.size
            bucket[1] -= 1
            node = index.get(norm(item.folder))
            if node is not None:
                node.own_size -= item.size
                node.own_files -= 1
            while node is not None:
                node.size -= item.size
                node.files -= 1
                node = node.parent
