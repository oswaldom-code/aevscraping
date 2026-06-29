#!/usr/bin/env python3
"""
Runner único de TODOS los tests unitarios del proyecto (scrapers + consolidador)
en un solo proceso y un solo reporte.

Resuelve la colisión de nombres: cada `scrapers/*/scraper.py` y su `test_scraper.py`
son homónimos, así que `unittest discover` global no sirve. Aquí cada test de scraper
se carga aislado (limpiando `sys.modules` y anteponiendo su dir al path); el
consolidador se descubre como paquete normal.

Correr con el venv (el consolidador necesita openpyxl):
    .venv/bin/python scripts/run_tests.py     (o: make test)
"""
import sys
import unittest
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # raíz del repo (scripts/ está un nivel abajo)
SCRAPER_DIRS = [
    ROOT / "scrapers" / "sosvenezuela2026",
    ROOT / "scrapers" / "venezuelareporta",
]


def load_scraper_suite(scraper_dir, idx):
    """Carga test_scraper.py de un scraper de forma aislada (evita la colisión
    de los módulos homónimos `scraper`/`test_scraper`)."""
    sys.path.insert(0, str(scraper_dir))
    for name in ("scraper", "test_scraper"):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(
        f"test_scraper_{idx}", scraper_dir / "test_scraper.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    sys.path.remove(str(scraper_dir))
    return suite


def build_suite():
    suite = unittest.TestSuite()
    for idx, d in enumerate(SCRAPER_DIRS):
        suite.addTest(load_scraper_suite(d, idx))
    # Consolidador: paquete normal. top_level_dir = raíz para `from consolidator import ...`.
    suite.addTests(unittest.defaultTestLoader.discover(
        start_dir=str(ROOT / "consolidator" / "tests"), top_level_dir=str(ROOT)))
    return suite


def main():
    result = unittest.TextTestRunner(verbosity=2).run(build_suite())
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
