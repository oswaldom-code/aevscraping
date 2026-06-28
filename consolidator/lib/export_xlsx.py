"""
export_xlsx.py

Escribe el delta (nuevos + actualizados) en uno o varios .xlsx, cada uno por
debajo de un tope de tamaño (default 5MB). Las columnas y etiquetas replican el
xlsx que ya consume la API (generate_xlsx.py), para que el delta sea ingestible
igual que el archivo completo.

El .xlsx es un ZIP comprimido: no se puede predecir el tamaño final por fila, así
que se escribe y se mide; si una parte excede el tope, se re-particiona en más
partes y se reescribe (converge en 1-2 iteraciones porque el tamaño es ~lineal).
"""

from math import ceil
from pathlib import Path

import openpyxl

COLUMNS = [
    "id", "nombre", "cedula", "edad", "ultima_ubicacion", "telefono_contacto",
    "observaciones", "estado", "ubicacion_encontrado", "encontrado_por",
    "encontrado_por_cedula", "foto_url", "fecha_registro", "fecha_actualizacion",
    "es_menor", "fuente",
]
COLUMN_LABELS = {
    "id": "ID", "nombre": "Nombre", "cedula": "Cédula", "edad": "Edad",
    "ultima_ubicacion": "Última Ubicación", "telefono_contacto": "Teléfono Contacto",
    "observaciones": "Observaciones", "estado": "Estado",
    "ubicacion_encontrado": "Ubicación Encontrado", "encontrado_por": "Encontrado Por",
    "encontrado_por_cedula": "Cédula Encontrado", "foto_url": "URL Foto",
    "fecha_registro": "Fecha Registro", "fecha_actualizacion": "Fecha Actualización",
    "es_menor": "Es Menor", "fuente": "Fuente",
}


def _write_xlsx(records, path, title="Delta"):
    wb = openpyxl.Workbook(write_only=True)   # write_only: bajo consumo de memoria
    ws = wb.create_sheet(title)
    ws.append([COLUMN_LABELS[c] for c in COLUMNS])
    for r in records:
        row = []
        for c in COLUMNS:
            v = r.get(c)
            if isinstance(v, bool):
                v = "Sí" if v else "No"
            row.append(v)
        ws.append(row)
    wb.save(path)


def _write_parts(records, out_dir, parts, prefix, title):
    for old in out_dir.glob(f"{prefix}_*.xlsx"):
        old.unlink()
    size = ceil(len(records) / parts)
    paths = []
    for idx in range(parts):
        chunk = records[idx * size:(idx + 1) * size]
        if not chunk:
            break
        path = out_dir / f"{prefix}_{idx + 1:03d}.xlsx"
        _write_xlsx(chunk, path, title)
        paths.append(path)
    return paths


def export_delta(records, out_dir, max_mb=5, prefix="delta_parte", title="Delta"):
    """Escribe el delta en .xlsx de a lo sumo max_mb. Devuelve la lista de rutas."""
    records = list(records)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not records:
        return []

    max_bytes = int(max_mb * 1_000_000)
    parts = 1
    while True:
        paths = _write_parts(records, out_dir, parts, prefix, title)
        sizes = [p.stat().st_size for p in paths]
        if all(s <= max_bytes for s in sizes) or parts >= len(records):
            return paths
        worst = max(sizes)
        # objetivo 0.92*tope como margen ante variación de compresión
        parts = max(parts + 1, ceil(parts * worst / (max_bytes * 0.92)))
