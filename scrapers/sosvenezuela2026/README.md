# Scraper: sosvenezuela2026.com

Fuente de personas desaparecidas/localizadas. Next.js con **API REST propia,
pública, sin auth ni captcha**. La fuente a su vez **agrega datos de
desaparecidosvenezuela.com** (visible en `photo_path` y en las notas internas).

## Endpoints

| Endpoint | Uso |
|---|---|
| `GET /api/persons/list?page=N&limit=100` | Listado paginado. `limit` **topa en 100** (valores mayores se ignoran). |
| `GET /api/persons/stats` | Totales: `{missing, found, total, missing_minors, found_minors}`. |
| `GET /api/persons/{id}` | Detalle (no usado): solo añade `note_text`, `sex`, `is_minor`, `tips`. |

Volumen actual: ~52.380 registros (~524 páginas).

## Estrategia: solo-listado

El listado cubre casi todo el esquema unificado. El detalle costaría ~1 request
por persona (~52k) y solo aportaría `note_text`/`sex`, por lo que **no se usa**.

`status` conocidos: `seeking_info` → `Desaparecido`, `found_alive` → `Localizado`.
`es_menor` se infiere de `display_name == "Menor reportado"` (la fuente anonimiza
así a los menores; verificado contra el campo `is_minor` del detalle).

## Campos NO disponibles en esta fuente

- `edad`: no expuesta (a veces aparece dentro de `note_text` en el detalle, no usado).
- `telefono_contacto`: PII restringida, nunca expuesta.
- `cedula`: enmascarada (`cedula_masked`), casi siempre nula → `"N/D"`.

## Uso

```bash
cd scrapers/sosvenezuela2026
python scraper.py --limit 5 --output _smoke   # prueba rápida
python scraper.py                             # corrida completa -> sosvenezuela2026.{json,csv}
```

Escribe con rutas relativas (igual que el resto de scrapers): ejecutar con el
`cwd` en este directorio. `fuente = "sosvenezuela2026"` (clave de dedup).
