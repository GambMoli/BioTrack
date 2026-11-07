"""Pantalla de resumen: CPU, RAM, discos y programas que más memoria usan."""

from __future__ import annotations

import random
import time
import tkinter as tk

from .. import system_info
from ..platform_utils import format_duration, human_size, top_memory_processes
from .theme import C, F, px
from .widgets import FlatButton, Page, UsageBar, card, label, plural

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
    "Usa «Organizar» con tu carpeta de Descargas de vez en cuando para no acumular instaladores viejos.",
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
        FlatButton(clean_card, "Buscar basura", self._analyze, small=True).pack(anchor="w")

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
        self.clean_value.configure(text=human_size(size))
        if not size:
            self.clean_note.configure(text="Nada pendiente de limpiar en lo seleccionado.")
            return
        where = plural(categories, "categoría seleccionada", "categorías seleccionadas")
        self.clean_note.configure(text=f"En {where}. Ve a Limpieza para liberarlo.")

    def set_cleaned(self, freed: int) -> None:
        self.clean_title.configure(text="ESPACIO LIBERADO")
        self.clean_value.configure(text=f"−{human_size(freed)}")
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
            FlatButton(line, "¿Qué ocupa?", lambda m=disk.mount: self.app.analyze_space(m),
                       kind="secondary", small=True).pack(side="right", padx=(px(10), 0))
            label(line, f"{human_size(disk.free)} libres de {human_size(disk.total)}", F.small, C.muted).pack(side="right")
            bar = UsageBar(row, C.card, height=12)
            bar.pack(fill="x", pady=(px(5), 0))
            bar.set(disk.fraction)
            if disk.fraction >= 0.9:
                label(row, "Casi lleno: Windows va más lento con menos de un 10 % libre.", F.small, C.warn).pack(
                    anchor="w", pady=(px(3), 0))

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
