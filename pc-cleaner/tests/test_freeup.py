"""Pruebas de «Liberar espacio»: node_modules, detección, ejecución y Liberador de espacio."""

import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from limpiapc import cleaner, freeup, winsys  # noqa: E402
from limpiapc.cleaner import Category, Target  # noqa: E402
from test_core import TempDirTest, make_file  # noqa: E402

OLD = time.time() - 90 * 86400


def make_project(root, name, size=1000, old=True):
    project = os.path.join(root, name)
    make_file(os.path.join(project, "package.json"), size=50)
    make_file(os.path.join(project, "src", "index.js"), size=50)
    make_file(os.path.join(project, "node_modules", "react", "index.js"), size=size)
    make_file(os.path.join(project, "node_modules", "react", "node_modules", "x", "y.js"), size=10)
    if old:
        for entry in os.scandir(project):
            os.utime(entry.path, (OLD, OLD))
    return project


class NodeModulesTests(TempDirTest):
    def test_finds_only_old_real_projects(self):
        root = os.path.join(self.tmp, "home")
        make_project(os.path.join(root, "Proyectos"), "viejo", size=5000)
        make_project(os.path.join(root, "Proyectos"), "activo", old=False)
        make_project(os.path.join(root, ".vscode", "extensions"), "extension")  # carpeta oculta: no
        make_project(os.path.join(root, "AppData", "Roaming", "npm"), "global")  # programas: no
        make_file(os.path.join(root, "suelto", "node_modules", "a.js"))  # sin package.json: no
        found = freeup.find_old_node_modules(root)
        self.assertEqual([n.project for n in found], ["viejo"])
        self.assertEqual(found[0].size, 5010)

    def test_execute_removes_node_modules_but_not_code(self):
        root = os.path.join(self.tmp, "home")
        project = make_project(root, "viejo")
        found = freeup.find_old_node_modules(root)
        task = freeup.FreeTask("node_modules", "Opcional", "x", "x", payload=found)
        result = freeup.execute(task)
        self.assertEqual(result.freed, 1010)
        self.assertFalse(os.path.exists(os.path.join(project, "node_modules")))
        self.assertTrue(os.path.exists(os.path.join(project, "src", "index.js")))
        self.assertTrue(os.path.exists(os.path.join(project, "package.json")))


class DetectTests(TempDirTest):
    def _categories(self):
        temp = os.path.join(self.tmp, "Temp")
        make_file(os.path.join(temp, "a.tmp"), size=300, old=True)
        npm = os.path.join(self.tmp, "npm-cache")
        make_file(os.path.join(npm, "pkg.tgz"), size=700)
        return [
            Category("temp_user", "Sistema", "Temporales", "x", (Target(temp),)),
            Category("npm", "Desarrollo", "npm", "x", (Target(npm),), default_on=False),
        ]

    def test_detect_and_execute_on_any_os(self):
        with mock.patch.object(cleaner, "available_categories", return_value=self._categories()), \
                mock.patch.object(freeup, "IS_WINDOWS", False):
            tasks = {t.id: t for t in freeup.detect(admin=False, dev_root=os.path.join(self.tmp, "nada"))}
        self.assertEqual(set(tasks), {"caches", "dev_caches"})
        self.assertEqual((tasks["caches"].estimate, tasks["caches"].default_on), (300, True))
        self.assertEqual((tasks["dev_caches"].estimate, tasks["dev_caches"].default_on), (700, False))
        result = freeup.execute(tasks["caches"])
        self.assertEqual((result.freed, result.error), (300, ""))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "Temp", "a.tmp")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "npm-cache", "pkg.tgz")))

    def _windows_detect(self, admin, battery=False):
        gb = 1024 ** 3
        patches = [
            mock.patch.object(cleaner, "available_categories", return_value=self._categories()),
            mock.patch.object(freeup, "IS_WINDOWS", True),
            mock.patch.object(winsys, "system_drive", return_value=self.tmp),
            mock.patch.object(winsys, "hibernation_file_size", return_value=6 * gb),
            mock.patch.object(winsys, "has_battery", return_value=battery),
            mock.patch.object(winsys, "windows_leftovers", return_value=(12 * gb, ["Windows.old: 12 GB"], True)),
            mock.patch.object(winsys, "shadow_copies", return_value=(3, 3 * gb)),
            mock.patch.object(winsys, "reserved_storage_enabled", return_value=True),
        ]
        for patcher in patches:
            patcher.start()
        try:
            return {t.id: t for t in freeup.detect(admin=admin, dev_root=os.path.join(self.tmp, "nada"))}
        finally:
            for patcher in patches:
                patcher.stop()

    def test_windows_tasks_as_admin(self):
        tasks = self._windows_detect(admin=True)
        self.assertTrue(tasks["hibernation"].default_on)  # PC de sobremesa
        self.assertEqual(tasks["hibernation"].estimate, 6 * 1024 ** 3)
        self.assertIn("anterior de Windows", tasks["windows_cleanup"].warning)
        self.assertEqual(tasks["restore_points"].estimate, 2 * 1024 ** 3)  # se conserva el más reciente
        self.assertFalse(tasks["reserved_storage"].default_on)
        self.assertFalse(tasks["compact_os"].default_on)
        for task_id in ("hibernation", "windows_cleanup", "components", "restore_points", "compact_os"):
            self.assertTrue(tasks[task_id].needs_admin, task_id)

    def test_windows_tasks_on_laptop_without_admin(self):
        tasks = self._windows_detect(admin=False, battery=True)
        self.assertFalse(tasks["hibernation"].default_on)  # portátil: la hibernación se respeta
        self.assertIn("batería", tasks["hibernation"].warning)
        self.assertIsNone(tasks["restore_points"].estimate)
        self.assertNotIn("reserved_storage", tasks)

    def test_windows_execute_measures_free_space_and_reboot_code(self):
        task = freeup.FreeTask("components", "Sistema de Windows", "DISM", "x", needs_admin=True)
        with mock.patch.object(freeup, "IS_WINDOWS", True), \
                mock.patch.object(freeup, "free_bytes", side_effect=[1000, 4000]), \
                mock.patch.object(winsys, "component_cleanup", return_value=3010):
            result = freeup.execute(task)
        self.assertEqual((result.freed, result.error, result.reboot), (3000, "", True))

    def test_windows_execute_reports_errors(self):
        task = freeup.FreeTask("hibernation", "Sistema de Windows", "Hibernación", "x", estimate=500)
        with mock.patch.object(freeup, "IS_WINDOWS", True), \
                mock.patch.object(freeup, "free_bytes", side_effect=[1000, 1000]), \
                mock.patch.object(winsys, "disable_hibernation", return_value=(1, "Acceso denegado.")):
            result = freeup.execute(task)
        self.assertEqual(result.freed, 0)
        self.assertIn("Acceso denegado", result.error)


class OtherDriveTests(TempDirTest):
    def test_other_drive_offers_recycle_bin_and_node_modules_only(self):
        drive = os.path.join(self.tmp, "D")
        make_project(os.path.join(drive, "Proyectos"), "viejo")
        make_project(os.path.join(drive, "Program Files"), "instalado")  # programas: no
        with mock.patch.object(freeup, "IS_WINDOWS", True), \
                mock.patch.object(winsys, "system_drive", return_value="C:\\"), \
                mock.patch("limpiapc.trash.recycle_bin_info", return_value=(4000, 3)) as info:
            tasks = {t.id: t for t in freeup.detect(admin=True, drive=drive)}
        info.assert_called_once_with(drive)
        self.assertEqual(set(tasks), {"drive_recycle_bin", "node_modules"})
        self.assertEqual(tasks["drive_recycle_bin"].estimate, 4000)
        self.assertEqual([p.project for p in tasks["node_modules"].payload], ["viejo"])
        with mock.patch("limpiapc.trash.empty_recycle_bin", return_value=(False, "error")) as empty:
            result = freeup.execute(tasks["drive_recycle_bin"])
        empty.assert_called_once_with(drive)
        self.assertEqual((result.freed, result.error), (0, "error"))


class FakeRegistry:
    HKEY_LOCAL_MACHINE, KEY_READ, KEY_SET_VALUE, KEY_WOW64_64KEY, REG_DWORD = 2, 1, 2, 4, 4

    class Key:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def __init__(self, handlers):
        self.values = {name: {} for name in handlers}

    def OpenKey(self, hive, path, reserved=0, access=0):
        return self.Key(path)

    def EnumKey(self, key, index):
        names = list(self.values)
        if index >= len(names):
            raise OSError("fin")
        return names[index]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[key.path.rsplit("\\", 1)[1]][name] = value

    def DeleteValue(self, key, name):
        handler = self.values[key.path.rsplit("\\", 1)[1]]
        if name not in handler:
            raise FileNotFoundError(name)
        del handler[name]


class DiskCleanupTests(unittest.TestCase):
    HANDLERS = ["Active Setup Temp Folders", "DownloadsFolder", "Previous Installations", "Recycle Bin",
                "Update Cleanup", "User file versions", "Windows ESD installation files", "Language Pack",
                "Delivery Optimization Files"]

    def test_only_safe_handlers_are_marked_and_flags_are_removed(self):
        reg = FakeRegistry(self.HANDLERS)
        flag = f"StateFlags{winsys.SAGE_SET:04d}"
        reg.values["DownloadsFolder"][flag] = 2  # ¡alguien lo dejó marcado!
        seen = {}

        def runner(command):
            seen["command"] = command
            seen["marked"] = {h for h, v in reg.values.items() if v.get(flag) == 2}
            return 0

        self.assertEqual(winsys.run_disk_cleanup(winreg_module=reg, runner=runner), 0)
        self.assertEqual(seen["marked"], {"Active Setup Temp Folders", "Previous Installations",
                                          "Update Cleanup", "Delivery Optimization Files"})
        self.assertEqual(seen["command"][-1], f"/sagerun:{winsys.SAGE_SET}")
        self.assertTrue(all(flag not in values for values in reg.values.values()))

    def test_flags_are_removed_even_if_cleanup_fails(self):
        reg = FakeRegistry(self.HANDLERS)

        def runner(command):
            raise OSError("cleanmgr no encontrado")

        with self.assertRaises(OSError):
            winsys.run_disk_cleanup(winreg_module=reg, runner=runner)
        self.assertTrue(all(not values for values in reg.values.values()))

    def test_dangerous_handlers_are_never_in_the_allowlist(self):
        for name in ("downloadsfolder", "recycle bin", "user file versions", "windows esd installation files",
                     "language pack", "device driver packages"):
            self.assertNotIn(name, winsys.SAFE_CLEANUP_HANDLERS)


class PowerShellParsingTests(unittest.TestCase):
    def test_shadow_copies(self):
        with mock.patch.object(winsys, "powershell", return_value=(0, "3 3221225472")):
            self.assertEqual(winsys.shadow_copies("C:\\"), (3, 3221225472))
        with mock.patch.object(winsys, "powershell", return_value=(1, "Acceso denegado")):
            self.assertIsNone(winsys.shadow_copies("C:\\"))

    def test_reserved_storage(self):
        with mock.patch.object(winsys, "powershell", return_value=(0, "Enabled")):
            self.assertTrue(winsys.reserved_storage_enabled())
        with mock.patch.object(winsys, "powershell", return_value=(0, "Disabled")):
            self.assertFalse(winsys.reserved_storage_enabled())
        with mock.patch.object(winsys, "powershell", return_value=(1, "")):
            self.assertIsNone(winsys.reserved_storage_enabled())


if __name__ == "__main__":
    unittest.main()
