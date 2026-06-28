"""
gen_seed_migrations.py

Procesa el consolidado y lo parte en varias migraciones SQL pequeñas (seed), una
por lote de filas. Lee los registros desde TODOS los .rar de datos_consolidados/
(cada .rar contiene un .json), así que el seed crece agregando .rar al directorio.
Cada migración es idempotente (ON CONFLICT), así que reaplicarlas reconstruye el
mismo estado del maestro.

Uso:
    python3 consolidator/scripts/gen_seed_migrations.py
    python3 consolidator/scripts/gen_seed_migrations.py --chunk-size 5000

Los .rar/.json crudos NO se versionan. Lo versionado son estas migraciones chicas.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Permite ejecutar el script directamente (añade la raíz del repo al path).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from consolidator.lib.registros import CANONICAL_COLUMNS, content_hash, normalize_record

BASE = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = BASE.parent / "datos_consolidados"
DEFAULT_OUT = BASE / "migrations"

# Columnas que escribe cada migración (16 canónicas + metadatos del maestro).
INSERT_COLUMNS = CANONICAL_COLUMNS + ["content_hash", "first_seen", "last_seen", "presente"]

# En ON CONFLICT no se tocan la llave ni first_seen (es el "primer avistamiento").
UPDATE_COLUMNS = [c for c in INSERT_COLUMNS if c not in ("id", "fuente", "first_seen")]


def _iter_json_array(text):
    """Itera los objetos de un array JSON sin materializarlos todos a la vez."""
    dec = json.JSONDecoder()
    n = len(text)
    i = text.find("[") + 1
    while True:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            return
        obj, i = dec.raw_decode(text, i)
        yield obj


def _rar_members(rar_path):
    out = subprocess.run(["unrar", "lb", str(rar_path)],
                         capture_output=True, text=True, check=True)
    return [m.strip() for m in out.stdout.splitlines() if m.strip()]


def stream_records(data_dir):
    """Itera los registros de los .json contenidos en todos los .rar del directorio."""
    rars = sorted(Path(data_dir).glob("*.rar"))
    if not rars:
        print(f"Advertencia: no hay .rar en {data_dir}", file=sys.stderr)
    for rar in rars:
        for member in _rar_members(rar):
            if not member.lower().endswith(".json"):
                continue
            raw = subprocess.run(["unrar", "p", "-inul", str(rar), member],
                                 capture_output=True, check=True).stdout
            print(f"  leído: {rar.name} :: {member} ({len(raw)//1_000_000} MB)")
            yield from _iter_json_array(raw.decode("utf-8"))
            del raw


def sql_value(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def build_row(rec):
    """Construye la tupla de valores SQL para un registro, o None si se rechaza."""
    norm = normalize_record(rec)   # rechaza sin id/nombre; fuente faltante -> "desconocida"
    if norm is None:
        return None

    values = dict(norm)
    values["content_hash"] = content_hash(norm)
    values["first_seen"] = norm.get("fecha_registro") or norm.get("fecha_actualizacion") or ""
    values["last_seen"] = norm.get("fecha_actualizacion") or norm.get("fecha_registro") or ""
    values["presente"] = 1
    return "(" + ", ".join(sql_value(values[c]) for c in INSERT_COLUMNS) + ")"


def write_migration(out_dir, version, part, rows, label="seed"):
    cols = ", ".join(INSERT_COLUMNS)
    set_clause = ",\n  ".join(f"{c}=excluded.{c}" for c in UPDATE_COLUMNS)
    body = (
        f"-- {label} parte {part}: {len(rows)} registros\n"
        f"INSERT INTO registros\n  ({cols})\nVALUES\n"
        + ",\n".join(rows)
        + f"\nON CONFLICT(fuente, id) DO UPDATE SET\n  {set_clause};\n"
    )
    path = out_dir / f"{version:04d}_{label}_{part:04d}.sql"
    path.write_text(body, encoding="utf-8")
    return path


def next_version(migrations_dir):
    """Siguiente número de migración (máximo prefijo NNNN existente + 1)."""
    versions = []
    for f in Path(migrations_dir).glob("*.sql"):
        prefix = f.stem.split("_", 1)[0]
        if prefix.isdigit():
            versions.append(int(prefix))
    return (max(versions) + 1) if versions else 1


def emit_migrations(records, out_dir, start_version, label, chunk_size=5000):
    """Escribe migraciones idempotentes a partir de registros crudos, en lotes.
    Devuelve {total, rejected, files}. Reutilizado por el seed y por el delta diario."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    buf = []
    state = {"part": 0, "version": start_version, "files": 0}

    def flush():
        if not buf:
            return
        state["part"] += 1
        write_migration(out_dir, state["version"], state["part"], buf, label)
        state["version"] += 1
        state["files"] += 1
        buf.clear()

    total = rejected = 0
    for rec in records:
        total += 1
        row = build_row(rec)
        if row is None:
            rejected += 1
            continue
        buf.append(row)
        if len(buf) >= chunk_size:
            flush()
    flush()
    return {"total": total, "rejected": rejected, "files": state["files"]}


def generate(data_dir, out_dir, chunk_size=5000, start_version=2):
    """Genera las migraciones de seed leyendo los .rar. Limpia las anteriores para
    una corrida determinista. Devuelve {total, rejected, files}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*_seed_*.sql"):
        old.unlink()
    return emit_migrations(stream_records(data_dir), out_dir, start_version, "seed", chunk_size)


def main():
    ap = argparse.ArgumentParser(description="Genera migraciones de seed por lotes.")
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR),
                    help="Directorio con los .rar de datos consolidados.")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--chunk-size", type=int, default=5000)
    ap.add_argument("--start-version", type=int, default=2,
                    help="Número de migración inicial (1 es 0001_init).")
    args = ap.parse_args()

    s = generate(args.data_dir, args.out, args.chunk_size, args.start_version)
    print(f"Procesados:  {s['total']}")
    print(f"Rechazados:  {s['rejected']}  (sin id/nombre)")
    print(f"Insertados:  {s['total'] - s['rejected']}")
    print(f"Migraciones: {s['files']}  ({args.chunk_size} filas/lote) en {args.out}")


if __name__ == "__main__":
    main()
