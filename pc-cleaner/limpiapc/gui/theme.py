"""Colores, fuentes, escalado para pantallas HiDPI y estilos ttk."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

SCALE = 1.0


def set_scale(root: tk.Misc) -> None:
    global SCALE
    SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)


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
    title = body = body_bold = small = small_bold = big = logo = nav = h2 = None

    @classmethod
    def init(cls, root: tk.Misc) -> None:
        available = {name.lower(): name for name in tkfont.families(root)}
        for candidate in ("Segoe UI", "Segoe UI Variable Text", "Inter", "Ubuntu", "Noto Sans",
                          "DejaVu Sans", "Liberation Sans", "Arial"):
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


_BAR_CACHE: dict = {}


def bar_image(fraction: float, color: str = C.accent) -> tk.PhotoImage:
    """Mini barra de porcentaje para mostrar dentro de una tabla (Treeview)."""
    steps = 40
    filled_steps = max(0, min(steps, round(fraction * steps)))
    key = (filled_steps, color)
    if key not in _BAR_CACHE:
        width, height = px(56), px(9)
        image = tk.PhotoImage(width=width + px(8), height=height)
        image.put(C.card, to=(0, 0, width + px(8), height))
        image.put(C.card_hi, to=(0, 0, width, height))
        filled = int(width * filled_steps / steps)
        if filled:
            image.put(color, to=(0, 0, max(1, filled), height))
        _BAR_CACHE[key] = image
    return _BAR_CACHE[key]


def setup_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    row_height = tkfont.Font(root=root, font=F.body).metrics("linespace") + px(12)
    style.configure("Treeview", background=C.card, fieldbackground=C.card, foreground=C.text,
                    rowheight=row_height, borderwidth=0, font=F.body, indent=px(16))
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


def app_icon(size: int = 32) -> tk.PhotoImage:
    image = tk.PhotoImage(width=size, height=size)
    radius, center = size / 2 - 0.5, (size - 1) / 2
    for y in range(size):
        row = [C.accent if (x - center) ** 2 + (y - center) ** 2 <= radius ** 2 else C.sidebar
               for x in range(size)]
        image.put("{" + " ".join(row) + "}", to=(0, y))

    def stroke(x1, y1, x2, y2):
        steps = int(max(abs(x2 - x1), abs(y2 - y1)) * 2) + 1
        for i in range(steps + 1):
            x = x1 + (x2 - x1) * i / steps
            y = y1 + (y2 - y1) * i / steps
            image.put(C.on_accent, to=(int(x) - 1, int(y) - 1, int(x) + 2, int(y) + 2))

    stroke(size * 0.28, size * 0.52, size * 0.44, size * 0.68)
    stroke(size * 0.44, size * 0.68, size * 0.74, size * 0.34)
    return image
