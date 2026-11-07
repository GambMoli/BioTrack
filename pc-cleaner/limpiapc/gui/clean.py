"""Limpieza de temporales y cachés."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .. import APP_NAME, cleaner
from ..platform_utils import format_count, human_size, running_process_names
from .theme import C, F, px
from .widgets import CheckBox, FlatButton, Page, ScrollFrame, label


class CategoryRow(tk.Frame):
    def __init__(self, master, category: cleaner.Category, admin: bool, on_change):
        super().__init__(master, bg=C.card, padx=px(14), pady=px(10),
                         highlightthickness=1, highlightbackground=C.border)
        self.category = category
        self.locked = category.needs_admin and not admin
        self.var = tk.BooleanVar(value=category.default_on and not self.locked)
        self.columnconfigure(1, weight=1)

        self.check = CheckBox(self, self.var, C.card, command=on_change)
        self.check.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, px(12)), pady=(px(1), 0))
        if self.locked:
            self.check.set_enabled(False)

        self.name = label(self, category.name, F.body_bold, C.faint if self.locked else C.text)
        self.name.grid(row=0, column=1, sticky="w")
        self.size = label(self, "—", F.body_bold, C.muted)
        self.size.grid(row=0, column=2, sticky="e")
        self.desc = label(self, category.description, F.small, C.muted, justify="left", anchor="w")
        self.desc.grid(row=1, column=1, sticky="we", pady=(px(2), 0))
        self.badge = label(self, "", F.small_bold, C.warn)
        self.badge.grid(row=1, column=2, sticky="e", padx=(px(12), 0))
        self.warning = label(self, category.warning, F.small, C.warn, justify="left", anchor="w")
        if category.warning:
            self.warning.grid(row=2, column=1, sticky="we", pady=(px(2), 0))
        if self.locked:
            self.badge.configure(text="Requiere administrador")
        for widget in (self, self.name, self.desc):
            widget.bind("<Button-1>", lambda e: self.check.toggle())
        self.bind("<Configure>", self._wrap)

    def _wrap(self, event):
        width = max(px(200), event.width - px(260))
        self.desc.configure(wraplength=width)
        self.warning.configure(wraplength=width)

    @property
    def selected(self) -> bool:
        return self.var.get() and not self.locked

    def set_size(self, text: str, color: str = C.text) -> None:
        self.size.configure(text=text, fg=color)

    def set_badge(self, text: str, color: str = C.warn) -> None:
        if not self.locked:
            self.badge.configure(text=text, fg=color)


class CleanPage(Page):
    title = "Limpieza"
    subtitle = ("Borra archivos temporales y cachés que Windows y tus programas vuelven a crear "
                "solos. Nada de tus documentos, fotos o contraseñas.")

    def __init__(self, app):
        super().__init__(app)
        self.results: dict[str, cleaner.ScanResult] = {}
        self.busy = False
        self.cancel = threading.Event()

        toolbar = tk.Frame(self.body, bg=C.bg)
        toolbar.pack(fill="x")
        self.scan_btn = FlatButton(toolbar, "Analizar", self.start_scan, kind="secondary")
        self.scan_btn.pack(side="left")
        self.clean_btn = FlatButton(toolbar, "Limpiar seleccionado", self.start_clean)
        self.clean_btn.pack(side="left", padx=(px(10), 0))
        self.total_label = label(toolbar, "", F.h2, C.accent)
        self.total_label.pack(side="right")

        status = tk.Frame(self.body, bg=C.bg)
        status.pack(fill="x", pady=(px(12), px(10)))
        self.progress = ttk.Progressbar(status, style="Accent.Horizontal.TProgressbar", mode="determinate")
        self.progress.pack(fill="x")
        self.status = label(status, "Pulsa «Analizar» para ver cuánto espacio puedes recuperar.", F.small, C.muted)
        self.status.pack(anchor="w", pady=(px(6), 0))

        self.scroll = ScrollFrame(self.body, C.bg)
        self.scroll.pack(fill="both", expand=True)
        self.rows: list[CategoryRow] = []
        categories = cleaner.available_categories()
        for group in cleaner.GROUPS:
            members = [c for c in categories if c.group == group]
            if not members:
                continue
            label(self.scroll.inner, group.upper(), F.small_bold, C.faint).pack(
                anchor="w", pady=(px(14) if self.rows else 0, px(6)))
            for category in members:
                row = CategoryRow(self.scroll.inner, category, app.admin, self._update_total)
                row.pack(fill="x", pady=(0, px(6)), padx=(0, px(8)))
                self.rows.append(row)
        if not self.rows:
            label(self.scroll.inner, "No se encontró nada que limpiar en este equipo.", F.body, C.muted).pack(anchor="w")
        self._update_total()

    # ----------------------------------------------------------------- utilidades
    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.scan_btn.set_enabled(not busy)
        self.clean_btn.set_enabled(not busy)

    def _row(self, category_id: str) -> CategoryRow | None:
        return next((r for r in self.rows if r.category.id == category_id), None)

    def _update_total(self) -> None:
        selected = [r for r in self.rows if r.selected and r.category.id in self.results]
        if not selected:
            self.total_label.configure(text="")
            return
        total = sum(self.results[r.category.id].size for r in selected)
        self.total_label.configure(text=f"Seleccionado: {human_size(total)}" if total else "")
        if total:
            self.app.pages["dashboard"].set_recoverable(total, len(selected))

    # ------------------------------------------------------------------- análisis
    def start_scan(self, then_clean: bool = False) -> None:
        if self.busy or not self.rows:
            return
        self._set_busy(True)
        self.cancel.clear()
        rows = list(self.rows)
        self.progress.configure(maximum=len(rows), value=0)
        self.status.configure(text="Analizando…")
        for row in rows:
            row.set_size("…", C.faint)
            row.set_badge("")

        def work():
            running = running_process_names()
            for index, row in enumerate(rows):
                if self.cancel.is_set():
                    break
                category = row.category
                self.app.post(self.status.configure, text=f"Analizando: {category.name}…")
                result = cleaner.scan_category(category, cancel=self.cancel)
                open_apps = [p for p in category.processes if p.lower() in running]
                self.app.post(self._scan_row_done, row, result, bool(open_apps), index + 1)
            return then_clean

        self.app.run_bg(work, self._scan_done, self._failed)

    def _scan_row_done(self, row: CategoryRow, result: cleaner.ScanResult, app_open: bool, step: int):
        self.results[row.category.id] = result
        self.progress.configure(value=step)
        if result.size:
            row.set_size(human_size(result.size), C.text)
        else:
            row.set_size("Vacío", C.faint)
        if app_open and result.size:
            row.set_badge("Abierto: ciérralo para limpiarlo todo")
        self._update_total()

    def _scan_done(self, then_clean: bool):
        self._set_busy(False)
        total = sum(r.size for r in self.results.values())
        self.status.configure(text=f"Análisis terminado: {human_size(total)} en total. "
                                   "Marca lo que quieras borrar y pulsa «Limpiar seleccionado».")
        self._update_total()
        if then_clean:
            self.start_clean()

    def _failed(self, exc: Exception):
        self._set_busy(False)
        self.status.configure(text=f"Error: {exc}")

    # ------------------------------------------------------------------- limpieza
    def start_clean(self) -> None:
        if self.busy:
            return
        selected = [r for r in self.rows if r.selected]
        if not selected:
            messagebox.showinfo(APP_NAME, "Marca al menos una categoría para limpiar.", parent=self)
            return
        if any(r.category.id not in self.results for r in selected):
            self.start_scan(then_clean=True)
            return
        targets = [r for r in selected if self.results[r.category.id].size or self.results[r.category.id].count]
        total = sum(self.results[r.category.id].size for r in targets)
        if not targets:
            messagebox.showinfo(APP_NAME, "No hay nada que limpiar en lo seleccionado. ¡Tu PC ya está limpio!",
                                parent=self)
            return
        lines = "\n".join(f"•  {r.category.name}: {human_size(self.results[r.category.id].size)}"
                          for r in targets[:12])
        if len(targets) > 12:
            lines += f"\n•  … y {len(targets) - 12} más"
        message = (f"Se van a eliminar {human_size(total)}:\n\n{lines}\n\n"
                   "Los archivos que estén en uso se saltarán sin problema.")
        if any(r.category.kind == "recycle_bin" for r in targets):
            message += "\n\nAtención: la papelera se vaciará de forma permanente."
        if not messagebox.askyesno("Confirmar limpieza", message + "\n\n¿Continuar?", icon="warning", parent=self):
            return

        self._set_busy(True)
        self.cancel.clear()
        total_files = sum(max(1, self.results[r.category.id].count) for r in targets)
        self.progress.configure(maximum=total_files, value=0)

        def work():
            outcomes = []
            offset = 0
            for row in targets:
                if self.cancel.is_set():
                    break
                category = row.category
                scan = self.results[category.id]
                self.app.post(self.status.configure, text=f"Limpiando: {category.name}…")

                def progress(done, base=offset):
                    self.app.post(self.progress.configure, value=base + done)

                result = cleaner.clean_category(category, scan, cancel=self.cancel, progress=progress)
                offset += max(1, scan.count)
                self.app.post(self.progress.configure, value=offset)
                self.app.post(self._clean_row_done, row, result)
                outcomes.append(result)
            return outcomes

        self.app.run_bg(work, self._clean_done, self._failed)

    def _clean_row_done(self, row: CategoryRow, result: cleaner.CleanResult):
        if result.error:
            row.set_size("Error", C.danger)
            row.set_badge(result.error[:60], C.danger)
            return
        row.set_size(f"−{human_size(result.freed)}", C.accent)
        if result.skipped:
            row.set_badge(f"{format_count(result.skipped)} en uso, omitidos", C.muted)
        else:
            row.set_badge("Limpio", C.accent)
        self.results.pop(row.category.id, None)

    def _clean_done(self, outcomes: list[cleaner.CleanResult]):
        self._set_busy(False)
        freed = sum(o.freed for o in outcomes)
        deleted = sum(o.deleted for o in outcomes)
        skipped = sum(o.skipped for o in outcomes)
        text = f"¡Listo! Liberaste {human_size(freed)} ({format_count(deleted)} archivos)."
        if skipped:
            text += f" {format_count(skipped)} archivos estaban en uso y se dejaron tal cual."
        self.status.configure(text=text)
        self._update_total()
        dashboard = self.app.pages["dashboard"]
        dashboard.refresh_disks()
        if freed:
            dashboard.set_cleaned(freed)
        messagebox.showinfo(APP_NAME, text, parent=self)
