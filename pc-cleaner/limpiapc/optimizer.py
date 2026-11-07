"""Optimizar Windows: ajustes reversibles del registro y apps preinstaladas innecesarias.

Cada ajuste guarda el valor original antes de cambiarlo (en %LOCALAPPDATA%\\LimpiaPC),
así que «Restaurar» deja todo exactamente como estaba.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Optional

from .organizer import data_dir
from .platform_utils import IS_WINDOWS

HKCU, HKLM = "HKCU", "HKLM"
CDM = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"


@dataclass(frozen=True)
class RegValue:
    hive: str
    path: str
    name: str
    value: int  # todos son DWORD


@dataclass(frozen=True)
class Tweak:
    id: str
    name: str
    description: str
    values: tuple
    needs_admin: bool = False
    default_on: bool = True
    warning: str = ""


TWEAKS = (
    Tweak("ads", "Quitar anuncios y sugerencias de Windows",
          "Apps sugeridas en Inicio, «consejos» en la pantalla de bloqueo, apps que se instalan solas "
          "(Candy Crush y similares) y sugerencias en Configuración.",
          tuple(RegValue(HKCU, CDM, name, 0) for name in (
              "SilentInstalledAppsEnabled", "SystemPaneSuggestionsEnabled", "SoftLandingEnabled",
              "SubscribedContent-338388Enabled", "SubscribedContent-338389Enabled",
              "SubscribedContent-338393Enabled", "SubscribedContent-353694Enabled",
              "SubscribedContent-353696Enabled", "RotatingLockScreenOverlayEnabled",
              "PreInstalledAppsEnabled", "OemPreInstalledAppsEnabled"))),
    Tweak("bing", "Quitar la búsqueda web (Bing) del menú Inicio",
          "Al buscar en Inicio solo aparecen tus apps y archivos: más rápido y sin resultados de internet.",
          (RegValue(HKCU, r"Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", 1),
           RegValue(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0))),
    Tweak("ad_id", "Desactivar el identificador de publicidad",
          "Las apps dejan de usar un ID para mostrarte anuncios personalizados.",
          (RegValue(HKCU, r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0),)),
    Tweak("telemetry", "Reducir la telemetría al mínimo",
          "Windows envía a Microsoft solo los datos de diagnóstico imprescindibles y deja de pedirte opiniones.",
          (RegValue(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0),
           RegValue(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "DoNotShowFeedbackNotifications", 1),
           RegValue(HKCU, r"Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", 0)),
          needs_admin=True),
    Tweak("gamedvr", "Desactivar la grabación de juegos en segundo plano",
          "Xbox Game Bar deja de grabar en segundo plano: más FPS en juegos. Puedes seguir haciendo capturas.",
          (RegValue(HKCU, r"System\GameConfigStore", "GameDVR_Enabled", 0),
           RegValue(HKCU, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0))),
    Tweak("background_apps", "Que las apps de la Tienda no funcionen en segundo plano",
          "Ahorra memoria y batería. Las apps siguen funcionando normal cuando las abres.",
          (RegValue(HKCU, r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
                    "GlobalUserDisabled", 1),),
          warning="Algunas apps (correo, calendario) no avisarán de novedades si están cerradas."),
    Tweak("transparency", "Quitar transparencias",
          "Menos efectos visuales: en PCs justos de gráfica o RAM se nota más fluido.",
          (RegValue(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    "EnableTransparency", 0),), default_on=False),
    Tweak("startup_delay", "Arrancar los programas de inicio sin esperar",
          "Quita la pausa de unos segundos que Windows mete antes de abrir los programas de inicio.",
          (RegValue(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize",
                    "StartupDelayInMSec", 0),), default_on=False),
)


@dataclass(frozen=True)
class BloatApp:
    pattern: str  # nombre del paquete Appx (comodines de PowerShell)
    name: str


BLOAT_APPS = (
    BloatApp("king.com.*", "Juegos de King (Candy Crush…)"),
    BloatApp("Microsoft.MicrosoftSolitaireCollection", "Microsoft Solitaire Collection"),
    BloatApp("Clipchamp.Clipchamp", "Clipchamp (editor de vídeo)"),
    BloatApp("Microsoft.BingNews", "Noticias"),
    BloatApp("Microsoft.BingWeather", "El Tiempo"),
    BloatApp("Microsoft.BingSearch", "Búsqueda de Bing"),
    BloatApp("Microsoft.GetHelp", "Obtener ayuda"),
    BloatApp("Microsoft.Getstarted", "Consejos"),
    BloatApp("Microsoft.MicrosoftOfficeHub", "Microsoft 365 (anuncio de Office)"),
    BloatApp("Microsoft.People", "Contactos"),
    BloatApp("Microsoft.WindowsFeedbackHub", "Centro de opiniones"),
    BloatApp("Microsoft.WindowsMaps", "Mapas"),
    BloatApp("Microsoft.ZuneVideo", "Películas y TV"),
    BloatApp("Microsoft.MixedReality.Portal", "Portal de realidad mixta"),
    BloatApp("Microsoft.Microsoft3DViewer", "Visor 3D"),
    BloatApp("Microsoft.SkypeApp", "Skype"),
    BloatApp("Microsoft.Todos", "Microsoft To Do"),
    BloatApp("Microsoft.PowerAutomateDesktop", "Power Automate"),
    BloatApp("MicrosoftCorporationII.QuickAssist", "Asistencia rápida"),
    BloatApp("Microsoft.549981C3F5F10", "Cortana"),
    BloatApp("*TikTok*", "TikTok"),
    BloatApp("*Disney*", "Disney+"),
    BloatApp("*SpotifyMusic*", "Spotify (preinstalado)"),
    BloatApp("*Facebook*", "Facebook"),
    BloatApp("*Instagram*", "Instagram"),
    BloatApp("AmazonVideo.PrimeVideo", "Prime Video"),
)


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #
class Registry:
    """Acceso mínimo al registro (inyectable en las pruebas)."""

    def __init__(self, winreg_module=None):
        if winreg_module is None:
            import winreg as winreg_module  # noqa: PLC0415
        self.w = winreg_module

    def _hive(self, hive: str):
        return self.w.HKEY_CURRENT_USER if hive == HKCU else self.w.HKEY_LOCAL_MACHINE

    def get(self, v: RegValue) -> Optional[int]:
        try:
            with self.w.OpenKey(self._hive(v.hive), v.path, 0, self.w.KEY_READ | self.w.KEY_WOW64_64KEY) as key:
                data, _ = self.w.QueryValueEx(key, v.name)
                return int(data)
        except (OSError, ValueError, TypeError):
            return None

    def set(self, v: RegValue, value: Optional[int]) -> None:
        """value=None borra el valor (vuelve a «sin configurar»)."""
        access = self.w.KEY_SET_VALUE | self.w.KEY_WOW64_64KEY
        if value is None:
            try:
                with self.w.OpenKey(self._hive(v.hive), v.path, 0, access) as key:
                    self.w.DeleteValue(key, v.name)
            except OSError:
                pass
            return
        with self.w.CreateKeyEx(self._hive(v.hive), v.path, 0, access) as key:
            self.w.SetValueEx(key, v.name, 0, self.w.REG_DWORD, int(value))


def _backup_path() -> str:
    return os.path.join(data_dir(), "ajustes-originales.json")


def _load_backup() -> dict:
    try:
        with open(_backup_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_backup(backup: dict) -> None:
    os.makedirs(os.path.dirname(_backup_path()), exist_ok=True)
    with open(_backup_path(), "w", encoding="utf-8") as fh:
        json.dump(backup, fh, indent=1)


def _key(v: RegValue) -> str:
    return f"{v.hive}\\{v.path}\\{v.name}"


def is_applied(tweak: Tweak, registry: Registry) -> bool:
    return all(registry.get(v) == v.value for v in tweak.values)


def apply_tweak(tweak: Tweak, registry: Registry) -> None:
    backup = _load_backup()
    for v in tweak.values:
        backup.setdefault(_key(v), registry.get(v))  # el original de verdad, solo la primera vez
    _save_backup(backup)
    for v in tweak.values:
        registry.set(v, v.value)


def restore_all(registry: Registry) -> int:
    """Devuelve cada valor tocado por LimpiaPC a como estaba. Devuelve cuántos restauró."""
    backup = _load_backup()
    by_key = {_key(v): v for t in TWEAKS for v in t.values}
    restored = 0
    for key, original in backup.items():
        v = by_key.get(key)
        if v is None:
            continue
        registry.set(v, original)
        restored += 1
    try:
        os.remove(_backup_path())
    except OSError:
        pass
    return restored


def has_backup() -> bool:
    return bool(_load_backup())


# --------------------------------------------------------------------------- #
# Apps preinstaladas (PowerShell Appx)
# --------------------------------------------------------------------------- #
def installed_bloat() -> list[tuple[BloatApp, list[str]]]:
    """[(app, [nombres de paquete instalados])] solo para las que estén instaladas."""
    if not IS_WINDOWS:
        return []
    from .winsys import powershell

    patterns = ",".join(f"'{a.pattern}'" for a in BLOAT_APPS)
    script = (f"foreach($p in @({patterns})){{ Get-AppxPackage -Name $p | "
              "ForEach-Object { Write-Output \"$p|$($_.PackageFullName)\" } }")
    try:
        code, out = powershell(script, timeout=180)
    except Exception:  # noqa: BLE001
        return []
    found: dict[str, list[str]] = {}
    for line in out.splitlines():
        if "|" in line:
            pattern, full = line.strip().split("|", 1)
            found.setdefault(pattern, []).append(full)
    return [(a, found[a.pattern]) for a in BLOAT_APPS if a.pattern in found]


_PACKAGE_RE = re.compile(r"^[A-Za-z0-9._~-]+$")


def remove_app(packages: list[str]) -> tuple[int, str]:
    from .winsys import powershell

    safe = [p for p in packages if _PACKAGE_RE.match(p)]
    if not safe:
        return 1, "Nombre de paquete no válido."
    script = "$ErrorActionPreference='Stop';" + "".join(f"Remove-AppxPackage -Package '{p}';" for p in safe)
    return powershell(script, timeout=600)
