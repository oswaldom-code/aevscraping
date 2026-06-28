"""
diff.py

Contrasta los registros entrantes (salida de scrapers) contra el maestro y los
clasifica. El maestro se indexa por (fuente, id) -> content_hash.

Embudo:
  procesados
  ├─ rechazados        (sin id/nombre)         -> rechazados.csv
  └─ válidos
     ├─ nuevos         (llave no existe)        -> delta
     ├─ actualizados   (existe, hash distinto)  -> delta
     ├─ sin_cambio     (existe, hash igual)
     └─ duplicados_lote (misma llave 2x en la corrida)
"""

from consolidator.lib.registros import content_hash, normalize_record


def load_master_index(con):
    """(fuente, id) -> content_hash de todo el maestro."""
    return {(f, i): h for f, i, h in
            con.execute("SELECT fuente, id, content_hash FROM registros")}


def classify(records, master_index):
    """Clasifica un iterable de registros crudos. Devuelve listas + conteos.
    'nuevos' y 'actualizados' vienen normalizados y con content_hash incluido."""
    seen = set()
    nuevos, actualizados, rechazados = [], [], []
    sin_cambio = duplicados = procesados = 0

    for rec in records:
        procesados += 1
        norm = normalize_record(rec)
        if norm is None:
            rechazados.append(rec)
            continue
        key = (norm["fuente"], norm["id"])
        if key in seen:
            duplicados += 1
            continue
        seen.add(key)

        ch = content_hash(norm)
        norm["content_hash"] = ch
        prev = master_index.get(key)
        if prev is None:
            nuevos.append(norm)
        elif prev != ch:
            actualizados.append(norm)
        else:
            sin_cambio += 1

    return {
        "procesados": procesados,
        "nuevos": nuevos,
        "actualizados": actualizados,
        "sin_cambio": sin_cambio,
        "duplicados_lote": duplicados,
        "rechazados": rechazados,
    }
