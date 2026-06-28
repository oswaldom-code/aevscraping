"""
build_db.py

Levanta y carga el maestro SQLite aplicando las migraciones pendientes. Es el
paso AUTOMÁTICO previo a cada corrida de scrapers (no genera seed).

La generación del seed es MANUAL y vive aparte (scripts/gen_seed_migrations.py);
se corre solo cuando llegan nuevos .rar a datos_consolidados/.

Uso:
    python3 consolidator/build_db.py            # aplica migraciones pendientes
    python3 consolidator/build_db.py --fresh     # parte de cero (borra master.db)
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from consolidator.lib import migrate as mig

BASE = Path(__file__).resolve().parent
DEFAULT_DB = BASE / "master.db"
DEFAULT_MIGRATIONS = BASE / "migrations"


def has_seed(migrations_dir):
    return any(Path(migrations_dir).glob("*_seed_*.sql"))


def main():
    ap = argparse.ArgumentParser(description="Levanta y carga el maestro SQLite desde migraciones.")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--migrations", default=str(DEFAULT_MIGRATIONS))
    ap.add_argument("--fresh", action="store_true", help="Borra master.db antes de construir.")
    args = ap.parse_args()

    db = Path(args.db)
    if args.fresh and db.exists():
        db.unlink()
        print(f"master.db borrado (--fresh): {db}")

    if not has_seed(args.migrations):
        print("Aviso: no hay migraciones de seed. Corre primero (manual):", file=sys.stderr)
        print("       python3 consolidator/scripts/gen_seed_migrations.py", file=sys.stderr)

    applied = mig.migrate(args.db, args.migrations)
    print(f"Migraciones aplicadas en esta corrida: {len(applied)}")

    con = sqlite3.connect(args.db)
    total = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    by_src = con.execute(
        "SELECT fuente, COUNT(*) FROM registros GROUP BY fuente ORDER BY 2 DESC"
    ).fetchall()
    con.close()

    print(f"Maestro: {total} registros")
    for fuente, n in by_src:
        print(f"   {fuente:<28}{n}")


if __name__ == "__main__":
    main()
