"""
run_daily.py

Orquestador de la corrida diaria de scraping de personas desaparecidas Venezuela.
Ejecuta en secuencia todos los scrapers, consolida datos, genera XLSX y llama a la API.

Uso manual:  python run_daily.py
Programado:  configurar con setup_tarea_diaria.ps1
"""

import subprocess
import sys
import json
import zipfile
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR   = Path(__file__).parent
AMILKIR    = BASE_DIR / "Amilkir"
CHIKI      = BASE_DIR / "chiki"
DATOS      = BASE_DIR / "datos_consolidados"
LOGS       = BASE_DIR / "logs"

_log_lines = []


def log(msg):
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log_lines.append(line)


def run_step(label, cmd, cwd=None):
    log(f">>> {label}")
    result = subprocess.run(cmd, cwd=str(cwd or BASE_DIR))
    if result.returncode != 0:
        log(f"ERROR: '{label}' terminó con código {result.returncode}")
        return False
    log(f"OK:  {label}")
    return True


def merge_all():
    """Combina los outputs de todos los scrapers en un único store consolidado.
    Clave de dedup: (id, fuente) — actualiza registros existentes en cada corrida."""
    DATOS.mkdir(exist_ok=True)
    todos_path = DATOS / "todos_registros.json"

    # Cargar store existente
    store = {}
    if todos_path.exists():
        try:
            for r in json.loads(todos_path.read_text(encoding="utf-8")):
                key = f"{r.get('id')}|{r.get('fuente', '')}"
                store[key] = r
            log(f"Store existente cargado: {len(store)} registros")
        except Exception as e:
            log(f"Advertencia al cargar store: {e}  (se iniciará vacío)")

    # Fuentes a combinar
    sources = [
        AMILKIR / "personas_venezuela.json",
        CHIKI   / "desaparecidos_redayudavenezuela.json",
        CHIKI   / "localizados_redayudavenezuela.json",
        CHIKI   / "personas_desaparecidas_venezuela_parsed.json",
    ]

    for src in sources:
        if not src.exists():
            log(f"  Omitiendo (no encontrado): {src.name}")
            continue
        try:
            records = json.loads(src.read_text(encoding="utf-8"))
            nuevos = 0
            for r in records:
                key = f"{r.get('id')}|{r.get('fuente', '')}"
                if key not in store:
                    nuevos += 1
                store[key] = r
            log(f"  {src.name}: {len(records)} registros ({nuevos} nuevos)")
        except Exception as e:
            log(f"  Error al procesar {src.name}: {e}")

    all_records = list(store.values())
    todos_path.write_text(
        json.dumps(all_records, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    log(f"Store consolidado actualizado: {len(all_records)} registros totales")
    return len(all_records)


def compress_json():
    """Comprime el archivo JSON consolidado en un archivo ZIP para ahorrar espacio y cumplir límites."""
    todos_path = DATOS / "todos_registros.json"
    zip_path = DATOS / "todos_registros.zip"
    if not todos_path.exists():
        log(f"Advertencia: No se encontró {todos_path.name} para comprimir")
        return False
    try:
        log(f"Comprimiendo {todos_path.name} a {zip_path.name}...")
        t0 = datetime.now(timezone.utc)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(todos_path, arcname=todos_path.name)
        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        log(f"OK: ZIP generado ({size_mb:.2f} MB) en {elapsed:.1f}s")
        return True
    except Exception as e:
        log(f"Error al comprimir a ZIP: {e}")
        return False


def save_log():
    LOGS.mkdir(exist_ok=True)
    date_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path  = LOGS / f"{date_str}.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(_log_lines) + "\n\n")
    print(f"Log guardado en: {log_path}")


def main():
    t0 = datetime.now(timezone.utc)
    log("=" * 52)
    log("INICIO CORRIDA DIARIA — SCRAPING VENEZUELA AEV")
    log("=" * 52)

    # 1. Venezuela Te Busca (Node.js, modo incremental)
    run_step(
        "venezuelatebusca.com",
        ["node", "scraper.js", "--update"],
        cwd=AMILKIR
    )

    # 2. Red Ayuda Venezuela — activos
    run_step(
        "redayudavenezuela.com (activos)",
        [sys.executable, "scraper.py", "--status", "active",
         "--output", "desaparecidos_redayudavenezuela"],
        cwd=CHIKI
    )

    # 3. Red Ayuda Venezuela — localizados
    run_step(
        "redayudavenezuela.com (localizados)",
        [sys.executable, "scraper.py", "--status", "found",
         "--output", "localizados_redayudavenezuela"],
        cwd=CHIKI
    )

    # 4. Terremoto — Playwright headless
    ok_terremoto = run_step(
        "desaparecidosterremotovenezuela.com (Playwright)",
        [sys.executable, "scraper_terremoto.py"],
        cwd=CHIKI
    )

    # 5. Parse datos terremoto (depende del paso anterior)
    if ok_terremoto:
        run_step(
            "parse_desaparecidos.py",
            [sys.executable, "parse_desaparecidos.py"],
            cwd=CHIKI
        )
    else:
        log("SKIP: parse_desaparecidos.py (scraper terremoto falló)")

    # 6. Consolidar todos los datos
    log("Consolidando datos de todas las fuentes...")
    merge_all()

    # 6.5. Comprimir JSON a ZIP
    compress_json()

    # 7. Generar XLSX
    ok_xlsx = run_step(
        "generate_xlsx.py",
        [sys.executable, str(BASE_DIR / "generate_xlsx.py")]
    )

    # 8. Enviar a API
    if ok_xlsx:
        run_step(
            "send_to_api.py",
            [sys.executable, str(BASE_DIR / "send_to_api.py")]
        )
    else:
        log("SKIP: send_to_api.py (generación XLSX falló)")

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    log(f"FIN CORRIDA DIARIA ({elapsed:.0f}s)")
    save_log()


if __name__ == "__main__":
    main()
