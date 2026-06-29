import urllib.request
import urllib.error
import json
import csv
import re
import sys
import time
import html
import uuid
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Fuente: venezuelareporta.org (Next.js SSR en Vercel). NO hay API masiva ni
# <lastmod> en el sitemap: cada persona es una pagina /reporte/{uuid} (~53k).
#
# Estado propio del scraper (sin tocar master.db del consolidador):
#   - <output>.jsonl : store durable append-only (1 fila por reporte). Fuente de
#     verdad del set "ya procesado" y del dataset. Append+flush -> resiliente a
#     cortes durante el backfill de ~53k.
#   - <output>.json  : array derivado al cerrar; es lo que ingiere el consolidador.
#
# Modos:
#   incremental (default): baja solo los UUID del sitemap que no estan en el store.
#   --full              : trunca el store y re-baja todo (capta cambios de estado;
#                         el consolidador detecta el delta por content_hash).
#
# Resiliencia a fallos de conexion: http_get reintenta con backoff. Solo se marca
# "procesado" tras un fetch exitoso; un fallo deja el UUID para la proxima corrida.
FUENTE = "venezuelareporta"
BASE = "https://venezuelareporta.org"
SITEMAP_INDEX = f"{BASE}/sitemap.xml"
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
        h = hashlib.sha256(str(val).encode('utf-8')).hexdigest()
        return int(h, 16) % 9223372036854775807


def map_timestamp(val):
    if not val:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(val, (int, float)) or (isinstance(val, str) and val.isdigit()):
        try:
            return datetime.fromtimestamp(float(val) / 1000.0, timezone.utc).isoformat()
        except Exception:
            pass
    try:
        s = str(val).strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        return datetime.fromisoformat(s).isoformat()
    except Exception:
        return str(val)


def http_get(url, tries=4, base_delay=1.5, timeout=30):
    """GET con reintentos y backoff exponencial. Resiliente a cortes de red."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            last = e
            # 4xx (salvo 429) no se reintenta: no va a cambiar
            if e.code < 500 and e.code != 429:
                raise
        except Exception as e:  # URLError, timeout, reset, etc.
            last = e
        if attempt < tries - 1:
            time.sleep(base_delay * (2 ** attempt))
    raise last


def uid_of(url):
    return url.rstrip('/').rsplit('/', 1)[-1]


# ----------------------------- parsing -----------------------------

_RE_TITLE = re.compile(r"<title>([^<]*)</title>")
_RE_NAME = re.compile(r'"mainEntity":\{"@type":"Person","name":"([^"]*)"')
_RE_H1 = re.compile(r'<h1[^>]*>([^<]*)</h1>')
_RE_DESC = re.compile(r'"mainEntity":\{"@type":"Person"[^}]*"description":"([^"]*)"')
_RE_DATE = re.compile(r'"datePublished":"([^"]*)"')
_RE_LOCALITY = re.compile(r'"addressLocality":"([^"]*)"')
_RE_EDAD = re.compile(r'Edad:\s*(\d{1,3})')
_RE_LUGAR = re.compile(r'Lugar:\s*(.+?,?\s*Venezuela)\b', re.IGNORECASE)
_RE_TEL = re.compile(r'tel:([+0-9]{6,})')
_RE_FOTO = re.compile(r'https://[a-z0-9]+\.supabase\.co/storage[^"\\ ]*')

# Estados de la fuente (prefijo del titulo, antes de ":").
_ESTADO_MAP = {
    "se busca": "Desaparecido",
    "encontrado": "Localizado",
    "a salvo": "Localizado",
    "localizado": "Localizado",
    "fallecido": "Fallecido",
}


def map_estado(prefix):
    p = (prefix or "").strip().lower()
    if p in _ESTADO_MAP:
        return _ESTADO_MAP[p]
    if p.startswith("se busca"):
        return "Desaparecido"
    if "fallec" in p:
        return "Fallecido"
    if p:  # cualquier otro prefijo conocido de "resuelto"
        return "Localizado"
    return "Desaparecido"


def parse_report(page_html, url):
    """Extrae los 16 campos canonicos de una pagina /reporte/{uuid}.
    Devuelve None si la pagina no parece un reporte valido (sin nombre)."""
    uid = uid_of(url)

    title = _RE_TITLE.search(page_html)
    title = html.unescape(title.group(1)) if title else ""
    estado_prefix = title.split(':', 1)[0] if ':' in title else ""
    estado = map_estado(estado_prefix)

    name_m = _RE_NAME.search(page_html) or _RE_H1.search(page_html)
    nombre = html.unescape(name_m.group(1)).strip() if name_m else None
    if not nombre:
        return None

    desc_m = _RE_DESC.search(page_html)
    desc = html.unescape(desc_m.group(1)).strip() if desc_m else ""

    edad_m = _RE_EDAD.search(desc)
    edad = int(edad_m.group(1)) if edad_m else None

    # ubicacion: cortar en "...Venezuela"; fallback a addressLocality.
    lugar_m = _RE_LUGAR.search(desc)
    if lugar_m:
        ubicacion = lugar_m.group(1).strip()
        resto = desc[lugar_m.end():].lstrip(" .").strip()  # descripcion fisica / "Ultima vez visto"
    else:
        loc_m = _RE_LOCALITY.search(page_html)
        ubicacion = html.unescape(loc_m.group(1)).strip() if loc_m else None
        resto = ""

    observaciones = resto or None

    tel_m = _RE_TEL.search(page_html)
    telefono = tel_m.group(1) if tel_m else None

    foto_m = _RE_FOTO.search(page_html)
    foto = foto_m.group(0) if foto_m else None

    date_m = _RE_DATE.search(page_html)
    fecha = map_timestamp(date_m.group(1) if date_m else None)

    es_menor = edad is not None and edad < 18

    ubicacion_encontrado = None if estado == "Desaparecido" else ubicacion

    return {
        "id": map_id(uid),
        "nombre": nombre,
        "cedula": "N/D",
        "edad": edad,
        "ultima_ubicacion": ubicacion,
        "telefono_contacto": telefono,
        "observaciones": observaciones,
        "estado": estado,
        "ubicacion_encontrado": ubicacion_encontrado,
        "encontrado_por": None,
        "encontrado_por_cedula": None,
        "foto_url": foto,
        "fecha_registro": fecha,
        "fecha_actualizacion": fecha,
        "es_menor": es_menor,
        "fuente": FUENTE,
    }


# ----------------------------- enumeracion / estado -----------------------------

_RE_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
_RE_REPORTE = re.compile(r"https://venezuelareporta\.org/reporte/[a-f0-9-]+")


def fetch_sitemap_uuids(max_sitemaps=None):
    """Devuelve la lista de URLs /reporte/{uuid} de todos los sub-sitemaps."""
    index = http_get(SITEMAP_INDEX)
    submaps = [u for u in _RE_LOC.findall(index) if "/sitemap/" in u]
    if max_sitemaps:
        submaps = submaps[:max_sitemaps]
    urls = []
    for i, sm in enumerate(submaps):
        try:
            body = http_get(sm)
        except Exception as e:
            print(f"   aviso: sub-sitemap fallo ({sm}): {e}", file=sys.stderr)
            continue
        urls.extend(_RE_REPORTE.findall(body))
        print(f"\r   sitemap {i + 1}/{len(submaps)} ({len(urls)} reportes)... ", end="", flush=True)
    print()
    # dedup preservando orden (newest-first segun el sitemap)
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


def load_seen(jsonl_path):
    """Carga el store JSONL -> dict id(str)->row. Es el set de 'ya procesado'
    (incluye filas rechazadas, marcadas con rejected=True, para no reintentarlas).
    Ignora lineas truncadas por un corte."""
    rows = {}
    p = Path(jsonl_path)
    if not p.exists():
        return rows
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                rows[str(r["id"])] = r
            except (json.JSONDecodeError, KeyError):
                continue
    return rows


def rows_for_output(seen):
    """Filas a emitir: las del store que no son marcadores de rechazo."""
    return [r for r in seen.values() if not r.get("rejected")]


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


# ----------------------------- main -----------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Scraper incremental de venezuelareporta.org (store JSON propio + resiliencia)."
    )
    ap.add_argument("--output", default="venezuelareporta", help="Nombre base de salida sin extension.")
    ap.add_argument("--limit", type=int, default=None, help="Maximo de reportes NUEVOS a bajar (pruebas).")
    ap.add_argument("--max-sitemaps", type=int, default=None, help="Limitar sub-sitemaps a leer (pruebas).")
    ap.add_argument("--full", action="store_true", help="Trunca el store y re-baja todo (capta cambios).")
    ap.add_argument("--sleep", type=float, default=0.1, help="Pausa entre paginas (cortesia).")
    args = ap.parse_args()

    base = args.output
    for ext in (".json", ".csv", ".jsonl"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    out_json = f"{base}.json"
    out_csv = f"{base}.csv"
    store = f"{base}.jsonl"

    print("====================================================")
    print("   SCRAPER venezuelareporta.org -> ESQUEMA BBDD      ")
    print("====================================================")

    if args.full and Path(store).exists():
        Path(store).unlink()
        print("Modo --full: store truncado, se re-baja todo.")

    seen = load_seen(store)
    print(f"Reportes ya en el store: {len(seen)}")

    print("Leyendo sitemap...")
    urls = fetch_sitemap_uuids(max_sitemaps=args.max_sitemaps)
    print(f"Total de reportes en el sitemap: {len(urls)}")

    pending = [u for u in urls if str(map_id(uid_of(u))) not in seen]
    print(f"Reportes nuevos a bajar: {len(pending)}")

    ck = open(store, "a", encoding="utf-8")
    fetched = 0
    failed = 0
    try:
        for u in pending:
            if args.limit and fetched >= args.limit:
                print(f"\nLimite de {args.limit} reportes nuevos alcanzado.")
                break
            try:
                page = http_get(u)
            except Exception as e:
                failed += 1
                print(f"\n   fallo definitivo {u}: {e}", file=sys.stderr)
                continue  # sigue "nuevo": se reintenta en la proxima corrida

            row = parse_report(page, u)
            if row is None:
                # marcar como procesado-rechazado para no reintentar eternamente
                marker = {"id": map_id(uid_of(u)), "rejected": True}
                ck.write(json.dumps(marker, ensure_ascii=False) + "\n")
                ck.flush()
                seen[str(marker["id"])] = marker
                failed += 1
                continue

            ck.write(json.dumps(row, ensure_ascii=False) + "\n")
            ck.flush()
            seen[str(row["id"])] = row
            fetched += 1
            print(f"\rBajados {fetched}/{len(pending)} (rechazados/fallos: {failed})... ", end="", flush=True)
            time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\nInterrumpido: el progreso quedo en el store, se reanuda en la proxima corrida.")
    finally:
        ck.close()

    # Salida consolidada para el consolidador (array JSON) + CSV: solo no-rechazados.
    rows = rows_for_output(seen)
    write_outputs(rows, base)

    print(f"\nListo. Nuevos esta corrida: {fetched} | rechazados/fallidos: {failed}")
    print(f"Total acumulado en salida: {len(rows)}")
    print(f"  - JSON:  '{out_json}'  (para el consolidador)")
    print(f"  - CSV:   '{out_csv}'")
    print(f"  - store: '{store}'")


if __name__ == "__main__":
    main()
