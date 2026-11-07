"""Interfaz gráfica de LimpiaPC (tkinter, sin dependencias externas)."""

from __future__ import annotations

import os
import queue
import random
import threading
import time
import traceback
from datetime import datetime

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, __version__, cleaner, largefiles, startup, system_info, trash
from .platform_utils import (
    IS_MAC,
    IS_WINDOWS,
    decode_output,
    format_count,
    format_duration,
    human_size,
    is_admin,
    open_target,
    relaunch_as_admin,
    reveal_in_file_manager,
    run_elevated,
    run_quiet,
    running_process_names,
    shell_open,
    top_memory_processes,
)

SCALE = 1.0


def px(value: float) -> int:
    return int(round(value * SCALE))


class C:
    sidebar = "#0b1120"
    nav_hover = "#131c2e"
    bg = "#111827"
    card = "#182235"
    card_hi = "#22304a"
    border = "#2a3852"
    text = "#e5e7eb"
    muted = "#94a3b8"
    faint = "#64748b"
    accent = "#10b981"
    accent_hover = "#34d399"
    accent_dim = "#0f5e48"
    on_accent = "#04261c"
    warn = "#f59e0b"
    danger = "#ef4444"
    danger_hover = "#f87171"


class F:
    family = "TkDefaultFont"

    @classmethod
    def init(cls, root: tk.Misc) -> None:
        available = {name.lower(): name for name in tkfont.families(root)}
        for candidate in ("Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Ubuntu",
                          "Cantarell", "Noto Sans", "DejaVu Sans", "Liberation Sans", "Arial"):
            if candidate.lower() in available:
                cls.family = available[candidate.lower()]
                break
        f = cls.family
        cls.title = (f, 19, "bold")
        cls.h2 = (f, 12, "bold")
        cls.body = (f, 10)
        cls.body_bold = (f, 10, "bold")
        cls.small = (f, 9)
        cls.small_bold = (f, 8, "bold")
        cls.big = (f, 24, "bold")
        cls.logo = (f, 15, "bold")
        cls.nav = (f, 11)


def level_color(fraction: float) -> str:
    if fraction < 0.75:
        return C.accent
    if fraction < 0.9:
        return C.warn
    return C.danger


def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kwargs):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# =========================================================================== #
# Widgets
# =========================================================================== #
class FlatButton(tk.Label):
    STYLES = {
        "primary": (C.accent, C.accent_hover, C.on_accent),
        "secondary": (C.card_hi, C.border, C.text),
        "danger": (C.danger, C.danger_hover, "#ffffff"),
    }

    def __init__(self, master, text, command=None, kind="primary", small=False):
        self._bg, self._hover, self._fg = self.STYLES[kind]
        super().__init__(
            master, text=text, bg=self._bg, fg=self._fg,
            font=F.small_bold if small else F.body_bold,
            padx=px(10 if small else 16), pady=px(4 if small else 7), cursor="hand2", takefocus=1,
            highlightthickness=1, highlightbackground=master.cget("bg"), highlightcolor=C.accent_hover,
        )
        self.command = command
        self.enabled = True
        self.bind("<Enter>", lambda e: self.enabled and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda e: self._restyle())
        self.bind("<Button-1>", self._click)
        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)

    def _restyle(self) -> None:
        self.configure(bg=self._bg if self.enabled else C.card_hi,
                       fg=self._fg if self.enabled else C.faint)

    def _click(self, _event=None):
        if self.enabled and self.command:
            self.focus_set()
            self.command()
        return "break"

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._restyle()


class CheckBox(tk.Canvas):
    def __init__(self, master, variable: tk.BooleanVar, bg: str, command=None):
        size = px(20)
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=1)
        self.var = variable
        self.command = command
        self.enabled = True
        self.size = size
        variable.trace_add("write", lambda *_: self._draw())
        self.bind("<Button-1>", self.toggle)
        self.bind("<space>", self.toggle)
        self._draw()

    def toggle(self, _event=None):
        if not self.enabled:
            return
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        s, pad = self.size, px(2)
        if not self.enabled:
            round_rect(self, pad, pad, s - pad, s - pad, px(5), fill=C.card_hi, outline=C.border)
            return
        if self.var.get():
            round_rect(self, pad, pad, s - pad, s - pad, px(5), fill=C.accent, outline=C.accent)
            self.create_line(s * 0.27, s * 0.52, s * 0.44, s * 0.68, s * 0.74, s * 0.34,
                             fill=C.on_accent, width=max(2, px(2.4)), capstyle="round", joinstyle="round")
        else:
            round_rect(self, pad, pad, s - pad, s - pad, px(5), fill="", outline=C.muted, width=max(1, px(1.5)))


class UsageBar(tk.Canvas):
    def __init__(self, master, bg: str, height: int = 10):
        super().__init__(master, height=px(height), bg=bg, highlightthickness=0, bd=0)
        self.fraction = 0.0
        self.color = None
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, fraction: float, color: str | None = None) -> None:
        self.fraction = max(0.0, min(1.0, fraction))
        self.color = color
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), int(self.cget("height"))
        if width <= 2:
            return
        round_rect(self, 0, 0, width, height, height / 2, fill=C.card_hi, outline="")
        if self.fraction > 0:
            filled = max(height, width * self.fraction)
            round_rect(self, 0, 0, filled, height, height / 2,
                       fill=self.color or level_color(self.fraction), outline="")


class ScrollFrame(tk.Frame):
    def __init__(self, master, bg: str):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=px(20))
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _event=None):
        self.bind_all("<MouseWheel>", self._on_wheel)
        self.bind_all("<Button-4>", lambda e: self._scroll(-3))
        self.bind_all("<Button-5>", lambda e: self._scroll(3))

    def _unbind_wheel(self, _event=None):
        x, y = self.winfo_pointerxy()
        widget = self.winfo_containing(x, y)
        if widget is not None and str(widget).startswith(str(self)):
            return  # el puntero solo pasó a un widget hijo
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.unbind_all(sequence)

    def _scroll(self, steps: int) -> None:
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(steps, "units")

    def _on_wheel(self, event):
        steps = -event.delta if IS_MAC else -int(event.delta / 120) * 3
        self._scroll(steps or (-1 if event.delta > 0 else 1))


def card(parent, padx=18, pady=16) -> tk.Frame:
    return tk.Frame(parent, bg=C.card, padx=px(padx), pady=px(pady),
                    highlightthickness=1, highlightbackground=C.border, highlightcolor=C.border)


def label(parent, text="", font=None, fg=None, bg=None, **kwargs) -> tk.Label:
    return tk.Label(parent, text=text, font=font or F.body, fg=fg or C.text,
                    bg=bg or parent.cget("bg"), **kwargs)


# =========================================================================== #
# Páginas
# =========================================================================== #
class Page(tk.Frame):
    title = ""
    subtitle = ""

    def __init__(self, app: "App"):
        super().__init__(app.content, bg=C.bg)
        self.app = app
        header = tk.Frame(self, bg=C.bg)
        header.pack(fill="x", padx=px(28), pady=(px(22), px(14)))
        label(header, self.title, F.title).pack(anchor="w")
        self.subtitle_label = label(header, self.subtitle, F.body, C.muted, justify="left",
                                    wraplength=px(780))
        if self.subtitle:
            self.subtitle_label.pack(anchor="w", pady=(px(4), 0))
        self.body = tk.Frame(self, bg=C.bg)
        self.body.pack(fill="both", expand=True, padx=px(28), pady=(0, px(20)))

    def on_show(self) -> None:
        pass


# --------------------------------------------------------------------------- #
TIPS = (
    "Desinstala los programas que ya no uses: es lo que más espacio y velocidad recupera.",
    "Deja al menos un 10-15 % libre en el disco del sistema; Windows lo necesita para "
    "actualizaciones y memoria virtual.",
    "Desactiva en «Programas al iniciar» lo que no necesites nada más encender: el PC arrancará antes.",
    "Reinicia el equipo de vez en cuando: libera memoria y termina de instalar actualizaciones.",
    "Decenas de pestañas abiertas en el navegador consumen mucha RAM. Ciérralas o guárdalas como marcadores.",
    "Mantén Windows y los controladores de la tarjeta gráfica al día.",
    "Si tu PC todavía usa un disco duro mecánico (HDD), cambiarlo por un SSD es la mejora más notable.",
    "Los «limpiadores de registro» y «optimizadores de RAM» no aceleran el PC y pueden dar problemas.",
)


class DashboardPage(Page):
    title = "Resumen"

    def __init__(self, app):
        super().__init__(app)
        self.cpu = system_info.CpuSampler()
        self._os = system_info.os_description()
        self._procs_loading = False
        self._last_procs = 0.0

        top = tk.Frame(self.body, bg=C.bg)
        top.pack(fill="x")
        for col in range(3):
            top.columnconfigure(col, weight=1, uniform="stat")

        self.cpu_value, self.cpu_bar, self.cpu_note = self._stat_card(top, 0, "PROCESADOR", "Uso en este momento")
        self.ram_value, self.ram_bar, self.ram_note = self._stat_card(top, 1, "MEMORIA RAM", "")

        clean_card = card(top)
        clean_card.grid(row=0, column=2, sticky="nsew", padx=(px(8), 0))
        self.clean_title = label(clean_card, "ESPACIO RECUPERABLE", F.small_bold, C.muted)
        self.clean_title.pack(anchor="w")
        self.clean_value = label(clean_card, "?", F.big, C.accent)
        self.clean_value.pack(anchor="w")
        self.clean_note = label(clean_card, "Analiza para ver cuánto puedes liberar.", F.small, C.muted,
                                justify="left", wraplength=px(240))
        self.clean_note.pack(anchor="w", pady=(0, px(8)))
        FlatButton(clean_card, "Analizar ahora", self._analyze, small=True).pack(anchor="w")

        bottom = tk.Frame(self.body, bg=C.bg)
        bottom.pack(fill="both", expand=True, pady=(px(16), 0))
        bottom.columnconfigure(0, weight=3, uniform="bottom")
        bottom.columnconfigure(1, weight=2, uniform="bottom")
        bottom.rowconfigure(0, weight=1)

        disks_card = card(bottom)
        disks_card.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
        label(disks_card, "Unidades de almacenamiento", F.h2).pack(anchor="w", pady=(0, px(10)))
        tip_box = tk.Frame(disks_card, bg=C.card)
        tip_box.pack(side="bottom", fill="x")
        label(tip_box, "CONSEJO", F.small_bold, C.accent).pack(anchor="w")
        self.tip = label(tip_box, random.choice(TIPS), F.small, C.muted, justify="left", anchor="w")
        self.tip.pack(fill="x", pady=(px(2), 0))
        tip_box.bind("<Configure>", lambda e: self.tip.configure(wraplength=max(px(200), e.width - px(4))))
        self.disks_frame = tk.Frame(disks_card, bg=C.card)
        self.disks_frame.pack(fill="both", expand=True)

        procs_card = card(bottom)
        procs_card.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0))
        label(procs_card, "Lo que más memoria usa", F.h2).pack(anchor="w")
        label(procs_card, "Cerrar lo que no uses libera RAM al instante.", F.small, C.muted).pack(
            anchor="w", pady=(px(2), px(10)))
        self.procs_frame = tk.Frame(procs_card, bg=C.card)
        self.procs_frame.pack(fill="both", expand=True)
        label(self.procs_frame, "Cargando…", F.small, C.muted).pack(anchor="w")

        self.refresh_disks()
        self.after(600, self._tick)

    def _stat_card(self, parent, column, title, note):
        box = card(parent)
        box.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else px(8), px(8)))
        label(box, title, F.small_bold, C.muted).pack(anchor="w")
        value = label(box, "—", F.big)
        value.pack(anchor="w")
        bar = UsageBar(box, C.card)
        bar.pack(fill="x", pady=(px(4), px(8)))
        note_label = label(box, note, F.small, C.muted)
        note_label.pack(anchor="w")
        return value, bar, note_label

    def _analyze(self):
        self.app.show("clean")
        self.app.pages["clean"].start_scan()

    def set_recoverable(self, size: int, categories: int) -> None:
        self.clean_title.configure(text="ESPACIO RECUPERABLE")
        self.clean_value.configure(text=human_size(size), fg=C.accent)
        if not size:
            self.clean_note.configure(text="Nada pendiente de limpiar en lo seleccionado.")
            return
        where = "1 categoría seleccionada" if categories == 1 else f"{categories} categorías seleccionadas"
        self.clean_note.configure(text=f"En {where}. Ve a Limpieza para liberarlo.")

    def set_cleaned(self, freed: int) -> None:
        self.clean_title.configure(text="ESPACIO LIBERADO")
        self.clean_value.configure(text=f"−{human_size(freed)}", fg=C.accent)
        self.clean_note.configure(text="Liberado en la última limpieza. ¡Buen trabajo!")

    def on_show(self):
        self.refresh_disks()
        self._load_processes()

    def _tick(self):
        usage = self.cpu.sample()
        if usage is not None:
            self.cpu_value.configure(text=f"{usage * 100:.0f} %")
            self.cpu_bar.set(usage)
        memory = system_info.get_memory()
        if memory:
            self.ram_value.configure(text=f"{memory.fraction * 100:.0f} %")
            self.ram_bar.set(memory.fraction)
            self.ram_note.configure(text=f"{human_size(memory.used)} de {human_size(memory.total)} en uso")
        uptime = system_info.get_uptime_seconds()
        text = self._os
        if uptime:
            text += f"  ·  Encendido desde hace {format_duration(uptime)}"
            if uptime > 7 * 24 * 3600:
                text += "  ·  Reiniciar de vez en cuando ayuda a que vaya más fluido."
        if not self.subtitle_label.winfo_ismapped():
            self.subtitle_label.pack(anchor="w", pady=(px(4), 0))
        self.subtitle_label.configure(text=text)
        if self.app.current == "dashboard" and time.monotonic() - self._last_procs > 8:
            self._load_processes()
        self.after(2000, self._tick)

    def refresh_disks(self):
        for child in self.disks_frame.winfo_children():
            child.destroy()
        disks = system_info.get_disks()
        if not disks:
            label(self.disks_frame, "No se pudo leer la información de los discos.", F.small, C.muted).pack(anchor="w")
        for disk in disks:
            row = tk.Frame(self.disks_frame, bg=C.card)
            row.pack(fill="x", pady=(0, px(12)))
            line = tk.Frame(row, bg=C.card)
            line.pack(fill="x")
            label(line, disk.label, F.body_bold).pack(side="left")
            label(line, f"{human_size(disk.free)} libres de {human_size(disk.total)}", F.small, C.muted).pack(side="right")
            bar = UsageBar(row, C.card, height=12)
            bar.pack(fill="x", pady=(px(5), 0))
            bar.set(disk.fraction)
            if disk.fraction >= 0.9:
                label(row, "Casi lleno: Windows va más lento con menos de un 10 % libre.", F.small, C.warn).pack(anchor="w", pady=(px(3), 0))

    def _load_processes(self):
        if self._procs_loading:
            return
        self._procs_loading = True
        self._last_procs = time.monotonic()

        def done(result):
            self._procs_loading = False
            self._show_processes(result)

        def failed(_exc):
            self._procs_loading = False

        self.app.run_bg(lambda: top_memory_processes(7), done, failed)

    def _show_processes(self, processes):
        for child in self.procs_frame.winfo_children():
            child.destroy()
        if not processes:
            label(self.procs_frame, "No disponible.", F.small, C.muted).pack(anchor="w")
            return
        biggest = processes[0][1] or 1
        for name, size, count in processes:
            row = tk.Frame(self.procs_frame, bg=C.card)
            row.pack(fill="x", pady=(0, px(7)))
            line = tk.Frame(row, bg=C.card)
            line.pack(fill="x")
            shown = name if len(name) <= 28 else name[:27] + "…"
            if count > 1:
                shown += f"  ×{count}"
            label(line, shown, F.small).pack(side="left")
            label(line, human_size(size), F.small_bold, C.muted).pack(side="right")
            bar = UsageBar(row, C.card, height=5)
            bar.pack(fill="x", pady=(px(3), 0))
            bar.set(size / biggest, C.accent_dim if size / biggest < 0.6 else C.accent)


# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
def _elide(text: str, limit: int = 48) -> str:
    """Acorta rutas largas por el medio: C:\\Users\\…\\Descargas."""
    if len(text) <= limit:
        return text
    keep = (limit - 1) // 2
    return text[:keep] + "…" + text[-keep:]


class LargeFilesPage(Page):
    title = "Archivos grandes"
    subtitle = ("Encuentra lo que más ocupa: vídeos olvidados, instaladores viejos, copias de seguridad… "
                "Lo que borres va a la papelera, así que puedes recuperarlo.")
    SIZES = {"50 MB": 50, "100 MB": 100, "250 MB": 250, "500 MB": 500, "1 GB": 1024}

    def __init__(self, app):
        super().__init__(app)
        self.folder = os.path.expanduser("~")
        self.cancel = threading.Event()
        self.busy = False
        self.files: dict[str, largefiles.LargeFile] = {}
        self.sort_desc = True
        self.sort_key = "size"

        controls = tk.Frame(self.body, bg=C.bg)
        controls.pack(fill="x")
        label(controls, "Carpeta:", F.body, C.muted).pack(side="left")
        self.search_btn = FlatButton(controls, "Buscar", self._toggle_search)
        self.search_btn.pack(side="right")
        self.size_var = tk.StringVar(value="100 MB")
        ttk.Combobox(controls, textvariable=self.size_var, values=list(self.SIZES), state="readonly",
                     width=8, font=F.body).pack(side="right", padx=(0, px(14)))
        label(controls, "Mayores de:", F.body, C.muted).pack(side="right", padx=(px(20), px(6)))
        FlatButton(controls, "Cambiar…", self._choose_folder, kind="secondary", small=True).pack(side="right")
        self.folder_label = label(controls, _elide(self.folder), F.body_bold, anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True, padx=(px(6), px(10)))

        self.status = label(self.body, "Elige una carpeta y pulsa «Buscar».", F.small, C.muted)
        self.status.pack(anchor="w", pady=(px(10), px(8)))

        table = tk.Frame(self.body, bg=C.card, highlightthickness=1, highlightbackground=C.border)
        table.pack(fill="both", expand=True)
        columns = ("name", "size", "modified", "folder")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="extended")
        headings = {"name": "Nombre", "size": "Tamaño", "modified": "Modificado", "folder": "Carpeta"}
        widths = {"name": 260, "size": 90, "modified": 110, "folder": 420}
        for column in columns:
            self.tree.heading(column, text=headings[column], anchor="e" if column == "size" else "w",
                              command=lambda c=column: self._sort_by(c))
            self.tree.column(column, width=px(widths[column]), anchor="e" if column == "size" else "w",
                             stretch=column in ("name", "folder"))
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self._reveal())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_selection())
        self.tree.bind("<Delete>", lambda e: self._trash())

        actions = tk.Frame(self.body, bg=C.bg)
        actions.pack(fill="x", pady=(px(10), 0))
        self.reveal_btn = FlatButton(actions, "Abrir ubicación", self._reveal, kind="secondary")
        self.reveal_btn.pack(side="left")
        self.trash_btn = FlatButton(actions, "Enviar a la papelera", self._trash, kind="danger")
        self.trash_btn.pack(side="left", padx=(px(10), 0))
        self.selection_label = label(actions, "", F.body, C.muted)
        self.selection_label.pack(side="right")
        self._update_selection()

    def _choose_folder(self):
        if self.busy:
            return
        chosen = filedialog.askdirectory(initialdir=self.folder, title="Elige la carpeta a revisar", parent=self)
        if chosen:
            self.folder = os.path.normpath(chosen)
            self.folder_label.configure(text=_elide(self.folder))

    def _toggle_search(self):
        if self.busy:
            self.cancel.set()
            self.status.configure(text="Deteniendo…")
            return
        self.busy = True
        self.cancel.clear()
        self.search_btn.configure(text="Detener")
        self.tree.delete(*self.tree.get_children())
        self.files.clear()
        self._update_selection()
        min_size = self.SIZES[self.size_var.get()] * 1024 * 1024
        folder = self.folder

        def progress(scanned, found):
            self.app.post(self.status.configure,
                          text=f"Revisados {format_count(scanned)} archivos… {found} encontrados")

        self.app.run_bg(
            lambda: largefiles.find_large_files(folder, min_size, cancel=self.cancel, progress=progress),
            self._search_done, self._search_failed)

    def _search_failed(self, exc):
        self.busy = False
        self.search_btn.configure(text="Buscar")
        self.status.configure(text=f"Error: {exc}")

    def _search_done(self, result):
        files, scanned = result
        self.busy = False
        self.search_btn.configure(text="Buscar")
        stopped = " (búsqueda detenida)" if self.cancel.is_set() else ""
        total = sum(f.size for f in files)
        if files:
            self.status.configure(text=f"{len(files)} archivos grandes que suman {human_size(total)} — "
                                       f"revisados {format_count(scanned)}{stopped}. Doble clic para abrir su carpeta.")
        else:
            self.status.configure(text=f"No hay archivos tan grandes aquí (revisados {format_count(scanned)}){stopped}.")
        for item in files:
            self.files[item.path] = item
        self._fill()

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        key = {"name": lambda f: f.name.lower(), "size": lambda f: f.size,
               "modified": lambda f: f.mtime, "folder": lambda f: f.folder.lower()}[self.sort_key]
        for item in sorted(self.files.values(), key=key, reverse=self.sort_desc):
            modified = datetime.fromtimestamp(item.mtime).strftime("%d/%m/%Y")
            self.tree.insert("", "end", iid=item.path,
                             values=(item.name, human_size(item.size), modified, item.folder))
        self._update_selection()

    def _sort_by(self, column):
        if self.sort_key == column:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = column, column in ("size", "modified")
        self._fill()

    def _selected(self) -> list[largefiles.LargeFile]:
        return [self.files[iid] for iid in self.tree.selection() if iid in self.files]

    def _update_selection(self):
        selected = self._selected()
        self.reveal_btn.set_enabled(len(selected) == 1)
        self.trash_btn.set_enabled(bool(selected))
        if selected:
            self.selection_label.configure(
                text=f"{len(selected)} seleccionados · {human_size(sum(f.size for f in selected))}")
        else:
            self.selection_label.configure(text="")

    def _reveal(self):
        selected = self._selected()
        if selected:
            try:
                reveal_in_file_manager(selected[0].path)
            except OSError as exc:
                messagebox.showerror(APP_NAME, f"No se pudo abrir la carpeta:\n{exc}", parent=self)

    def _trash(self):
        selected = self._selected()
        if not selected:
            return
        size = human_size(sum(f.size for f in selected))
        names = "\n".join(f"•  {f.name}" for f in selected[:8])
        if len(selected) > 8:
            names += f"\n•  … y {len(selected) - 8} más"
        message = f"¿Enviar {len(selected)} archivo(s) ({size}) a la papelera?\n\n{names}"
        if any(largefiles.is_system_path(f.path) for f in selected):
            message += ("\n\nCuidado: algunos están en carpetas de Windows o de programas instalados. "
                        "Borrarlos puede hacer que un programa deje de funcionar; para quitar un programa, "
                        "mejor desinstálalo desde Configuración.")
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

        self.app.run_bg(work, self._trash_done)

    def _trash_done(self, result):
        done, errors = result
        for item in done:
            self.files.pop(item.path, None)
            if self.tree.exists(item.path):
                self.tree.delete(item.path)
        self._update_selection()
        freed = sum(f.size for f in done)
        if done:
            self.status.configure(text=f"Enviados a la papelera: {len(done)} archivos ({human_size(freed)}). "
                                       "Vacía la papelera para liberar el espacio.")
        if errors:
            messagebox.showwarning(APP_NAME, "No se pudieron mover algunos archivos:\n\n" + "\n".join(errors[:10]),
                                   parent=self)


# --------------------------------------------------------------------------- #
class StartupPage(Page):
    title = "Programas al iniciar"
    subtitle = ("Cuantos menos programas arranquen con el equipo, antes estará listo para usar. "
                "Deshabilitar no desinstala nada y puedes volver a activarlos cuando quieras.")

    def __init__(self, app):
        super().__init__(app)
        self.items: dict[str, startup.StartupItem] = {}

        table = tk.Frame(self.body, bg=C.card, highlightthickness=1, highlightbackground=C.border)
        table.pack(fill="both", expand=True)
        columns = ("name", "state", "scope", "command")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        for column, text, width, stretch in (("name", "Programa", 220, True), ("state", "Estado", 110, False),
                                             ("scope", "Para", 140, False), ("command", "Comando", 420, True)):
            self.tree.heading(column, text=text, anchor="w")
            self.tree.column(column, width=px(width), stretch=stretch)
        self.tree.tag_configure("disabled", foreground=C.faint)
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_buttons())
        self.tree.bind("<Double-1>", lambda e: self._toggle())

        actions = tk.Frame(self.body, bg=C.bg)
        actions.pack(fill="x", pady=(px(10), 0))
        self.toggle_btn = FlatButton(actions, "Deshabilitar", self._toggle)
        self.toggle_btn.pack(side="left")
        FlatButton(actions, "Actualizar", self.refresh, kind="secondary").pack(side="left", padx=(px(10), 0))
        if IS_WINDOWS:
            FlatButton(actions, "Abrir Administrador de tareas", lambda: _launch(["taskmgr", "/0", "/startup"]),
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


# --------------------------------------------------------------------------- #
def _launch(args: list[str]) -> None:
    try:
        ok = shell_open(args[0], " ".join(args[1:]))
    except OSError as exc:
        ok, detail = False, str(exc)
    else:
        detail = "Windows no pudo abrirlo o se canceló."
    if not ok:
        messagebox.showerror(APP_NAME, f"No se pudo abrir {args[0]}:\n{detail}")


def _open(uri: str) -> None:
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
             "Abrir", lambda: _open("ms-settings:appsfeatures")),
            ("Liberador de espacio en disco", "La limpieza oficial de Windows: incluye restos de actualizaciones "
             "y versiones anteriores de Windows.", "Abrir", lambda: _launch(["cleanmgr"])),
            ("Sensor de almacenamiento", "Haz que Windows borre temporales y vacíe la papelera automáticamente.",
             "Configurar", lambda: _open("ms-settings:storagesense")),
            ("Optimizar unidades", "Desfragmenta discos duros y aplica TRIM a los SSD.",
             "Abrir", lambda: _launch(["dfrgui"])),
            ("Administrador de tareas", "Mira qué está usando la CPU, la memoria o el disco ahora mismo.",
             "Abrir", lambda: _launch(["taskmgr"])),
            ("Vaciar caché DNS", "Puede arreglar páginas que no cargan después de cambiar de red.",
             "Vaciar", self._flush_dns),
            ("Reparar archivos de Windows", "Ejecuta «sfc /scannow» para buscar y reparar archivos del sistema "
             "dañados. Tarda varios minutos y pide permiso de administrador.", "Ejecutar", self._run_sfc),
            ("Opciones de energía", "En un PC de sobremesa, el plan «Alto rendimiento» puede dar algo más de velocidad.",
             "Abrir", lambda: _launch(["control", "powercfg.cpl"])),
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


# =========================================================================== #
# Ventana principal
# =========================================================================== #
class Sidebar(tk.Frame):
    ITEMS = (("dashboard", "Resumen"), ("clean", "Limpieza"), ("large", "Archivos grandes"),
             ("startup", "Programas al iniciar"), ("tools", "Herramientas"))

    def __init__(self, app: "App"):
        super().__init__(app, bg=C.sidebar, width=px(230))
        self.app = app
        self.pack_propagate(False)
        self.buttons: dict[str, tuple[tk.Frame, tk.Frame, tk.Label]] = {}

        logo = tk.Frame(self, bg=C.sidebar)
        logo.pack(fill="x", padx=px(20), pady=(px(22), px(26)))
        icon = tk.Canvas(logo, width=px(30), height=px(30), bg=C.sidebar, highlightthickness=0)
        icon.pack(side="left")
        s = px(30)
        round_rect(icon, 0, 0, s, s, px(9), fill=C.accent, outline="")
        icon.create_line(s * 0.28, s * 0.52, s * 0.44, s * 0.68, s * 0.74, s * 0.34, fill=C.on_accent,
                         width=max(2, px(3)), capstyle="round", joinstyle="round")
        label(logo, APP_NAME, F.logo).pack(side="left", padx=(px(10), 0))

        for key, text in self.ITEMS:
            row = tk.Frame(self, bg=C.sidebar, cursor="hand2")
            row.pack(fill="x", padx=px(10), pady=px(1))
            indicator = tk.Frame(row, bg=C.sidebar, width=px(3))
            indicator.pack(side="left", fill="y")
            text_label = label(row, text, F.nav, C.muted, anchor="w", padx=px(14), pady=px(9))
            text_label.pack(side="left", fill="x", expand=True)
            for widget in (row, text_label):
                widget.bind("<Button-1>", lambda e, k=key: app.show(k))
                widget.bind("<Enter>", lambda e, k=key: self._hover(k, True))
                widget.bind("<Leave>", lambda e, k=key: self._hover(k, False))
            self.buttons[key] = (row, indicator, text_label)

        footer = tk.Frame(self, bg=C.sidebar)
        footer.pack(side="bottom", fill="x", padx=px(20), pady=px(18))
        if app.admin:
            label(footer, "● Modo administrador", F.small, C.accent).pack(anchor="w")
        else:
            label(footer, "● Modo normal", F.small, C.muted).pack(anchor="w")
            if IS_WINDOWS:
                label(footer, "Algunas limpiezas del sistema necesitan permisos de administrador.",
                      F.small, C.faint, justify="left", wraplength=px(185)).pack(anchor="w", pady=(px(4), px(8)))
                FlatButton(footer, "Abrir como administrador", app.elevate, kind="secondary", small=True).pack(anchor="w")
        label(footer, f"Versión {__version__}", F.small, C.faint).pack(anchor="w", pady=(px(12), 0))

    def _hover(self, key: str, inside: bool) -> None:
        if key == self.app.current:
            return
        row, indicator, text_label = self.buttons[key]
        color = C.nav_hover if inside else C.sidebar
        for widget in (row, indicator, text_label):
            widget.configure(bg=color)

    def select(self, key: str) -> None:
        for name, (row, indicator, text_label) in self.buttons.items():
            active = name == key
            row.configure(bg=C.card if active else C.sidebar)
            text_label.configure(bg=C.card if active else C.sidebar, fg=C.text if active else C.muted)
            indicator.configure(bg=C.accent if active else C.sidebar)


def _setup_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    row_height = tkfont.Font(root=root, font=F.body).metrics("linespace") + px(12)
    style.configure("Treeview", background=C.card, fieldbackground=C.card, foreground=C.text,
                    rowheight=row_height, borderwidth=0, font=F.body)
    style.map("Treeview", background=[("selected", C.accent_dim)], foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=C.card_hi, foreground=C.muted, relief="flat",
                    borderwidth=0, font=F.small_bold, padding=(px(8), px(6)))
    style.map("Treeview.Heading", background=[("active", C.border)])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Vertical.TScrollbar", background=C.card_hi, troughcolor=C.bg, bordercolor=C.bg,
                    arrowcolor=C.muted, lightcolor=C.card_hi, darkcolor=C.card_hi, gripcount=0)
    style.map("Vertical.TScrollbar", background=[("active", C.border)])
    style.configure("Accent.Horizontal.TProgressbar", troughcolor=C.card_hi, background=C.accent,
                    bordercolor=C.bg, lightcolor=C.accent, darkcolor=C.accent, thickness=px(6))
    style.configure("TCombobox", fieldbackground=C.card_hi, background=C.card_hi, foreground=C.text,
                    arrowcolor=C.text, bordercolor=C.border, lightcolor=C.card_hi, darkcolor=C.card_hi,
                    padding=px(4))
    style.map("TCombobox", fieldbackground=[("readonly", C.card_hi)], foreground=[("readonly", C.text)],
              selectbackground=[("readonly", C.card_hi)], selectforeground=[("readonly", C.text)])
    root.option_add("*TCombobox*Listbox.background", C.card_hi)
    root.option_add("*TCombobox*Listbox.foreground", C.text)
    root.option_add("*TCombobox*Listbox.selectBackground", C.accent_dim)
    root.option_add("*TCombobox*Listbox.font", F.body)


def _app_icon(size: int = 32) -> tk.PhotoImage:
    image = tk.PhotoImage(width=size, height=size)
    radius, center = size / 2 - 0.5, (size - 1) / 2
    for y in range(size):
        row = []
        for x in range(size):
            inside = (x - center) ** 2 + (y - center) ** 2 <= radius ** 2
            row.append(C.accent if inside else C.sidebar)
        image.put("{" + " ".join(row) + "}", to=(0, y))
    # Marca de verificación
    def stroke(x1, y1, x2, y2):
        steps = int(max(abs(x2 - x1), abs(y2 - y1)) * 2) + 1
        for i in range(steps + 1):
            x = x1 + (x2 - x1) * i / steps
            y = y1 + (y2 - y1) * i / steps
            image.put(C.on_accent, to=(int(x) - 1, int(y) - 1, int(x) + 2, int(y) + 2))
    stroke(size * 0.28, size * 0.52, size * 0.44, size * 0.68)
    stroke(size * 0.44, size * 0.68, size * 0.74, size * 0.34)
    return image


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        global SCALE
        SCALE = max(1.0, self.winfo_fpixels("1i") / 96.0)
        F.init(self)
        self.title(APP_NAME)
        self.configure(bg=C.bg)
        width = min(px(1140), self.winfo_screenwidth() - 40)
        height = min(px(740), self.winfo_screenheight() - 80)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(px(960), width), min(px(600), height))
        try:
            self._icon = _app_icon()
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        self.admin = is_admin()
        self.current: str | None = None
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self.report_callback_exception = self._on_tk_error
        _setup_styles(self)

        self.sidebar = Sidebar(self)
        self.sidebar.pack(side="left", fill="y")
        self.content = tk.Frame(self, bg=C.bg)
        self.content.pack(side="left", fill="both", expand=True)
        self.pages: dict[str, Page] = {}
        self.pages["dashboard"] = DashboardPage(self)
        self.pages["clean"] = CleanPage(self)
        self.pages["large"] = LargeFilesPage(self)
        self.pages["startup"] = StartupPage(self)
        self.pages["tools"] = ToolsPage(self)
        self.show("dashboard")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._poll)

    # ------------------------------------------------------------ navegación
    def show(self, key: str) -> None:
        if self.current == key:
            return
        if self.current:
            self.pages[self.current].pack_forget()
        self.current = key
        self.pages[key].pack(fill="both", expand=True)
        self.sidebar.select(key)
        self.pages[key].on_show()

    # ------------------------------------------------------------- hilos
    def post(self, fn, *args, **kwargs) -> None:
        """Ejecuta `fn(*args, **kwargs)` en el hilo de la interfaz (seguro desde otros hilos)."""
        self._queue.put((fn, args, kwargs))

    def _poll(self) -> None:
        try:
            while True:
                fn, args, kwargs = self._queue.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.after(50, self._poll)

    def run_bg(self, work, on_done=None, on_error=None) -> None:
        def runner():
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                self.post(on_error or self._show_error, exc)
                return
            if on_done:
                self.post(on_done, result)

        threading.Thread(target=runner, daemon=True).start()

    def _show_error(self, exc: Exception) -> None:
        messagebox.showerror(APP_NAME, f"Algo salió mal:\n{exc}", parent=self)

    def _on_tk_error(self, exc_type, exc, tb):
        traceback.print_exception(exc_type, exc, tb)
        messagebox.showerror(APP_NAME, f"Algo salió mal:\n{exc}", parent=self)

    # ------------------------------------------------------------- acciones
    def elevate(self) -> None:
        if relaunch_as_admin():
            self.destroy()
        else:
            messagebox.showinfo(APP_NAME, "No se concedieron permisos de administrador.", parent=self)

    def _on_close(self) -> None:
        clean_page = self.pages["clean"]
        if getattr(clean_page, "busy", False):
            if not messagebox.askyesno(APP_NAME, "Hay una operación en curso. ¿Detenerla y salir?", parent=self):
                return
        for page in self.pages.values():
            cancel = getattr(page, "cancel", None)
            if cancel is not None:
                cancel.set()
        self.destroy()


def _prepare_windows_process() -> None:
    if not IS_WINDOWS:
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nítido en pantallas con escalado
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass
    try:
        ctypes.windll.kernel32.SetErrorMode(0x0001)  # sin diálogos de "inserte un disco"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LimpiaPC.App")
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    _prepare_windows_process()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
