"""Pantalla principal: «Liberar espacio en C:» con un solo botón."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .. import APP_NAME, freeup, system_info, winsys
from ..platform_utils import IS_WINDOWS, format_count, human_size, open_target
from .theme import C, F, px
from .widgets import CheckBox, FlatButton, Page, ScrollFrame, UsageBar, card, label, plural


class TaskRow(tk.Frame):
    def __init__(self, master, task: freeup.FreeTask, admin: bool, on_change):
        super().__init__(master, bg=C.card, padx=px(14), pady=px(10),
                         highlightthickness=1, highlightbackground=C.border)
        self.task = task
        self.locked = task.needs_admin and not admin
        empty = task.estimate == 0
        self.var = tk.BooleanVar(value=task.default_on and not self.locked and not empty)
        self.columnconfigure(1, weight=1)

        self.check = CheckBox(self, self.var, C.card, command=on_change)
        self.check.grid(row=0, column=0, rowspan=4, sticky="n", padx=(0, px(12)), pady=(px(1), 0))
        if self.locked:
            self.check.set_enabled(False)
        label(self, task.name, F.body_bold, C.faint if self.locked else C.text).grid(row=0, column=1, sticky="w")
        self.size = label(self, "", F.body_bold)
        self.size.grid(row=0, column=2, sticky="e")
        self.desc = label(self, task.description, F.small, C.muted, justify="left", anchor="w")
        self.desc.grid(row=1, column=1, sticky="we", pady=(px(2), 0))
        self.badge = label(self, "", F.small_bold, C.warn)
        self.badge.grid(row=1, column=2, sticky="ne", padx=(px(12), 0))
        self.note = label(self, task.note, F.small, C.faint, justify="left", anchor="w")
        if task.note:
            self.note.grid(row=2, column=1, sticky="we", pady=(px(2), 0))
        self.warning = label(self, task.warning, F.small, C.warn, justify="left", anchor="w")
        if task.warning:
            self.warning.grid(row=3, column=1, sticky="we", pady=(px(2), 0))

        if task.estimate is None:
            self.size.configure(text="Al terminar", fg=C.faint, font=F.small_bold)
        elif empty:
            self.size.configure(text="Vacío", fg=C.faint)
        else:
            self.size.configure(text=human_size(task.estimate), fg=C.text)
        if self.locked:
            self.badge.configure(text="Requiere administrador")
        elif task.slow:
            self.badge.configure(text="Tarda unos minutos", fg=C.muted)
        self.bind("<Configure>", self._wrap)
        for widget in (self, self.desc):
            widget.bind("<Button-1>", lambda e: self.check.toggle())

    def _wrap(self, event) -> None:
        width = max(px(200), event.width - px(280))
        for widget in (self.desc, self.note, self.warning):
            widget.configure(wraplength=width)

    @property
    def selected(self) -> bool:
        return self.var.get() and not self.locked

    def set_result(self, text: str, color: str) -> None:
        self.size.configure(text=text, fg=color, font=F.body_bold)

    def set_badge(self, text: str, color: str = C.warn) -> None:
        self.badge.configure(text=text, fg=color)


class FreeUpPage(Page):
    title = "Liberar espacio"
    subtitle = ("Busca todo lo que se puede borrar sin riesgo en el disco del sistema y lo limpia de una vez. "
                "Tus documentos, fotos y programas no se tocan.")

    def __init__(self, app):
        self.drive = winsys.system_drive()
        self.drive_name = self.drive.rstrip("\\") if IS_WINDOWS else self.drive
        super().__init__(app)
        self.rows: list[TaskRow] = []
        self.cancel = threading.Event()
        self.busy = False
        self.analyzed = False

        # --- tarjetas de arriba -------------------------------------------------
        top = tk.Frame(self.body, bg=C.bg)
        top.pack(fill="x")
        top.columnconfigure(0, weight=3, uniform="top")
        top.columnconfigure(1, weight=2, uniform="top")
        disk = card(top)
        disk.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
        disk_head = tk.Frame(disk, bg=C.card)
        disk_head.pack(fill="x")
        self.disk_title = label(disk_head, f"DISCO DEL SISTEMA ({self.drive_name})", F.small_bold, C.muted)
        self.disk_title.pack(side="left")
        self.system_drive = self.drive
        self.drive_choices = {d.label: d.mount for d in system_info.get_disks()}
        if len(self.drive_choices) > 1:
            self.drive_var = tk.StringVar(value=next((k for k, v in self.drive_choices.items()
                                                      if v.lower() == self.drive.lower()), ""))
            box = ttk.Combobox(disk_head, textvariable=self.drive_var, values=list(self.drive_choices),
                               state="readonly", width=24, font=F.small)
            box.pack(side="right")
            box.bind("<<ComboboxSelected>>", lambda e: self._change_drive())
            label(disk_head, "Disco:", F.small, C.muted).pack(side="right", padx=(0, px(6)))
        self.free_value = label(disk, "—", F.big)
        self.free_value.pack(anchor="w")
        self.disk_bar = UsageBar(disk, C.card, height=12)
        self.disk_bar.pack(fill="x", pady=(px(4), px(6)))
        self.disk_note = label(disk, "", F.small, C.muted)
        self.disk_note.pack(anchor="w")
        potential = card(top)
        potential.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0))
        self.potential_title = label(potential, "PUEDES LIBERAR", F.small_bold, C.muted)
        self.potential_title.pack(anchor="w")
        self.potential_value = label(potential, "…", F.big, C.accent)
        self.potential_value.pack(anchor="w")
        self.potential_note = label(potential, "Analizando…", F.small, C.muted, justify="left",
                                    wraplength=px(300))
        self.potential_note.pack(anchor="w")

        if IS_WINDOWS and not app.admin:
            banner = tk.Frame(self.body, bg=C.card, padx=px(14), pady=px(10),
                              highlightthickness=1, highlightbackground=C.warn)
            banner.pack(fill="x", pady=(px(12), 0))
            FlatButton(banner, "Abrir como administrador", app.elevate, small=True).pack(side="right")
            label(banner, "Para lo más gordo (hibernación, restos de Windows y de actualizaciones, puntos de "
                          "restauración) LimpiaPC necesita permisos de administrador.", F.small, C.text,
                  justify="left", wraplength=px(620)).pack(side="left")

        # --- botones y estado -----------------------------------------------------
        toolbar = tk.Frame(self.body, bg=C.bg)
        toolbar.pack(fill="x", pady=(px(14), 0))
        self.free_btn = FlatButton(toolbar, "Liberar espacio", self.free)
        self.free_btn.pack(side="left")
        self.analyze_btn = FlatButton(toolbar, "Analizar de nuevo", self.analyze, kind="secondary")
        self.analyze_btn.pack(side="left", padx=(px(10), 0))
        self.stop_btn = FlatButton(toolbar, "Detener después de este paso", self._stop, kind="secondary")
        self.progress = ttk.Progressbar(self.body, style="Accent.Horizontal.TProgressbar", mode="determinate")
        self.progress.pack(fill="x", pady=(px(12), 0))
        self.status = label(self.body, "", F.small, C.muted, anchor="w", justify="left")
        self.status.pack(fill="x", pady=(px(6), px(8)))

        # --- lista de tareas y registro ----------------------------------------------
        extras = tk.Frame(self.body, bg=C.bg)
        extras.pack(side="bottom", fill="x", pady=(px(10), 0))
        label(extras, "También:", F.small, C.faint).pack(side="left", padx=(0, px(6)))
        self.space_btn = FlatButton(extras, f"Ver qué ocupa {self.drive_name}", lambda: app.analyze_space(self.drive),
                   kind="secondary", small=True)
        self.space_btn.pack(side="left", padx=(0, px(6)))
        FlatButton(extras, "Buscar duplicados", lambda: app.show("duplicates"), kind="secondary",
                   small=True).pack(side="left", padx=(0, px(6)))
        if IS_WINDOWS:
            FlatButton(extras, "Desinstalar programas que no uses", lambda: open_target("ms-settings:appsfeatures"),
                       kind="secondary", small=True).pack(side="left")

        self.log = tk.Text(self.body, height=7, bg=C.card, fg=C.text, font=F.small, relief="flat",
                           highlightthickness=1, highlightbackground=C.border, padx=px(10), pady=px(8),
                           wrap="word", state="disabled")
        self.log.tag_configure("ok", foreground=C.accent)
        self.log.tag_configure("error", foreground=C.danger_hover)
        self.log.tag_configure("muted", foreground=C.muted)
        self.scroll = ScrollFrame(self.body, C.bg)
        self.scroll.pack(fill="both", expand=True)
        self.refresh_disk()
        self._update_buttons()

    # ================================================================ utilidades
    def on_show(self) -> None:
        self.refresh_disk()
        if not self.analyzed and not self.busy and not getattr(self.app, "selftest", False):
            self.analyze()

    def _change_drive(self) -> None:
        mount = self.drive_choices.get(self.drive_var.get())
        if not mount or self.busy or mount == self.drive:
            return
        self.drive = mount
        self.drive_name = mount.rstrip("\\") if IS_WINDOWS else mount
        is_system = freeup.is_system_drive(mount)
        self.disk_title.configure(text=f"{'DISCO DEL SISTEMA' if is_system else 'DISCO'} ({self.drive_name})")
        self.space_btn.configure(text=f"Ver qué ocupa {self.drive_name}")
        self.refresh_disk()
        self.analyze()

    def refresh_disk(self) -> None:
        try:
            import shutil

            usage = shutil.disk_usage(self.drive)
        except OSError:
            return
        self.free_value.configure(text=f"{human_size(usage.free)} libres")
        self.disk_bar.set(usage.used / usage.total if usage.total else 0)
        self.disk_note.configure(text=f"de {human_size(usage.total)} · {usage.used / usage.total * 100:.0f} % usado"
                                 if usage.total else "")

    def _update_buttons(self) -> None:
        self.free_btn.set_enabled(not self.busy and any(r.selected for r in self.rows))
        self.analyze_btn.set_enabled(not self.busy)

    def _update_potential(self) -> None:
        selected = [r.task for r in self.rows if r.selected]
        known = sum(t.estimate or 0 for t in selected)
        unknown = [t for t in selected if t.estimate is None]
        self.potential_value.configure(text=f"≈ {human_size(known)}" if known or not unknown else "?")
        if not selected:
            self.potential_note.configure(text="Marca lo que quieras liberar.")
        elif unknown:
            self.potential_note.configure(
                text=f"En lo marcado, más lo que liberen {plural(len(unknown), 'tarea', 'tareas')} de Windows "
                     "que solo se pueden medir al terminar.")
        else:
            self.potential_note.configure(text="En lo que tienes marcado.")
        self._update_buttons()

    def _clear_rows(self) -> None:
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        self.rows = []

    def _log(self, text: str, tag: str = "") -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ================================================================== análisis
    def analyze(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        self._clear_rows()
        self._update_buttons()
        self.potential_title.configure(text="PUEDES LIBERAR")
        self.potential_value.configure(text="…")
        self.potential_note.configure(text="Analizando…")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status.configure(text="Analizando…", fg=C.muted)
        admin = self.app.admin
        drive = self.drive

        def say(text: str) -> None:
            self.app.post(self.status.configure, text=text)

        self.app.run_bg(lambda: freeup.detect(admin, dev_root=freeup.default_dev_root(), cancel=self.cancel, drive=drive,
                                              say=say), self._detected, self._failed)

    def _stop_progress(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)

    def _failed(self, exc: Exception) -> None:
        self.busy = False
        self._stop_progress()
        self.stop_btn.pack_forget()
        self.status.configure(text=f"Error: {exc}", fg=C.danger)
        self._update_buttons()

    def _detected(self, tasks: list) -> None:
        self.busy = False
        self.analyzed = True
        self._stop_progress()
        self._clear_rows()
        for group in freeup.GROUPS:
            members = [t for t in tasks if t.group == group]
            if not members:
                continue
            label(self.scroll.inner, group.upper(), F.small_bold, C.faint).pack(
                anchor="w", pady=(px(14) if self.rows else 0, px(6)))
            for task in members:
                row = TaskRow(self.scroll.inner, task, self.app.admin, self._update_potential)
                row.pack(fill="x", pady=(0, px(6)), padx=(0, px(8)))
                self.rows.append(row)
        self.status.configure(text="Revisa la lista: lo marcado es lo recomendado. Pulsa «Liberar espacio» "
                                   "cuando quieras.", fg=C.muted)
        self._update_potential()

    # ================================================================= liberar
    def free(self) -> None:
        if self.busy:
            return
        selected = [r for r in self.rows if r.selected]
        if not selected:
            messagebox.showinfo(APP_NAME, "Marca al menos una cosa para liberar.", parent=self)
            return
        lines = []
        for row in selected:
            estimate = human_size(row.task.estimate) if row.task.estimate else "se mide al terminar"
            lines.append(f"•  {row.task.name}: {estimate}")
        warnings = [f"•  {r.task.warning}" for r in selected if r.task.warning]
        message = "Se va a liberar:\n\n" + "\n".join(lines)
        if warnings:
            message += "\n\nTen en cuenta:\n" + "\n".join(warnings)
        if any(r.task.slow for r in selected):
            message += ("\n\nLas tareas de Windows pueden tardar varios minutos (verás la ventana del Liberador "
                        "de espacio). Puedes seguir usando el PC mientras tanto.")
        if not messagebox.askyesno("Liberar espacio", message + "\n\n¿Empezamos?", icon="warning", parent=self):
            return

        ordered = sorted(selected, key=lambda r: freeup.ORDER.index(r.task.id)
                         if r.task.id in freeup.ORDER else len(freeup.ORDER))
        self.busy = True
        self.cancel.clear()
        self._update_buttons()
        self.stop_btn.pack(side="left", padx=(px(10), 0))
        self.progress.configure(mode="determinate", maximum=len(ordered), value=0)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.log.pack(fill="x", pady=(px(8), 0), before=self.scroll)
        drive = self.drive
        before = freeup.free_bytes(drive)

        def say(text: str) -> None:
            self.app.post(self.status.configure, text=text)

        def work():
            results = []
            for index, row in enumerate(ordered):
                if self.cancel.is_set():
                    break
                self.app.post(self._task_started, row, index, len(ordered))
                try:
                    result = freeup.execute(row.task, cancel=self.cancel, say=say)
                except Exception as exc:  # noqa: BLE001
                    result = freeup.TaskResult(row.task.id, error=str(exc) or exc.__class__.__name__)
                results.append(result)
                self.app.post(self._task_done, row, result, index + 1)
            return results, before

        self.app.run_bg(work, self._all_done, self._failed)

    def _stop(self) -> None:
        self.cancel.set()
        self.status.configure(text="Se detendrá al terminar el paso actual…")

    def _task_started(self, row: TaskRow, index: int, total: int) -> None:
        self.status.configure(text=f"Paso {index + 1} de {total}: {row.task.name}…", fg=C.text)
        row.set_result("En marcha…", C.muted)
        self._log(f"→ {row.task.name}…", "muted")

    def _task_done(self, row: TaskRow, result: freeup.TaskResult, step: int) -> None:
        self.progress.configure(value=step)
        self.refresh_disk()
        if result.error:
            row.set_result("Error", C.danger)
            row.set_badge(result.error[:70], C.danger)
            self._log(f"✗ {row.task.name}: {result.error}", "error")
            return
        row.set_result(f"−{human_size(result.freed)}" if result.freed else "Hecho", C.accent)
        text = f"✓ {row.task.name}: {human_size(result.freed)} liberados"
        if result.skipped:
            text += f" ({format_count(result.skipped)} archivos en uso se dejaron tal cual)"
        if result.reboot:
            text += ". Parte del espacio se libera al reiniciar."
        row.set_badge("Hecho", C.accent)
        self._log(text, "ok")

    def _all_done(self, outcome) -> None:
        results, before = outcome
        self.busy = False
        self.stop_btn.pack_forget()
        self.refresh_disk()
        gained = max(0, freeup.free_bytes(self.drive) - before)
        errors = [r for r in results if r.error]
        reboot = any(r.reboot for r in results)
        text = f"¡Listo! Ahora {self.drive_name} tiene {human_size(gained)} más libres."
        if errors:
            text += f" {plural(len(errors), 'paso tuvo', 'pasos tuvieron')} problemas (mira el registro)."
        if reboot:
            text += " Reinicia el PC para que Windows termine de liberar lo suyo."
        self.status.configure(text=text, fg=C.accent if not errors else C.warn)
        self._log(text, "ok" if not errors else "")
        self.potential_title.configure(text="LIBERADO")
        self.potential_value.configure(text=human_size(gained))
        self.potential_note.configure(text="Pulsa «Analizar de nuevo» para ver si queda algo más.")
        for row in self.rows:
            row.check.set_enabled(False)
        self.analyzed = False  # la próxima vez que se abra, se vuelve a analizar
        self._update_buttons()
        self.free_btn.set_enabled(False)
        dashboard = self.app.pages.get("dashboard")
        if dashboard is not None:
            dashboard.refresh_disks()
            if gained:
                dashboard.set_cleaned(gained)
        messagebox.showinfo(APP_NAME, text, parent=self)
