"""
api.py

Sube las partes del delta (.xlsx) a la API de aquiestoyvenezuela.com, con el
mismo contrato que send_to_api.py (multipart, header X-API-Key). Cada parte se
sube por separado; devuelve el resultado por archivo para el reporte.

La config sale de variables de entorno (con los valores actuales como fallback),
para no clavar credenciales nuevas: AEV_API_URL, AEV_API_KEY, AEV_ID_USUARIO,
AEV_ID_HOSPITAL.
"""

import os
from pathlib import Path

import requests


def _load_dotenv():
    """Carga el .env de la raíz del repo si existe (sin pisar variables ya
    definidas en el entorno). Mínimo, sin dependencias."""
    env = Path(__file__).resolve().parents[2] / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()

API_URL = os.environ.get("AEV_API_URL", "https://aquiestoyvenezuela.com/api/post_carga_doc.php")
API_KEY = os.environ.get("AEV_API_KEY", "%iRjRkN&Ve8+YP9*U2R1voNvcQq1d^6F")
ID_USUARIO = os.environ.get("AEV_ID_USUARIO", "1")
ID_HOSPITAL = os.environ.get("AEV_ID_HOSPITAL", "1")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload_file(path, timeout=120):
    """Sube un .xlsx. Devuelve (status_code, texto_respuesta_recortado)."""
    path = Path(path)
    with open(path, "rb") as f:
        resp = requests.post(
            API_URL,
            headers={"X-API-Key": API_KEY},
            files={"file": (path.name, f, XLSX_MIME)},
            data={"id_usuario": ID_USUARIO, "id_hospital": ID_HOSPITAL},
            timeout=timeout,
        )
    return resp.status_code, resp.text[:500]


def upload_delta(paths, timeout=120):
    """Sube cada parte del delta. Devuelve una lista de resultados por archivo."""
    results = []
    for p in paths:
        name = Path(p).name
        try:
            status, text = upload_file(p, timeout)
            results.append({"file": name, "status": status, "ok": status == 200, "resp": text})
        except requests.exceptions.RequestException as e:
            results.append({"file": name, "status": None, "ok": False, "resp": str(e)})
    return results
