"""Widgets reutilizables con el estilo de LimpiaPC."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..platform_utils import IS_MAC
from .theme import C, F, level_color, px, round_rect

if TYPE_CHECKING:  # pragma: no cover
    from .app import App


def label(parent, text="", font=None, fg=None, bg=None, **kwargs) -> tk.Label:
    return tk.Label(parent, text=text, font=font or F.body, fg=fg or C.text,
                    bg=bg or parent.cget("bg"), **kwargs)


def card(parent, padx=18, pady=16) -> tk.Frame:
    return tk.Frame(parent, bg=C.card, padx=px(padx), pady=px(pady),
                    highlightthickness=1, highlightbackground=C.border, highlightcolor=C.border)


def elide(text: str, limit: int = 48) -> str:
    """Acorta rutas largas por el medio."""
    if len(text) <= limit:
        return text
    keep = (limit - 1) // 2
    return text[:keep] + "…" + text[-keep:]


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


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


class StackedBar(tk.Canvas):
    """Barra horizontal dividida en segmentos de colores."""

    def __init__(self, master, bg: str, height: int = 22):
        super().__init__(master, height=px(height), bg=bg, highlightthickness=0, bd=0)
        self.segments: list[tuple[float, str]] = []
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, segments: list[tuple[float, str]]) -> None:
        self.segments = segments
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), int(self.cget("height"))
        if width <= 2:
            return
        round_rect(self, 0, 0, width, height, px(6), fill=C.card_hi, outline="")
        total = sum(value for value, _ in self.segments) or 1
        x = 0.0
        for value, color in self.segments:
            w = width * value / total
            if w >= 1:
                self.create_rectangle(x, 0, x + w, height, fill=color, outline=self.cget("bg"), width=1)
            x += w


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


class Segmented(tk.Frame):
    """Pestañas tipo «botones pegados»."""

    def __init__(self, master, options: list[tuple[str, str]], command):
        super().__init__(master, bg=C.card_hi, padx=px(3), pady=px(3))
        self.command = command
        self.labels: dict[str, tk.Label] = {}
        self.value = options[0][0]
        for key, text in options:
            item = tk.Label(self, text=text, font=F.body_bold, padx=px(14), pady=px(5), cursor="hand2")
            item.pack(side="left")
            item.bind("<Button-1>", lambda e, k=key: self.select(k, notify=True))
            self.labels[key] = item
        self._paint()

    def select(self, key: str, notify: bool = False) -> None:
        self.value = key
        self._paint()
        if notify:
            self.command(key)

    def _paint(self) -> None:
        for key, item in self.labels.items():
            active = key == self.value
            item.configure(bg=C.accent if active else C.card_hi, fg=C.on_accent if active else C.muted)


def make_table(parent, columns: list[tuple[str, str, int, str, bool]], tree_column: tuple | None = None,
               selectmode: str = "extended") -> ttk.Treeview:
    """Crea un Treeview con borde y barra de desplazamiento.

    columns: (id, título, ancho, alineación "w"/"e", estirable)
    tree_column: (título, ancho) para mostrar la columna jerárquica #0.
    """
    frame = tk.Frame(parent, bg=C.card, highlightthickness=1, highlightbackground=C.border)
    frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns],
                        show="tree headings" if tree_column else "headings", selectmode=selectmode)
    if tree_column:
        tree.heading("#0", text=tree_column[0], anchor="w")
        tree.column("#0", width=px(tree_column[1]), stretch=True)
    for column_id, title, width, anchor, stretch in columns:
        tree.heading(column_id, text=title, anchor=anchor)
        tree.column(column_id, width=px(width), anchor=anchor, stretch=stretch)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    tree.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return tree


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

    busy = False

    def on_show(self) -> None:
        pass
