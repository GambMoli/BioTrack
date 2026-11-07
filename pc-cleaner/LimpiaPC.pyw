"""Doble clic en este archivo para abrir LimpiaPC (Windows, con Python instalado)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from limpiapc.gui import main  # noqa: E402

main()
