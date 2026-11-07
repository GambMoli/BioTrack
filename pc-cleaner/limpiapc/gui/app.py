"""Ventana principal de LimpiaPC."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import traceback
from tkinter import messagebox

from .. import APP_NAME, __version__
from ..platform_utils import IS_WINDOWS, is_admin, relaunch_as_admin
from . import theme
from .clean import CleanPage
from .dashboard import DashboardPage
from .duplicates_page import DuplicatesPage
from .organize import OrganizePage
from .space import SpacePage
from .startup_page import StartupPage
from .theme import C, F, px, round_rect
from .tools import ToolsPage
from .widgets import FlatButton, Page, label


class Sidebar(tk.Frame):
    ITEMS = (("dashboard", "Resumen"), ("space", "Análisis de espacio"), ("clean", "Limpieza"),
             ("organize", "Organizar"), ("duplicates", "Duplicados"), ("startup", "Programas al iniciar"),
             ("tools", "Herramientas"))

    def __init__(self, app: "App"):
        super().__init__(app, bg=C.sidebar, width=px(230))
        self.app = app
        self.pack_propagate(False)
        self.buttons: dict[str, tuple[tk.Frame, tk.Frame, tk.Label]] = {}

        logo = tk.Frame(self, bg=C.sidebar)
        logo.pack(fill="x", padx=px(20), pady=(px(22), px(26)))
        s = px(30)
        icon = tk.Canvas(logo, width=s, height=s, bg=C.sidebar, highlightthickness=0)
        icon.pack(side="left")
        round_rect(icon, 0, 0, s, s, px(9), fill=C.accent, outline="")
        icon.create_line(s * 0.28, s * 0.52, s * 0.44, s * 0.68, s * 0.74, s * 0.34, fill=C.on_accent,
                         width=max(2, px(3)), capstyle="round", joinstyle="round")
        label(logo, APP_NAME, F.logo).pack(side="left", padx=(px(10), 0))

        for key, text in self.ITEMS:
            row = tk.Frame(self, bg=C.sidebar, cursor="hand2")
            row.pack(fill="x", padx=px(10), pady=px(1))
            indicator = tk.Frame(row, bg=C.sidebar, width=px(3))
            indicator.pack(side="left", fill="y")
            text_label = label(row, text, F.nav, C.muted, anchor="w", padx=px(14), pady=px(8))
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
                label(footer, "Algunas limpiezas y carpetas del sistema necesitan permisos de administrador.",
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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        theme.set_scale(self)
        F.init(self)
        self.title(APP_NAME)
        self.configure(bg=C.bg)
        width = min(px(1180), self.winfo_screenwidth() - 40)
        height = min(px(760), self.winfo_screenheight() - 80)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(px(980), width), min(px(620), height))
        try:
            self._icon = theme.app_icon()
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass

        self.admin = is_admin()
        self.current: str | None = None
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self.report_callback_exception = self._on_tk_error
        theme.setup_styles(self)

        self.sidebar = Sidebar(self)
        self.sidebar.pack(side="left", fill="y")
        self.content = tk.Frame(self, bg=C.bg)
        self.content.pack(side="left", fill="both", expand=True)
        self.pages: dict[str, Page] = {}
        for key, page_class in (("dashboard", DashboardPage), ("space", SpacePage), ("clean", CleanPage),
                                ("organize", OrganizePage), ("duplicates", DuplicatesPage),
                                ("startup", StartupPage), ("tools", ToolsPage)):
            self.pages[key] = page_class(self)
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

    def analyze_space(self, path: str) -> None:
        page = self.pages["space"]
        self.show("space")
        if not page.busy:
            page.set_location(path)
            page.start(path)

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
        if any(page.busy for page in self.pages.values()):
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
