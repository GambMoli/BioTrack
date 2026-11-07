"""Pruebas de «Optimizar Windows»: aplicar y restaurar ajustes con un registro simulado."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from limpiapc import optimizer  # noqa: E402
from test_core import TempDirTest  # noqa: E402


class FakeWinreg:
    HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE = 1, 2
    KEY_READ, KEY_SET_VALUE, KEY_WOW64_64KEY, REG_DWORD = 1, 2, 4, 4

    class Key:
        def __init__(self, hive, path):
            self.id = (hive, path.lower())

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def __init__(self):
        self.data = {}

    def OpenKey(self, hive, path, reserved=0, access=0):
        if (hive, path.lower()) not in self.data:
            raise FileNotFoundError(path)
        return self.Key(hive, path)

    def CreateKeyEx(self, hive, path, reserved=0, access=0):
        self.data.setdefault((hive, path.lower()), {})
        return self.Key(hive, path)

    def QueryValueEx(self, key, name):
        if name not in self.data[key.id]:
            raise FileNotFoundError(name)
        return self.data[key.id][name], 4

    def SetValueEx(self, key, name, reserved, kind, value):
        self.data[key.id][name] = value

    def DeleteValue(self, key, name):
        if name not in self.data[key.id]:
            raise FileNotFoundError(name)
        del self.data[key.id][name]


class OptimizerTests(TempDirTest):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"LIMPIAPC_DATA_DIR": os.path.join(self.tmp, "datos")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_apply_and_restore_exactly(self):
        fake = FakeWinreg()
        reg = optimizer.Registry(fake)
        ads = next(t for t in optimizer.TWEAKS if t.id == "ads")
        first = ads.values[0]
        reg.set(first, 1)  # valor original existente; los demás no existen
        self.assertFalse(optimizer.is_applied(ads, reg))
        optimizer.apply_tweak(ads, reg)
        self.assertTrue(optimizer.is_applied(ads, reg))
        optimizer.apply_tweak(ads, reg)  # aplicar dos veces no pisa el original guardado
        self.assertTrue(optimizer.has_backup())
        restored = optimizer.restore_all(reg)
        self.assertEqual(restored, len(ads.values))
        self.assertEqual(reg.get(first), 1)
        self.assertTrue(all(reg.get(v) is None for v in ads.values[1:]))  # se borran: como antes
        self.assertFalse(optimizer.has_backup())

    def test_tweaks_are_well_formed(self):
        ids = [t.id for t in optimizer.TWEAKS]
        self.assertEqual(len(ids), len(set(ids)))
        for tweak in optimizer.TWEAKS:
            for v in tweak.values:
                if v.hive == optimizer.HKLM:
                    self.assertTrue(tweak.needs_admin, tweak.id)

    def test_remove_app_rejects_weird_names(self):
        with mock.patch("limpiapc.winsys.powershell") as ps:
            code, _ = optimizer.remove_app(["x'; Remove-Item C:\\ -Recurse; '"])
        self.assertEqual(code, 1)
        ps.assert_not_called()


if __name__ == "__main__":
    unittest.main()
