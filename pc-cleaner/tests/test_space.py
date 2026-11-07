"""Pruebas de análisis de espacio, organizador, duplicados y movimiento de archivos."""

import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from limpiapc import analyzer, duplicates, fileops, organizer  # noqa: E402
from test_core import TempDirTest, make_file  # noqa: E402

OLD = time.time() - 10 * 86400


class AnalyzerTests(TempDirTest):
    def test_folder_sizes_types_and_largest(self):
        root = os.path.join(self.tmp, "disk")
        make_file(os.path.join(root, "Videos", "boda.mp4"), size=5000)
        make_file(os.path.join(root, "Videos", "viaje", "playa.mkv"), size=3000)
        make_file(os.path.join(root, "Fotos", "a.jpg"), size=700)
        make_file(os.path.join(root, "Steam", "steamapps", "common", "Juego", "data.pak"), size=4000)
        make_file(os.path.join(root, "proyecto", "node_modules", "react", "index.js"), size=900)
        make_file(os.path.join(root, "nota.txt"), size=10)
        os.symlink(os.path.join(root, "Videos"), os.path.join(root, "enlace"))  # no se cuenta dos veces

        result = analyzer.analyze(root)
        self.assertEqual(result.total_size, 5000 + 3000 + 700 + 4000 + 900 + 10)
        self.assertEqual(result.root.size, result.total_size)
        videos = next(n for n in result.root.children if n.name == "Videos")
        self.assertEqual((videos.size, videos.files, videos.own_size), (8000, 2, 5000))
        self.assertEqual(result.by_type["video"], [8000, 2])
        self.assertEqual(result.by_type["games"], [4000, 1])
        self.assertEqual(result.by_type["dev"], [900, 1])
        self.assertEqual(result.by_type["docs"], [10, 1])
        self.assertEqual([f.name for f in result.largest[:2]], ["boda.mp4", "data.pak"])
        self.assertEqual(result.root.sorted_children()[0].name, "Videos")

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "permisos POSIX")
    def test_denied_folder_is_reported(self):
        root = os.path.join(self.tmp, "disk")
        make_file(os.path.join(root, "privado", "x.bin"), size=10)
        os.chmod(os.path.join(root, "privado"), 0)
        try:
            result = analyzer.analyze(root)
        finally:
            os.chmod(os.path.join(root, "privado"), 0o700)
        self.assertEqual(result.denied, 1)


class FileOpsTests(TempDirTest):
    def test_move_never_overwrites(self):
        dest = os.path.join(self.tmp, "dest")
        make_file(os.path.join(dest, "foto.jpg"), size=1)
        src = make_file(os.path.join(self.tmp, "foto.jpg"), size=2)
        final = fileops.move_file(src, dest)
        self.assertEqual(os.path.basename(final), "foto (2).jpg")
        self.assertEqual(os.path.getsize(os.path.join(dest, "foto.jpg")), 1)
        self.assertFalse(os.path.exists(src))

    def test_cross_device_fallback_copies_then_deletes(self):
        src = make_file(os.path.join(self.tmp, "video.mp4"), size=1234)
        dest = os.path.join(self.tmp, "otro_disco")
        with mock.patch.object(fileops.os, "rename", side_effect=OSError(18, "cross-device")):
            final = fileops.move_file(src, dest)
        self.assertEqual(os.path.getsize(final), 1234)
        self.assertFalse(os.path.exists(src))


class OrganizerTests(TempDirTest):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"LIMPIAPC_DATA_DIR": os.path.join(self.tmp, "data")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.downloads = os.path.join(self.home, "Downloads")
        for name in ("foto.JPG", "factura.pdf", "setup.exe", "cancion.mp3", "raro.xyz", "acceso.lnk",
                     "desktop.ini", "a_medias.crdownload"):
            make_file(os.path.join(self.downloads, name), old=True)
        make_file(os.path.join(self.downloads, "Imágenes", "foto.JPG"), old=True)  # choque de nombres
        make_file(os.path.join(self.downloads, "carpeta", "dentro.pdf"), old=True)  # subcarpeta: no se toca

    def _ctime_ok(self):
        # ctime es "ahora" en Linux: se adelanta el reloj para que no parezcan descargas recientes.
        return mock.patch.object(organizer.time, "time", return_value=time.time() + 3600)

    def test_plan_and_apply_by_type_then_undo(self):
        with self._ctime_ok():
            plan = organizer.plan_organize(self.downloads, "type")
        planned = {m.name: os.path.basename(m.dest_dir) for m in plan}
        self.assertEqual(planned, {"foto.JPG": "Imágenes", "factura.pdf": "Documentos",
                                   "setup.exe": "Instaladores", "cancion.mp3": "Música", "raro.xyz": "Otros"})
        record = organizer.apply_plan(self.downloads, plan, "type")
        self.assertEqual(record["errors"], [])
        self.assertTrue(os.path.exists(os.path.join(self.downloads, "Imágenes", "foto (2).JPG")))
        self.assertTrue(os.path.exists(os.path.join(self.downloads, "Imágenes", "foto.JPG")))
        self.assertTrue(os.path.exists(os.path.join(self.downloads, "acceso.lnk")))
        self.assertTrue(os.path.exists(os.path.join(self.downloads, "carpeta", "dentro.pdf")))

        last = organizer.last_record()
        self.assertIsNotNone(last)
        restored, errors = organizer.undo(last)
        self.assertEqual((restored, errors), (5, []))
        for name in ("foto.JPG", "factura.pdf", "setup.exe", "cancion.mp3", "raro.xyz"):
            self.assertTrue(os.path.exists(os.path.join(self.downloads, name)), name)
        # Las carpetas creadas y vacías se quitan; la que ya existía se queda.
        self.assertFalse(os.path.exists(os.path.join(self.downloads, "Documentos")))
        self.assertTrue(os.path.isdir(os.path.join(self.downloads, "Imágenes")))
        self.assertIsNone(organizer.last_record())

    def test_by_date(self):
        stamp = time.mktime((2023, 3, 15, 12, 0, 0, 0, 0, -1))
        path = os.path.join(self.downloads, "factura.pdf")
        os.utime(path, (stamp, stamp))
        with self._ctime_ok():
            plan = organizer.plan_organize(self.downloads, "date")
        dest = next(m.dest_dir for m in plan if m.name == "factura.pdf")
        self.assertEqual(os.path.relpath(dest, self.downloads), os.path.join("2023", "03 - Marzo"))

    def test_symlinks_are_not_moved(self):
        target = make_file(os.path.join(self.tmp, "fuera", "real.pdf"), old=True)
        os.symlink(target, os.path.join(self.downloads, "enlace.pdf"))
        with self._ctime_ok():
            names = {m.name for m in organizer.plan_organize(self.downloads, "type")}
        self.assertNotIn("enlace.pdf", names)
        self.assertIn("factura.pdf", names)

    def test_recent_files_are_left_alone(self):
        plan = organizer.plan_organize(self.downloads, "type")
        self.assertEqual(plan, [])  # todo se creó hace segundos (ctime)

    def test_refuses_dangerous_folders(self):
        self.assertTrue(organizer.check_folder(self.home))
        self.assertTrue(organizer.check_folder(os.path.abspath(os.sep)))
        appdata = os.path.join(self.home, "AppData", "Local")
        os.makedirs(appdata)
        self.assertTrue(organizer.check_folder(appdata))
        self.assertEqual(organizer.check_folder(self.downloads), "")


class DuplicatesTests(TempDirTest):
    def test_finds_identical_content_only(self):
        folder = os.path.join(self.tmp, "fotos")
        content = os.urandom(200_000)
        for path in ("a/IMG_1.jpg", "b/copia de IMG_1.jpg", "c/IMG_1 (1).jpg"):
            full = os.path.join(folder, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(content)
        # Mismo tamaño y mismo inicio, pero distinto final: NO es duplicado.
        with open(os.path.join(folder, "parecido.jpg"), "wb") as fh:
            fh.write(content[:-1] + bytes([content[-1] ^ 1]))
        make_file(os.path.join(folder, "pequeño1.txt"), size=10)
        make_file(os.path.join(folder, "pequeño2.txt"), size=10)

        groups, scanned = duplicates.find_duplicates(folder, min_size=1000)
        self.assertEqual(scanned, 6)
        self.assertEqual(len(groups), 1)
        self.assertEqual(sorted(f.name for f in groups[0].files),
                         ["IMG_1 (1).jpg", "IMG_1.jpg", "copia de IMG_1.jpg"])
        self.assertEqual(groups[0].wasted, 400_000)


if __name__ == "__main__":
    unittest.main()
