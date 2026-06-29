"""
Integración consolidador <- scraper venezuelareporta.

Genera un registro con el parser REAL del scraper (`parse_report`); si su esquema
deriva, el test lo detecta. Lo ingiere por el pipeline del consolidador con un maestro
sintético y verifica clasificación, persistencia de `fuente` e idempotencia.
Hermético (dirs temporales; sin red). Requiere openpyxl (correr con venv).
"""

import importlib.util
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from consolidator import run_consolidacion as run_mod

BASE = Path(__file__).resolve().parents[1]   # consolidator/
REPO = BASE.parent
INIT_SQL = BASE / "migrations" / "0001_init.sql"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SCRAPER = _load("vr_scraper", "scrapers/venezuelareporta/scraper.py")
FUENTE = "venezuelareporta"


def sample_record():
    page_html = (
        "<title>Se busca: Abel Velasquez — La Guaira</title>"
        '<script type="application/ld+json">[{"@type":"WebPage","mainEntity":'
        '{"@type":"Person","name":"Abel Velasquez",'
        '"description":"Alguien busca a esta persona. Edad: 35. Lugar: La Guaira, Venezuela."}}]</script>'
        '<script>"datePublished":"2026-06-29T12:00:00+00:00"</script>'
    )
    return SCRAPER.parse_report(
        page_html, "https://venezuelareporta.org/reporte/038c38ea-484d-42bc-a101-29e2570067c9")


class TestIngestVenezuelareporta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.migr = root / "migrations"
        self.migr.mkdir()
        shutil.copy(INIT_SQL, self.migr / "0001_init.sql")  # maestro vacío (solo esquema)
        self.db = root / "master.db"
        self.out = root / "out"
        self.inp = root / "entrada.json"
        self.inp.write_text(json.dumps([sample_record()]), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, run_id):
        return run_mod.run(db=self.db, migrations=self.migr, out_dir=self.out / run_id,
                           sources=[self.inp], run_id=run_id, scrape=False, cotejo=False)

    def test_record_ingested_as_new(self):
        r = self._run("t1")
        self.assertEqual(r["procesados"], 1)
        self.assertEqual(r["nuevos"], 1)
        self.assertEqual(r["rechazados"], 0)

    def test_fuente_persisted_in_master(self):
        self._run("t1")
        con = sqlite3.connect(self.db)
        fuentes = {row[0] for row in con.execute("SELECT DISTINCT fuente FROM registros")}
        con.close()
        self.assertIn(FUENTE, fuentes)

    def test_second_run_is_idempotent(self):
        self._run("t1")
        r2 = self._run("t2")
        self.assertEqual(r2["nuevos"], 0)
        self.assertEqual(r2["actualizados"], 0)
        self.assertEqual(r2["delta_total"], 0)
        self.assertEqual(r2["sin_cambio"], 1)


if __name__ == "__main__":
    unittest.main()
