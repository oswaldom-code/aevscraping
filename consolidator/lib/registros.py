"""
registros.py

Definición canónica del registro del maestro (16 columnas, esquema missing_persons)
y el cálculo de content_hash. Compartido por el seed y por el diff diario: ambos
deben hashear igual o el diff daría falsos "cambios".
"""

import hashlib

# Columnas canónicas, en el orden del esquema y del consolidado.
CANONICAL_COLUMNS = [
    "id", "nombre", "cedula", "edad", "ultima_ubicacion", "telefono_contacto",
    "observaciones", "estado", "ubicacion_encontrado", "encontrado_por",
    "encontrado_por_cedula", "foto_url", "fecha_registro", "fecha_actualizacion",
    "es_menor", "fuente",
]

# Llave de identidad por fuente.
KEY_COLUMNS = ("fuente", "id")

# Fuente por defecto para registros sin tag (no se descartan: se conserva la persona).
DEFAULT_FUENTE = "desconocida"

# Campos que definen "el contenido" para detectar cambios. Se EXCLUYE
# fecha_actualizacion: cambia en cada re-scrape sin que el dato real cambie,
# y nos haría marcar "actualizado" por nada. (id/fuente son la llave, no contenido.)
HASH_COLUMNS = [
    "nombre", "cedula", "edad", "ultima_ubicacion", "telefono_contacto",
    "observaciones", "estado", "ubicacion_encontrado", "encontrado_por",
    "encontrado_por_cedula", "foto_url", "fecha_registro", "es_menor",
]

_SEP = "\x1f"  # separador improbable en los datos


def clean_text(val):
    """Quita bytes NUL (rompen SQLite y el SQL generado). Deja el resto intacto."""
    if isinstance(val, str):
        return val.replace("\x00", "")
    return val


def _norm(val):
    """Representación estable de un valor para hashear."""
    val = clean_text(val)
    if val is None:
        return ""
    if isinstance(val, bool):
        return "1" if val else "0"
    return str(val).strip()


def content_hash(record):
    """SHA-256 del contenido significativo del registro."""
    joined = _SEP.join(_norm(record.get(col)) for col in HASH_COLUMNS)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def normalize_record(rec):
    """Lleva un registro crudo (de scraper o consolidado) a las 16 columnas
    canónicas. Devuelve el dict normalizado, o None si se rechaza (sin id/nombre).
    Misma lógica para seed y diff → el content_hash coincide."""
    if rec.get("id") in (None, "") or not clean_text(rec.get("nombre")):
        return None
    out = {col: clean_text(rec.get(col)) for col in CANONICAL_COLUMNS}
    out["id"] = str(rec["id"])                      # TEXT, sin perder precisión
    out["fuente"] = out["fuente"] or DEFAULT_FUENTE
    return out
