# Scraper: venezuelareporta.org

Fuente maestra de reportes del terremoto (venezuelatebusca y Tilores consumen su
upstream). **Next.js SSR en Vercel. NO hay API masiva ni `<lastmod>` en el sitemap:**
cada persona es una página `/reporte/{uuid}` (~53.000). Los datos se extraen del
**JSON-LD + título** de cada página.

## Estado propio del scraper (store JSON)

No depende de `master.db` del consolidador. Mantiene su propio estado en dos archivos:

- **`venezuelareporta.jsonl`** — store durable, append-only (1 fila JSON por reporte).
  Es la **fuente de verdad** del set "ya procesado" y del dataset. Append + `flush`
  tras cada fetch → un corte de red no pierde lo ya bajado (clave en el backfill de ~53k).
  Las páginas sin nombre se marcan `{"id":…, "rejected":true}` para no reintentarlas.
- **`venezuelareporta.json`** — array derivado al cerrar la corrida; es la **salida que
  ingiere el consolidador** (+ `venezuelareporta.csv`).

> ⚠️ **`venezuelareporta.jsonl` SÍ se commitea al repo** (está des-ignorado en
> `.gitignore`). Es estado **compartido del equipo**: quien clone el repo parte de
> este store y solo baja lo nuevo, en vez de re-backfillear las ~53k páginas. Súbelo
> tras cada corrida significativa para que el resto tenga los datos al día.
>
> El `.json` y el `.csv` son **derivados regenerables** desde el `.jsonl` → siguen
> gitignoreados (no se commitean, evita duplicar el dato).

## Estrategia incremental (set-diff)

Como los reportes son UUID sin orden ni `lastmod`, "continuar desde lo último" es un
**set-diff**, no un cursor:

1. Leer todos los UUID del sitemap (`/sitemap.xml` → 53 sub-sitemaps de 1000).
2. Restar los `id` ya presentes en el store.
3. Bajar **solo los que faltan**.

Idempotente y **auto-resumible**: si una corrida se cae, la siguiente rehace el diff
y sigue. 1ra corrida = backfill (~53k); las siguientes solo bajan lo nuevo.

## Modos

- **Incremental (default):** baja solo los UUID nuevos. Diario barato.
- **`--full`:** trunca el store y re-baja **todo** → capta cambios de estado
  (Se busca → Encontrado) en reportes viejos. El consolidador detecta el delta por
  `content_hash`. Pensado para corrida **programada** (ej. semanal).

## Resiliencia a fallos de conexión

`http_get` reintenta con **backoff exponencial** (timeout / `URLError` / 5xx / 429;
4xx salvo 429 no se reintenta). Una página que falla definitivamente se omite y sigue
siendo "nueva" → se reintenta en la próxima corrida. Progreso durable vía el `.jsonl`.

## Mapeo al esquema unificado

| Campo | Origen | Nota |
|---|---|---|
| `id` | `map_id(uuid)` | bigint (la API exige `id` bigint) |
| `nombre` | JSON-LD `mainEntity.Person.name` (fallback `<h1>`) | a veces truncado en la fuente (`"…"`) |
| `cedula` | — | `"N/D"` (no expuesta) |
| `edad` | `"Edad: NN"` en la descripción | |
| `ultima_ubicacion` | `"Lugar: …Venezuela"` (cortado), fallback `addressLocality` | |
| `telefono_contacto` | enlace `tel:` | contacto de la familia |
| `observaciones` | resto de la descripción (señas físicas, "Última vez visto") | |
| `estado` | prefijo del título | `Se busca`→Desaparecido; `Encontrado`/`A salvo`→Localizado; `Fallecido`→Fallecido |
| `ubicacion_encontrado` | ubicación si está localizado | |
| `foto_url` | foto real de Supabase Storage (`/storage/.../fotos/`) | rara; el OG-image no se usa |
| `fecha_registro` / `fecha_actualizacion` | `datePublished` | |
| `es_menor` | `edad < 18` | |
| `fuente` | — | `"venezuelareporta"` |

## Uso

```bash
cd scrapers/venezuelareporta
python scraper.py --max-sitemaps 1 --limit 5 --output _smoke   # prueba rápida
python scraper.py                                              # incremental (solo nuevos)
python scraper.py --full                                       # refresh completo (re-baja todo)
```

## Tests

```bash
cd scrapers/venezuelareporta && python3 -m unittest test_scraper -v
```

17 tests: `map_id`/`map_timestamp`/`map_estado`, `parse_report` (HTML mínimo) y
`load_seen` (incl. línea truncada y marcadores `rejected`).
