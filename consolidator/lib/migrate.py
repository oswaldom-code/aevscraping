"""
migrate.py

Runner de migraciones SQLite. Aplica en orden los .sql de un directorio que aún
no estén registrados en schema_migrations. Las migraciones son idempotentes
(IF NOT EXISTS / ON CONFLICT), así que reaplicar es seguro; el registro evita
reaplicar trabajo innecesario y deja trazabilidad de qué se aplicó y cuándo.

La 'version' de cada migración es el nombre de archivo sin extensión
(ej. '0001_init', '0002_seed_0001'), y el orden de aplicación es alfabético
(por eso los prefijos van con ceros: 0001, 0002, …).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _ensure_tracking(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    con.commit()


def applied_versions(con):
    _ensure_tracking(con)
    return {r[0] for r in con.execute("SELECT version FROM schema_migrations")}


def pending(migrations_dir, applied):
    files = sorted(Path(migrations_dir).glob("*.sql"))
    return [f for f in files if f.stem not in applied]


def apply_migration(con, path):
    con.executescript(path.read_text(encoding="utf-8"))
    con.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (path.stem, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()


def migrate(db_path, migrations_dir):
    """Aplica las migraciones pendientes. Devuelve la lista de versiones aplicadas."""
    con = sqlite3.connect(str(db_path))
    try:
        todo = pending(migrations_dir, applied_versions(con))
        for path in todo:
            apply_migration(con, path)
        return [p.stem for p in todo]
    finally:
        con.close()
