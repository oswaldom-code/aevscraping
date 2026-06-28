"""
cotejo.py

Corre el cotejo cross-source sobre el maestro y escribe los resultados. Es de
SOLO LECTURA: no modifica master.db.

Uso:
    .venv/bin/python consolidator/cotejo.py
    .venv/bin/python consolidator/cotejo.py --solo-alertas   # solo "buscado/localizado"

Salida en consolidator/out/cotejo_<run_id>/:
    coincidencias.json   grupos cross-source (alertas primero)
    reporte.json         conteos
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from consolidator.lib.cotejo import find_matches, load_master_records, summarize

BASE = Path(__file__).resolve().parent
DEFAULT_DB = BASE / "master.db"
OUT = BASE / "out"


def main():
    ap = argparse.ArgumentParser(description="Cotejo cross-source sobre el maestro (standalone).")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--solo-alertas", action="store_true",
                    help="Emite solo los grupos con alerta crítica.")
    args = ap.parse_args()

    records = load_master_records(args.db)
    grupos = find_matches(records)
    if args.solo_alertas:
        grupos = [g for g in grupos if g["alerta_critica"]]

    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = OUT / f"cotejo_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "coincidencias.json").write_text(
        json.dumps(grupos, indent=2, ensure_ascii=False), encoding="utf-8")
    resumen = {"run_id": run_id, "registros_maestro": len(records), **summarize(grupos)}
    (out_dir / "reporte.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"registros maestro:   {len(records)}")
    print(f"grupos coincidencia: {resumen['grupos_coincidencia']}")
    print(f"alertas críticas:    {resumen['alertas_criticas']}  (buscado en A / resuelto en B)")
    print(f"salida en {out_dir}")


if __name__ == "__main__":
    main()
