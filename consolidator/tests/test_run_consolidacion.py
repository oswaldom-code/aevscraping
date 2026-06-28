"""
End-to-end del orquestador: maestro sintético + entrada simulada -> verifica el
embudo completo, los artefactos de salida, la migración del delta y la
idempotencia de una segunda corrida. Requiere openpyxl (correr con el venv).
"""

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from consolidator import run_consolidacion as run_mod
from consolidator.scripts.gen_seed_migrations import emit_migrations

BASE = Path(__file__).resolve().parents[1]
INIT_SQL = BASE / "migrations" / "0001_init.sql"


def rec(rid, nombre, estado="Desaparecido"):
    return {"id": rid, "nombre": nombre, "estado": estado, "fuente": "f"}


class TestRunConsolidacion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        # maestro sintético: esquema + seed de 3 registros (hash real).
        self.migr = root / "migrations"
        self.migr.mkdir()
        shutil.copy(INIT_SQL, self.migr / "0001_init.sql")
        emit_migrations([rec(1, "Ana"), rec(2, "Beto"), rec(3, "Caro")],
                        self.migr, 2, "seed")
        self.db = root / "master.db"
        self.out = root / "out"
        # entrada: 1=igual, 2=cambia estado, 10/11=nuevos, 11 dup, 99 sin nombre.
        entrada = [rec(1, "Ana"), rec(2, "Beto", "Localizado"),
                   rec(10, "Nuevo Uno"), rec(11, "Nuevo Dos"), rec(11, "Nuevo Dos"),
                   {"id": 99, "fuente": "f"}]
        self.inp = root / "entrada.json"
        self.inp.write_text(json.dumps(entrada), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, run_id):
        return run_mod.run(db=self.db, migrations=self.migr, out_dir=self.out / run_id,
                           sources=[self.inp], run_id=run_id, scrape=False)

    def test_funnel_and_artifacts(self):
        r = self._run("t1")
        self.assertEqual(r["procesados"], 6)
        self.assertEqual(r["nuevos"], 2)
        self.assertEqual(r["actualizados"], 1)
        self.assertEqual(r["sin_cambio"], 1)
        self.assertEqual(r["duplicados_lote"], 1)
        self.assertEqual(r["rechazados"], 1)
        self.assertEqual(r["delta_total"], 3)
        # artefactos en out/t1/
        self.assertEqual(len(r["archivos_xls"]), 1)
        self.assertTrue((self.out / "t1" / "reporte.json").exists())
        self.assertTrue((self.out / "t1" / "rechazados.csv").exists())
        self.assertTrue((self.out / "t1" / r["archivos_xls"][0]).exists())
        # migración del delta creada
        self.assertEqual(len(list(self.migr.glob("*_run_t1_*.sql"))), 1)

    def test_second_run_is_idempotent(self):
        self._run("t1")
        r2 = self._run("t2")
        self.assertEqual(r2["nuevos"], 0)
        self.assertEqual(r2["actualizados"], 0)
        self.assertEqual(r2["delta_total"], 0)
        self.assertEqual(r2["sin_cambio"], 4)  # 1,2,10,11 ya en el maestro
        self.assertEqual(len(list(self.migr.glob("*_run_t2_*.sql"))), 0)

    def test_update_applied_to_master(self):
        self._run("t1")
        con = sqlite3.connect(self.db)
        estado = con.execute(
            "SELECT estado FROM registros WHERE fuente='f' AND id='2'").fetchone()[0]
        filas = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
        con.close()
        self.assertEqual(estado, "Localizado")
        self.assertEqual(filas, 5)  # 3 seed + 2 nuevos

    def test_rejected_csv_has_reason(self):
        self._run("t1")
        content = (self.out / "t1" / "rechazados.csv").read_text(encoding="utf-8-sig")
        self.assertIn("motivo_rechazo", content)
        self.assertIn("sin nombre", content)

    @mock.patch("consolidator.lib.api.upload_delta")
    def test_upload_integrated_in_report(self, mock_upload):
        mock_upload.return_value = [
            {"file": "delta_parte_001.xlsx", "status": 200, "ok": True, "resp": "ok"}]
        r = run_mod.run(db=self.db, migrations=self.migr, out_dir=self.out / "tu",
                        sources=[self.inp], run_id="tu", scrape=False, upload=True)
        self.assertTrue(mock_upload.called)
        self.assertIn("subida", r)
        self.assertTrue(r["subida"][0]["ok"])

    def test_cotejo_is_part_of_run(self):
        r = self._run("t1")
        self.assertIn("cotejo", r)
        self.assertTrue((self.out / "t1" / "alertas.json").exists())

    def test_cotejo_detects_cross_source_in_run(self):
        # dos fuentes distintas, misma persona, estados en conflicto
        entrada = [
            {"id": "100", "nombre": "Maria Lopez", "estado": "Desaparecido", "fuente": "redayuda"},
            {"id": "200", "nombre": "Maria Lopez", "estado": "Localizado", "fuente": "terremoto"},
        ]
        inp = Path(self.tmp.name) / "cross.json"
        inp.write_text(json.dumps(entrada), encoding="utf-8")
        r = run_mod.run(db=self.db, migrations=self.migr, out_dir=self.out / "tc",
                        sources=[inp], run_id="tc", scrape=False)
        self.assertGreaterEqual(r["cotejo"]["alertas_criticas"], 1)
        alertas = json.loads((self.out / "tc" / "alertas.json").read_text(encoding="utf-8"))
        self.assertTrue(all(g["alerta_critica"] for g in alertas))
        self.assertEqual(alertas[0]["fuente"], "redayuda/terremoto")

    def test_no_cotejo_skips_it(self):
        r = run_mod.run(db=self.db, migrations=self.migr, out_dir=self.out / "tn",
                        sources=[self.inp], run_id="tn", scrape=False, cotejo=False)
        self.assertNotIn("cotejo", r)
        self.assertFalse((self.out / "tn" / "alertas.json").exists())


if __name__ == "__main__":
    unittest.main()
