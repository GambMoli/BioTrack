"""Pruebas del motor de limpieza. Ejecutar con:  python -m unittest discover -s tests"""

import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from limpiapc import cleaner, largefiles, trash  # noqa: E402
from limpiapc.cleaner import Category, Target  # noqa: E402
from limpiapc.fsutil import walk_files  # noqa: E402
from limpiapc.platform_utils import human_size, format_duration  # noqa: E402

OLD = time.time() - 3 * 24 * 3600


def make_file(path, size=10, old=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)
    if old:
        os.utime(path, (OLD, OLD))
    return path


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = os.path.realpath(self._tmp.name)
        # El directorio temporal del sistema suele estar fuera de las rutas protegidas,
        # pero "home" apunta a un sitio que controlamos.
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        patcher = mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)


class FormatTests(unittest.TestCase):
    def test_human_size(self):
        self.assertEqual(human_size(0), "0 B")
        self.assertEqual(human_size(1023), "1023 B")
        self.assertEqual(human_size(1536), "1,5 KB")
        self.assertEqual(human_size(150 * 1024 ** 2), "150 MB")
        self.assertEqual(human_size(2.25 * 1024 ** 3), "2,2 GB")

    def test_duration(self):
        self.assertEqual(format_duration(59), "0 min")
        self.assertEqual(format_duration(3 * 3600 + 120), "3 h 2 min")
        self.assertEqual(format_duration(2 * 86400 + 3600), "2 d 1 h")


class WalkTests(TempDirTest):
    def test_does_not_follow_symlinks(self):
        outside = os.path.join(self.tmp, "outside")
        make_file(os.path.join(outside, "precious.txt"))
        cache = os.path.join(self.tmp, "cache")
        make_file(os.path.join(cache, "a.tmp"))
        os.symlink(outside, os.path.join(cache, "link_dir"))
        os.symlink(os.path.join(outside, "precious.txt"), os.path.join(cache, "link_file"))
        found = sorted(os.path.basename(p) for p, _ in walk_files(cache))
        self.assertEqual(found, ["a.tmp"])

    def test_cancel(self):
        cache = os.path.join(self.tmp, "cache")
        for i in range(5):
            make_file(os.path.join(cache, f"d{i}", "f.tmp"))
        event = threading.Event()
        event.set()
        self.assertEqual(list(walk_files(cache, cancel=event)), [])


class ProtectionTests(TempDirTest):
    def test_protected_paths(self):
        self.assertTrue(cleaner.is_protected(os.path.abspath(os.sep)))
        self.assertTrue(cleaner.is_protected(self.home))
        self.assertTrue(cleaner.is_protected(os.path.join(self.home, "Documents")))
        self.assertFalse(cleaner.is_protected(os.path.join(self.home, "some", "cache")))

    def test_protected_root_is_never_scanned(self):
        make_file(os.path.join(self.home, "Documents", "tesis.docx"), old=True)
        category = Category("bad", "Sistema", "x", "x", (Target(self.home),))
        self.assertFalse(category.is_available())
        result = cleaner.scan_category(category)
        self.assertEqual(result.count, 0)

    def test_protected_root_allowed_for_specific_file_patterns(self):
        make_file(os.path.join(self.home, "MEMORY.DMP"), size=50)
        make_file(os.path.join(self.home, "important.txt"), size=50)
        make_file(os.path.join(self.home, "sub", "MEMORY.DMP"), size=50)
        category = Category("dmp", "Sistema", "x", "x",
                            (Target(self.home, patterns=("memory.dmp",), recursive=False),))
        result = cleaner.scan_category(category)
        self.assertEqual([os.path.basename(p) for r in result.roots for p, _ in r.files], ["MEMORY.DMP"])


class ScanCleanTests(TempDirTest):
    def test_min_age_is_respected(self):
        temp = os.path.join(self.tmp, "Temp")
        make_file(os.path.join(temp, "old.tmp"), size=100, old=True)
        new = make_file(os.path.join(temp, "new.tmp"), size=100)
        # ctime (creación en Windows) no se puede falsear: adelantamos el reloj 48 h
        # y dejamos "new.tmp" modificado justo en ese "ahora".
        future = time.time() + 48 * 3600
        os.utime(new, (future, future))
        category = Category("t", "Sistema", "x", "x", (Target(temp, min_age_hours=24),))
        with mock.patch.object(cleaner.time, "time", return_value=future):
            result = cleaner.scan_category(category)
        self.assertEqual(result.count, 1)
        self.assertEqual(result.size, 100)
        cleaned = cleaner.clean_category(category, result)
        self.assertEqual(cleaned.deleted, 1)
        self.assertEqual(cleaned.freed, 100)
        self.assertFalse(os.path.exists(os.path.join(temp, "old.tmp")))
        self.assertTrue(os.path.exists(os.path.join(temp, "new.tmp")))

    def test_glob_sub_targets_and_patterns(self):
        user_data = os.path.join(self.tmp, "Chrome", "User Data")
        make_file(os.path.join(user_data, "Default", "Cache", "Cache_Data", "data_0"), size=10)
        make_file(os.path.join(user_data, "Profile 1", "Cache", "f_0001"), size=20)
        make_file(os.path.join(user_data, "Default", "Login Data"), size=30)  # ¡no tocar!
        make_file(os.path.join(user_data, "Default", "History"), size=30)
        category = Category("chrome", "Navegadores", "Chrome", "",
                            cleaner._chromium(user_data))
        result = cleaner.scan_category(category)
        self.assertEqual(result.size, 30)
        cleaner.clean_category(category, result)
        self.assertTrue(os.path.exists(os.path.join(user_data, "Default", "Login Data")))
        self.assertTrue(os.path.exists(os.path.join(user_data, "Default", "History")))
        self.assertFalse(os.path.exists(os.path.join(user_data, "Profile 1", "Cache", "f_0001")))
        # La carpeta raíz de la caché se conserva.
        self.assertTrue(os.path.isdir(os.path.join(user_data, "Profile 1", "Cache")))

    def test_nested_roots_are_not_counted_twice(self):
        base = os.path.join(self.tmp, "app")
        make_file(os.path.join(base, "Cache", "inner", "a"), size=10)
        category = Category("x", "Sistema", "x", "x",
                            (Target(os.path.join(base, "Cache", "inner")), Target(os.path.join(base, "Cache"))))
        result = cleaner.scan_category(category)
        self.assertEqual(result.count, 1)

    def test_remove_empty_dirs_keeps_root(self):
        temp = os.path.join(self.tmp, "Temp")
        make_file(os.path.join(temp, "setup123", "deep", "a.tmp"), old=True)
        category = Category("t", "Sistema", "x", "x", (Target(temp, remove_empty_dirs=True),))
        cleaner.clean_category(category, cleaner.scan_category(category))
        self.assertTrue(os.path.isdir(temp))
        self.assertEqual(os.listdir(temp), [])

    def test_clean_never_deletes_outside_root(self):
        temp = os.path.join(self.tmp, "Temp")
        precious = make_file(os.path.join(self.tmp, "precious.txt"))
        make_file(os.path.join(temp, "a.tmp"))
        category = Category("t", "Sistema", "x", "x", (Target(temp),))
        result = cleaner.scan_category(category)
        # Simula una lista manipulada con una ruta fuera de la carpeta.
        result.roots[0].files.append((precious, 10))
        result.roots[0].files.append((os.path.join(temp, "..", "precious.txt"), 10))
        cleaned = cleaner.clean_category(category, result)
        self.assertTrue(os.path.exists(precious))
        self.assertEqual(cleaned.deleted, 1)
        self.assertEqual(cleaned.skipped, 2)

    def test_symlink_swapped_in_after_scan_is_not_followed(self):
        temp = os.path.join(self.tmp, "Temp")
        outside = os.path.join(self.tmp, "outside")
        precious = make_file(os.path.join(outside, "a.tmp"))
        victim = make_file(os.path.join(temp, "a.tmp"))
        category = Category("t", "Sistema", "x", "x", (Target(temp),))
        result = cleaner.scan_category(category)
        os.remove(victim)
        os.symlink(precious, victim)
        cleaner.clean_category(category, result)
        self.assertTrue(os.path.exists(precious))

    def test_already_deleted_files_are_ignored(self):
        temp = os.path.join(self.tmp, "Temp")
        path = make_file(os.path.join(temp, "a.tmp"))
        category = Category("t", "Sistema", "x", "x", (Target(temp),))
        result = cleaner.scan_category(category)
        os.remove(path)
        cleaned = cleaner.clean_category(category, result)
        self.assertEqual((cleaned.deleted, cleaned.skipped, cleaned.freed), (0, 0, 0))

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "permisos POSIX")
    def test_locked_files_are_skipped(self):
        temp = os.path.join(self.tmp, "Temp")
        locked_dir = os.path.join(temp, "locked")
        make_file(os.path.join(locked_dir, "a.tmp"))
        make_file(os.path.join(temp, "b.tmp"))
        category = Category("t", "Sistema", "x", "x", (Target(temp),))
        result = cleaner.scan_category(category)
        os.chmod(locked_dir, 0o500)
        try:
            cleaned = cleaner.clean_category(category, result)
        finally:
            os.chmod(locked_dir, 0o700)
        self.assertEqual((cleaned.deleted, cleaned.skipped), (1, 1))

    def test_builtin_catalog_is_well_formed(self):
        categories = cleaner.build_categories()
        ids = [c.id for c in categories]
        self.assertEqual(len(ids), len(set(ids)))
        for category in categories:
            self.assertIn(category.group, cleaner.GROUPS)
            for target in category.targets:
                self.assertNotIn("*", target.base)


class WindowsCatalogTests(TempDirTest):
    """Ejecuta el catálogo de Windows con variables de entorno apuntando a carpetas falsas."""

    def test_windows_catalog_finds_only_caches(self):
        local = os.path.join(self.tmp, "Local")
        roaming = os.path.join(self.tmp, "Roaming")
        windir = os.path.join(self.tmp, "Windows")
        env = {"LOCALAPPDATA": local, "APPDATA": roaming, "SystemRoot": windir,
               "ProgramData": os.path.join(self.tmp, "ProgramData"), "TEMP": os.path.join(self.tmp, "Temp")}
        chrome = os.path.join(local, "Google", "Chrome", "User Data")
        make_file(os.path.join(chrome, "Default", "Cache", "Cache_Data", "data_1"), size=100)
        make_file(os.path.join(chrome, "Default", "Login Data"), size=100)
        make_file(os.path.join(chrome, "Default", "Bookmarks"), size=100)
        explorer = os.path.join(local, "Microsoft", "Windows", "Explorer")
        make_file(os.path.join(explorer, "thumbcache_256.db"), size=7)
        make_file(os.path.join(explorer, "iconcache_16.db"), size=7)
        make_file(os.path.join(windir, "MEMORY.DMP"), size=9)
        make_file(os.path.join(windir, "System32", "kernel32.dll"), size=9)
        make_file(os.path.join(roaming, "discord", "Cache", "Cache_Data", "f_1"), size=5)
        make_file(os.path.join(roaming, "discord", "Local Storage", "leveldb", "000.log"), size=5)

        with mock.patch.dict(os.environ, env):
            categories = {c.id: c for c in cleaner._windows_categories()}
            files = {}
            for cid in ("chrome", "thumbnails", "error_reports_system", "discord"):
                result = cleaner.scan_category(categories[cid])
                files[cid] = sorted(os.path.basename(p) for r in result.roots for p, _ in r.files)

        self.assertEqual(files["chrome"], ["data_1"])
        self.assertEqual(files["thumbnails"], ["thumbcache_256.db"])
        self.assertEqual(files["error_reports_system"], ["MEMORY.DMP"])
        self.assertEqual(files["discord"], ["f_1"])


class FakeWinreg:
    """Registro de Windows en memoria con la API mínima que usa startup.py."""

    HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE = 1, 2
    KEY_READ, KEY_SET_VALUE, KEY_WOW64_64KEY, REG_BINARY, REG_SZ = 1, 2, 4, 3, 1

    def __init__(self):
        self.data = {}

    class _Key:
        def __init__(self, store):
            self.store = store

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _path(self, hive, path):
        return (hive, path.lower())

    def OpenKey(self, hive, path, reserved=0, access=0):
        if self._path(hive, path) not in self.data:
            raise OSError("no existe")
        return self._Key(self.data[self._path(hive, path)])

    def CreateKeyEx(self, hive, path, reserved=0, access=0):
        return self._Key(self.data.setdefault(self._path(hive, path), {}))

    def EnumValue(self, key, index):
        items = list(key.store.items())
        if index >= len(items):
            raise OSError("fin")
        name, data = items[index]
        return name, data, 0

    def SetValueEx(self, key, name, reserved, kind, data):
        key.store[name] = data


class StartupTests(TempDirTest):
    def test_windows_startup_toggle(self):
        from limpiapc import startup

        reg = FakeWinreg()
        base = r"Software\Microsoft\Windows\CurrentVersion"
        reg.data[(reg.HKEY_CURRENT_USER, (base + r"\Run").lower())] = {"Spotify": r"C:\Spotify.exe /min"}
        reg.data[(reg.HKEY_LOCAL_MACHINE, (base + r"\Run").lower())] = {"Antivirus": r"C:\av.exe"}
        reg.data[(reg.HKEY_CURRENT_USER, (base + r"\Explorer\StartupApproved\Run").lower())] = {
            "Spotify": b"\x03" + b"\x00" * 11}
        appdata = os.path.join(self.tmp, "Roaming")
        make_file(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "Notion.lnk"))
        make_file(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "desktop.ini"))

        with mock.patch.object(startup, "winreg", reg, create=True), \
                mock.patch.object(startup, "IS_WINDOWS", True), \
                mock.patch.dict(os.environ, {"APPDATA": appdata, "ProgramData": os.path.join(self.tmp, "PD")}):
            items = {i.name: i for i in startup.list_startup_items(admin=False)}
            self.assertEqual(sorted(items), ["Antivirus", "Notion", "Spotify"])
            self.assertFalse(items["Spotify"].enabled)
            self.assertTrue(items["Notion"].enabled)
            self.assertFalse(items["Antivirus"].can_toggle)  # de equipo: requiere admin
            self.assertTrue(items["Spotify"].can_toggle)

            startup.set_enabled(items["Notion"], False)
            startup.set_enabled(items["Spotify"], True)
            again = {i.name: i for i in startup.list_startup_items(admin=False)}
            self.assertFalse(again["Notion"].enabled)
            self.assertTrue(again["Spotify"].enabled)
            folder_key = (reg.HKEY_CURRENT_USER, (base + r"\Explorer\StartupApproved\StartupFolder").lower())
            self.assertEqual(reg.data[folder_key]["Notion.lnk"][0], 3)
            self.assertEqual(len(reg.data[folder_key]["Notion.lnk"]), 12)
            with self.assertRaises(OSError):
                startup.set_enabled(items["Antivirus"], False)


class LargeFilesTests(TempDirTest):
    def test_top_files_sorted(self):
        folder = os.path.join(self.tmp, "data")
        make_file(os.path.join(folder, "small.bin"), size=10)
        make_file(os.path.join(folder, "a", "big.bin"), size=5000)
        make_file(os.path.join(folder, "b", "bigger.bin"), size=9000)
        make_file(os.path.join(folder, "c", "medium.bin"), size=2000)
        files, scanned = largefiles.find_large_files(folder, 1000, limit=2)
        self.assertEqual(scanned, 4)
        self.assertEqual([f.name for f in files], ["bigger.bin", "big.bin"])

    def test_skips_system_dirs(self):
        folder = os.path.join(self.tmp, "drive")
        make_file(os.path.join(folder, "$Recycle.Bin", "x.bin"), size=5000)
        make_file(os.path.join(folder, "pagefile.sys"), size=5000)
        make_file(os.path.join(folder, "video.mp4"), size=5000)
        files, _ = largefiles.find_large_files(folder, 1000)
        self.assertEqual([f.name for f in files], ["video.mp4"])


@unittest.skipIf(os.name == "nt" or sys.platform == "darwin", "papelera freedesktop")
class TrashTests(TempDirTest):
    def test_send_to_trash_freedesktop(self):
        data_home = os.path.join(self.tmp, "share")
        path = make_file(os.path.join(self.tmp, "video.mp4"))
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": data_home, "LIMPIAPC_NO_GIO": "1"}):
            trash.send_to_trash(path)
            other = make_file(os.path.join(self.tmp, "video.mp4"))
            trash.send_to_trash(other)
        self.assertFalse(os.path.exists(path))
        files = sorted(os.listdir(os.path.join(data_home, "Trash", "files")))
        infos = sorted(os.listdir(os.path.join(data_home, "Trash", "info")))
        self.assertEqual(files, ["video 2.mp4", "video.mp4"])
        self.assertEqual(infos, ["video 2.mp4.trashinfo", "video.mp4.trashinfo"])


if __name__ == "__main__":
    unittest.main()
