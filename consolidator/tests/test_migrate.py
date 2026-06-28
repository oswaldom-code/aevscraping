"""
Verifica el runner de migraciones: aplica en orden, registra versiones, y
reaplicar no hace nada (idempotente). Hermético: usa un directorio temporal con
el esquema real (0001_init) + una migración sintética chica, sin tocar el seed.

Ejecutar:  python -m unittest discover -s consolidator/tests -t .
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from consolidator.lib import migrate as mig

BASE = Path(__file__).resolve().parents[1]
INIT_SQL = (BASE / "migrations" / "0001_init.sql").read_text(encoding="utf-8")

# Migración de datos sintética (2 filas) que respeta el esquema de 'registros'.
SEED_SQL = """
INSERT INTO registros (id, fuente, nombre, content_hash, first_seen, last_seen, presente)
VALUES
  ('1', 'test', 'Ana',  'h1', 't', 't', 1),
  ('2', 'test', 'Beto', 'h2', 't', 't', 1)
ON CONFLICT(fuente, id) DO UPDATE SET nombre=excluded.nombre;
"""


class TestMigrate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.migrations = root / "migrations"
        self.migrations.mkdir()
        (self.migrations / "0001_init.sql").write_text(INIT_SQL, encoding="utf-8")
        (self.migrations / "0002_seed_0001.sql").write_text(SEED_SQL, encoding="utf-8")
        self.db = root / "master.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_applies_in_order_and_records(self):
        applied = mig.migrate(self.db, self.migrations)
        self.assertEqual(applied, ["0001_init", "0002_seed_0001"])

        con = sqlite3.connect(self.db)
        versions = [r[0] for r in con.execute(
            "SELECT version FROM schema_migrations ORDER BY version")]
        count = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
        con.close()
        self.assertEqual(versions, ["0001_init", "0002_seed_0001"])
        self.assertEqual(count, 2)

    def test_second_run_is_noop(self):
        mig.migrate(self.db, self.migrations)
        applied_again = mig.migrate(self.db, self.migrations)
        self.assertEqual(applied_again, [])

        con = sqlite3.connect(self.db)
        count = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
        con.close()
        self.assertEqual(count, 2)

    def test_new_migration_applied_incrementally(self):
        mig.migrate(self.db, self.migrations)
        # Aparece una migración nueva después de la primera corrida.
        (self.migrations / "0003_seed_0002.sql").write_text(
            "INSERT INTO registros (id, fuente, nombre, content_hash, first_seen, "
            "last_seen, presente) VALUES ('3','test','Caro','h3','t','t',1) "
            "ON CONFLICT(fuente,id) DO UPDATE SET nombre=excluded.nombre;",
            encoding="utf-8",
        )
        applied = mig.migrate(self.db, self.migrations)
        self.assertEqual(applied, ["0003_seed_0002"])

        con = sqlite3.connect(self.db)
        count = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
        con.close()
        self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
