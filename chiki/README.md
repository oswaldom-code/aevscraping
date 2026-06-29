# Scrapers en `chiki/`

> _Pendiente de documentar en detalle por el dev responsable._

Directorio con varios scrapers. Resumen mínimo:

## redayudavenezuela.com → `chiki/scraper.py`

Supabase REST (`missing_persons`, anon key), paginado por header `Range`. Se corre
dos veces: `--status active` y `--status found`.

```bash
cd chiki
python scraper.py --status active --output desaparecidos_redayudavenezuela
python scraper.py --status found  --output localizados_redayudavenezuela
```

`fuente = "redayudavenezuela"`.

## desaparecidosterremotovenezuela.com → `chiki/scraper_terremoto.py` + `parse_desaparecidos.py`

API gated por reCAPTCHA v3 → se conduce con Playwright (Chromium headless). El scraper
emite crudo; `parse_desaparecidos.py` lo mapea al esquema y descarta spam.

```bash
cd chiki
python scraper_terremoto.py && python parse_desaparecidos.py
```

`fuente = "desaparecidosterremoto"`.

## Fuera del pipeline diario

- `scraper_pacientesve.py` (+ `index.html/js/css`) — herramienta de pacientes
  hospitalizados, **no** forma parte del pipeline de desaparecidos.
