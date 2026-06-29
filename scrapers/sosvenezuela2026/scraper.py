import urllib.request
import json
import csv
import sys
import argparse
import time
import uuid
import hashlib
from datetime import datetime, timezone

BASE_URL = "https://sosvenezuela2026.com/api"
PAGE_SIZE = 100  # el servidor ignora limit mayores y devuelve 100 fijo
USER_AGENT = "CentralizadorHumanitario/1.0 (Contacto: ayuda-humanitaria@ejemplo.com)"

CANONICAL_COLUMNS = [
    "id", "nombre", "cedula", "edad", "ultima_ubicacion", "telefono_contacto",
    "observaciones", "estado", "ubicacion_encontrado", "encontrado_por",
    "encontrado_por_cedula", "foto_url", "fecha_registro", "fecha_actualizacion",
    "es_menor", "fuente",
]


def map_id(val):
    if not val:
        return 0
    try:
        # Convert UUID to bigint (signed 64-bit integer: max 9223372036854775807)
        return uuid.UUID(str(val)).int % 9223372036854775807
    except ValueError:
        # Fallback to standard SHA-256 hash if not a valid UUID string
        h = hashlib.sha256(str(val).encode('utf-8')).hexdigest()
        return int(h, 16) % 9223372036854775807


def map_timestamp(val):
    if not val:
        return datetime.now(timezone.utc).isoformat()
    # If it's a number (milliseconds Unix timestamp)
    if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
        try:
            return datetime.fromtimestamp(float(val) / 1000.0, timezone.utc).isoformat()
        except Exception:
            pass
    # If it's already an ISO or date string
    try:
        s = str(val).strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        return dt.isoformat()
    except Exception:
        return str(val)


def _clean(val):
    if val is None:
        return None
    s = str(val).replace("\n", " ").strip()
    return s if s else None


def map_estado(status):
    # status conocidos: "seeking_info" (desaparecido), "found_alive" (localizado).
    # Defensivo ante variantes "found_*".
    s = (status or "").lower()
    if s.startswith("found"):
        if "dead" in s or "deceased" in s:
            return "Fallecido"
        return "Localizado"
    return "Desaparecido"


def map_row(item):
    # nombre: text, NOT NULL
    nombre = _clean(item.get("display_name")) or "Desconocido"

    # cedula: text, NOT NULL (la fuente la enmascara -> casi siempre N/D)
    cedula = _clean(item.get("cedula_masked")) or "N/D"

    # ultima_ubicacion: parroquia trae una ruta rica ("Estado · Municipio · Lugar")
    ultima_ubicacion = _clean(item.get("parroquia")) or _clean(item.get("municipio"))

    # estado
    status = item.get("status")
    estado = map_estado(status)

    # hospital_name: usar como ubicacion_encontrado si esta localizado, si no como observacion
    hospital = _clean(item.get("hospital_name"))
    if estado == "Desaparecido":
        ubicacion_encontrado = None
        observaciones = f"Hospital: {hospital}" if hospital else None
    else:
        ubicacion_encontrado = hospital
        observaciones = None

    # es_menor: la fuente anonimiza a los menores como "Menor reportado"
    es_menor = (nombre.strip().lower() == "menor reportado")

    fecha_registro = map_timestamp(item.get("source_date"))

    return {
        "id": map_id(item.get("id")),
        "nombre": nombre,
        "cedula": cedula,
        "edad": None,  # no disponible en esta fuente
        "ultima_ubicacion": ultima_ubicacion,
        "telefono_contacto": None,  # PII restringida, no expuesta
        "observaciones": observaciones,
        "estado": estado,
        "ubicacion_encontrado": ubicacion_encontrado,
        "encontrado_por": None,
        "encontrado_por_cedula": None,
        "foto_url": _clean(item.get("photo_path")),
        "fecha_registro": fecha_registro,
        "fecha_actualizacion": fecha_registro,
        "es_menor": es_menor,
        "fuente": "sosvenezuela2026",
    }


def fetch_page(page):
    url = f"{BASE_URL}/persons/list?page={page}&limit={PAGE_SIZE}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"\nError descargando la pagina {page}: {e}", file=sys.stderr)
        return None


def fetch_stats():
    url = f"{BASE_URL}/persons/stats"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return None


def write_outputs(rows, base):
    """Escribe <base>.json (array) y <base>.csv en el esquema de 16 columnas.
    Devuelve (ruta_json, ruta_csv)."""
    out_json = f"{base}.json"
    out_csv = f"{base}.csv"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CANONICAL_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return out_json, out_csv


def main():
    parser = argparse.ArgumentParser(
        description="Exporta personas desaparecidas/localizadas de sosvenezuela2026.com y las adapta al esquema unificado."
    )
    parser.add_argument("--limit", type=int, default=None, help="Limite maximo de registros a descargar (para pruebas).")
    parser.add_argument("--output", default="sosvenezuela2026", help="Nombre base de los archivos de salida sin extension.")
    args = parser.parse_args()

    output_base = args.output
    if output_base.endswith('.csv'):
        output_base = output_base[:-4]
    elif output_base.endswith('.json'):
        output_base = output_base[:-5]

    output_csv = f"{output_base}.csv"
    output_json = f"{output_base}.json"

    print("====================================================")
    print("   EXPORTADOR sosvenezuela2026.com -> ESQUEMA BBDD   ")
    print("====================================================")
    stats = fetch_stats()
    if stats:
        print(f"Totales segun la fuente: {stats.get('total')} (desaparecidos: {stats.get('missing')}, localizados: {stats.get('found')})")
    print(f"Archivo CSV de salida: {output_csv}")
    print(f"Archivo JSON de salida: {output_json}")
    if args.limit:
        print(f"Limite de descarga: {args.limit} registros")
    print("----------------------------------------------------")

    page = 1
    total_written = 0
    all_rows = []
    seen_ids = set()  # corta si la API repite (defensa ante paginacion inconsistente)

    try:
        while True:
            if args.limit and total_written >= args.limit:
                print(f"\nLimite de {args.limit} registros alcanzado.")
                break

            print(f"\rDescargando pagina {page} (registros: {total_written})... ", end="", flush=True)

            chunk = fetch_page(page)
            if chunk is None:
                print("Reintentando en 3 segundos...")
                time.sleep(3)
                chunk = fetch_page(page)
                if chunk is None:
                    print("Error persistente. Deteniendo descarga.")
                    break

            if not chunk:
                print("\nNo hay mas registros disponibles.")
                break

            new_in_page = 0
            for item in chunk:
                rid = item.get("id")
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                all_rows.append(map_row(item))
                total_written += 1
                new_in_page += 1
                if args.limit and total_written >= args.limit:
                    break

            if new_in_page == 0:
                print("\nLa pagina no aporto registros nuevos. Deteniendo.")
                break

            # Si la pagina vino incompleta, es la ultima
            if len(chunk) < PAGE_SIZE:
                print("\nUltima pagina (incompleta) alcanzada.")
                break

            page += 1
            time.sleep(0.1)  # cortesia con el servidor

        if all_rows:
            write_outputs(all_rows, output_base)
            print(f"\nDescarga finalizada con exito. Se guardaron {len(all_rows)} registros en:")
            print(f"  - CSV: '{output_csv}'")
            print(f"  - JSON: '{output_json}'")
        else:
            print("\nNo se encontraron registros para exportar.")

    except KeyboardInterrupt:
        print("\nDescarga cancelada por el usuario.")


if __name__ == "__main__":
    main()
