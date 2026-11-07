"""Optimizar Windows: ajustes reversibles y quitar apps preinstaladas."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .. import APP_NAME, optimizer
from ..platform_utils import IS_WINDOWS
from .theme import C, F, px
from .widgets import CheckBox, FlatButton, Page, ScrollFrame, label, plural


class OptionRow(tk.Frame):
    def __init__(self, master, name, description, locked=False, checked=True, warning="", on_change=None):
        super().__init__(master, bg=C.card, padx=px(14), pady=px(10),
                         highlightthickness=1, highlightbackground=C.border)
        self.locked = locked
        self.var = tk.BooleanVar(value=checked and not locked)
        self.columnconfigure(1, weight=1)
        self.check = CheckBox(self, self.var, C.card, command=on_change)
        self.check.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, px(12)))
        if locked:
            self.check.set_enabled(False)
        label(self, name, F.body_bold, C.faint if locked else C.text).grid(row=0, column=1, sticky="w")
        self.state = label(self, "", F.small_bold, C.muted)
        self.state.grid(row=0, column=2, sticky="e")
        self.desc = label(self, description, F.small, C.muted, justify="left", anchor="w")
        self.desc.grid(row=1, column=1, columnspan=2, sticky="we", pady=(px(2), 0))
        self.warn = label(self, warning, F.small, C.warn, justify="left", anchor="w")
        if warning:
            self.warn.grid(row=2, column=1, columnspan=2, sticky="we", pady=(px(2), 0))
        if locked:
            self.state.configure(text="Requiere administrador", fg=C.warn)
        self.bind("<Configure>", lambda e: [w.configure(wraplength=max(px(200), e.width - px(80)))
                                            for w in (self.desc, self.warn)])

    @property
    def selected(self) -> bool:
        return self.var.get() and not self.locked

    def set_state(self, text, color):
        self.state.configure(text=text, fg=color)


class OptimizePage(Page):
    title = "Optimizar Windows"
    subtitle = ("Quita anuncios, telemetría, procesos en segundo plano y apps preinstaladas que no usas. "
                "Los ajustes se pueden deshacer con «Restaurar»; las apps se reinstalan desde la Microsoft Store.")

    def __init__(self, app):
        super().__init__(app)
        self.busy = False
        self.loaded = False
        self.tweak_rows: list[tuple[optimizer.Tweak, OptionRow]] = []
        self.app_rows: list[tuple[optimizer.BloatApp, list, OptionRow]] = []
        if not IS_WINDOWS:
            label(self.body, "Esta sección solo está disponible en Windows.", F.body, C.muted).pack(anchor="w")
            return
        bar = tk.Frame(self.body, bg=C.bg)
        bar.pack(fill="x")
        self.apply_btn = FlatButton(bar, "Aplicar lo marcado", self.apply)
        self.apply_btn.pack(side="left")
        self.restore_btn = FlatButton(bar, "Restaurar ajustes originales", self.restore, kind="secondary")
        self.restore_btn.pack(side="left", padx=(px(10), 0))
        self.status = label(self.body, "", F.small, C.muted, anchor="w", justify="left")
        self.status.pack(fill="x", pady=(px(10), px(8)))
        self.scroll = ScrollFrame(self.body, C.bg)
        self.scroll.pack(fill="both", expand=True)

    def on_show(self) -> None:
        if IS_WINDOWS and not self.loaded and not self.busy and not getattr(self.app, "selftest", False):
            self.load()

    # ------------------------------------------------------------------ carga
    def load(self) -> None:
        self.busy = True
        self.status.configure(text="Comprobando ajustes y apps instaladas…", fg=C.muted)
        self.app.run_bg(lambda: (self._read_states(), optimizer.installed_bloat()), self._loaded, self._failed)

    def _read_states(self) -> dict:
        registry = optimizer.Registry()
        return {t.id: optimizer.is_applied(t, registry) for t in optimizer.TWEAKS}

    def _failed(self, exc) -> None:
        self.busy = False
        self.status.configure(text=f"Error: {exc}", fg=C.danger)

    def _loaded(self, result) -> None:
        states, apps = result
        self.busy = False
        self.loaded = True
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        self.tweak_rows, self.app_rows = [], []
        label(self.scroll.inner, "AJUSTES DE WINDOWS", F.small_bold, C.faint).pack(anchor="w", pady=(0, px(6)))
        for tweak in optimizer.TWEAKS:
            applied = states.get(tweak.id, False)
            row = OptionRow(self.scroll.inner, tweak.name, tweak.description,
                            locked=tweak.needs_admin and not self.app.admin,
                            checked=tweak.default_on and not applied, warning=tweak.warning)
            if applied:
                row.set_state("Ya aplicado", C.accent)
            row.pack(fill="x", pady=(0, px(6)), padx=(0, px(8)))
            self.tweak_rows.append((tweak, row))
        label(self.scroll.inner, "APPS PREINSTALADAS QUE PUEDES QUITAR", F.small_bold, C.faint).pack(
            anchor="w", pady=(px(14), px(6)))
        if not apps:
            label(self.scroll.inner, "No tienes ninguna de las apps de relleno conocidas. ¡Bien!",
                  F.small, C.muted).pack(anchor="w")
        for bloat, packages in apps:
            row = OptionRow(self.scroll.inner, bloat.name, "Se desinstala para tu usuario. "
                            "Si un día la quieres, está en la Microsoft Store.", checked=False)
            row.pack(fill="x", pady=(0, px(6)), padx=(0, px(8)))
            self.app_rows.append((bloat, packages, row))
        self.restore_btn.set_enabled(optimizer.has_backup())
        self.status.configure(text="Marca lo que quieras y pulsa «Aplicar lo marcado». Las apps vienen "
                                   "desmarcadas: elige tú cuáles quitar.", fg=C.muted)

    # ---------------------------------------------------------------- aplicar
    def apply(self) -> None:
        if self.busy:
            return
        tweaks = [(t, r) for t, r in self.tweak_rows if r.selected]
        apps = [(a, p, r) for a, p, r in self.app_rows if r.selected]
        if not tweaks and not apps:
            messagebox.showinfo(APP_NAME, "Marca al menos una opción.", parent=self)
            return
        lines = [f"•  {t.name}" for t, _ in tweaks] + [f"•  Quitar {a.name}" for a, _, _ in apps]
        if not messagebox.askyesno("Optimizar", "Se va a aplicar:\n\n" + "\n".join(lines) +
                                   "\n\nLos ajustes se pueden deshacer con «Restaurar». ¿Seguir?", parent=self):
            return
        self.busy = True
        self.status.configure(text="Aplicando…", fg=C.text)

        def work():
            registry = optimizer.Registry()
            done = []
            for tweak, row in tweaks:
                try:
                    optimizer.apply_tweak(tweak, registry)
                    done.append((row, "Aplicado", C.accent))
                except OSError as exc:
                    done.append((row, f"Error: {exc.strerror or exc}"[:40], C.danger))
            for bloat, packages, row in apps:
                code, out = optimizer.remove_app(packages)
                done.append((row, "Quitada" if code == 0 else "No se pudo quitar", C.accent if code == 0 else C.danger))
            return done

        def finished(done):
            self.busy = False
            for row, text, color in done:
                row.set_state(text, color)
                row.var.set(False)
            errors = sum(1 for _, _, color in done if color == C.danger)
            text = f"Hecho: {plural(len(done) - errors, 'cambio aplicado', 'cambios aplicados')}."
            if errors:
                text += f" {errors} con error."
            text += " Algunos ajustes se notan después de cerrar sesión o reiniciar."
            self.status.configure(text=text, fg=C.accent if not errors else C.warn)
            self.restore_btn.set_enabled(optimizer.has_backup())

        self.app.run_bg(work, finished, self._failed)

    def restore(self) -> None:
        if self.busy or not messagebox.askyesno(
                "Restaurar", "¿Devolver todos los ajustes que cambió LimpiaPC a como estaban?", parent=self):
            return
        count = optimizer.restore_all(optimizer.Registry())
        self.loaded = False
        self.load()
        self.app.after(100, lambda: self.status.configure(
            text=f"Restaurados {count} valores. Reinicia sesión para verlo todo como antes.", fg=C.accent))
