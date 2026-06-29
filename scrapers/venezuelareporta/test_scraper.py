import os
import sys
import csv
import json
import uuid
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scraper  # noqa: E402

MAX_BIGINT = 9223372036854775807
SCHEMA_FIELDS = [
    "id", "nombre", "cedula", "edad", "ultima_ubicacion", "telefono_contacto",
    "observaciones", "estado", "ubicacion_encontrado", "encontrado_por",
    "encontrado_por_cedula", "foto_url", "fecha_registro", "fecha_actualizacion",
    "es_menor", "fuente",
]


def build_page(title, name, description="", date="2026-06-29T19:08:38.711889+00:00",
               tel=None, foto=None, locality=None, include_person=True):
    """Arma un HTML minimo con lo que el parser necesita (JSON-LD + titulo)."""
    parts = [f"<title>{title}</title>"]
    if include_person:
        person = f'"mainEntity":{{"@type":"Person","name":"{name}","description":"{description}"'
        if locality:
            person += f',"homeLocation":{{"@type":"Place","address":{{"addressLocality":"{locality}"}}}}'
        person += "}"
        parts.append(f'<script type="application/ld+json">[{{"@type":"WebPage",{person}}}]</script>')
    parts.append(f'<script>"datePublished":"{date}"</script>')
    if tel:
        parts.append(f'<a href="tel:{tel}">Llamar</a>')
    if foto:
        parts.append(f'<img src="{foto}">')
    if locality and not include_person:
        parts.append(f'"addressLocality":"{locality}"')
    return "".join(parts)


URL = "https://venezuelareporta.org/reporte/038c38ea-484d-42bc-a101-29e2570067c9"
UID = "038c38ea-484d-42bc-a101-29e2570067c9"


class TestMapId(unittest.TestCase):
    def test_valid_uuid(self):
        self.assertEqual(scraper.map_id(UID), uuid.UUID(UID).int % MAX_BIGINT)

    def test_empty(self):
        self.assertEqual(scraper.map_id(None), 0)


class TestMapTimestamp(unittest.TestCase):
    def test_iso_passthrough(self):
        self.assertEqual(
            scraper.map_timestamp("2026-06-29T19:08:38.711889+00:00"),
            "2026-06-29T19:08:38.711889+00:00",
        )

    def test_z_suffix(self):
        self.assertEqual(scraper.map_timestamp("2026-06-29T12:00:00Z"),
                         "2026-06-29T12:00:00+00:00")


class TestMapEstado(unittest.TestCase):
    def test_se_busca(self):
        self.assertEqual(scraper.map_estado("Se busca"), "Desaparecido")

    def test_encontrado(self):
        self.assertEqual(scraper.map_estado("Encontrado"), "Localizado")

    def test_a_salvo(self):
        self.assertEqual(scraper.map_estado("A salvo"), "Localizado")

    def test_fallecido(self):
        self.assertEqual(scraper.map_estado("Fallecido"), "Fallecido")

    def test_empty_defaults_desaparecido(self):
        self.assertEqual(scraper.map_estado(""), "Desaparecido")


class TestParseReport(unittest.TestCase):
    def test_se_busca_full(self):
        page = build_page(
            title="Se busca: Abel José Velasquez — La Guaira",
            name="Abel José Velasquez",
            description="Alguien busca a esta persona. Edad: 35. Lugar: La Guaira, Catia la mar, Venezuela. El es gordito Última vez visto: En Catia la mar",
            foto="https://wlvcfbuxkdrxhxqlwwmo.supabase.co/storage/v1/object/public/fotos/x.jpg",
        )
        r = scraper.parse_report(page, URL)
        self.assertEqual(list(r.keys()), SCHEMA_FIELDS)
        self.assertEqual(r["nombre"], "Abel José Velasquez")
        self.assertEqual(r["estado"], "Desaparecido")
        self.assertEqual(r["edad"], 35)
        self.assertFalse(r["es_menor"])
        self.assertEqual(r["ultima_ubicacion"], "La Guaira, Catia la mar, Venezuela")
        self.assertIn("Última vez visto", r["observaciones"])
        self.assertIsNone(r["ubicacion_encontrado"])
        self.assertTrue(r["foto_url"].endswith("x.jpg"))
        self.assertEqual(r["cedula"], "N/D")
        self.assertEqual(r["fuente"], "venezuelareporta")
        self.assertEqual(r["id"], uuid.UUID(UID).int % MAX_BIGINT)

    def test_encontrado_sets_ubicacion_encontrado_and_tel(self):
        page = build_page(
            title="Encontrado: Víctor Jardine — Playa Grande",
            name="Víctor Jardine",
            description="Alguien vio o encontró a esta persona. Lugar: Playa Grande, Venezuela.",
            tel="042448342",
        )
        r = scraper.parse_report(page, URL)
        self.assertEqual(r["estado"], "Localizado")
        self.assertEqual(r["ultima_ubicacion"], "Playa Grande, Venezuela")
        self.assertEqual(r["ubicacion_encontrado"], "Playa Grande, Venezuela")
        self.assertEqual(r["telefono_contacto"], "042448342")
        self.assertIsNone(r["edad"])

    def test_minor_inferred_from_edad(self):
        page = build_page(
            title="Se busca: José — Tanaguarena",
            name="José",
            description="Alguien busca a esta persona. Edad: 13. Lugar: Tanaguarena, San Agustín, Venezuela.",
        )
        self.assertTrue(scraper.parse_report(page, URL)["es_menor"])

    def test_locality_fallback_when_no_lugar(self):
        page = build_page(
            title="Se busca: Antonella — La Guaira",
            name="Antonella",
            description="Alguien busca a esta persona.",
            locality="La Guaira",
        )
        self.assertEqual(scraper.parse_report(page, URL)["ultima_ubicacion"], "La Guaira")

    def test_no_name_returns_none(self):
        page = build_page(title="Reporte", name="", include_person=False)
        self.assertIsNone(scraper.parse_report(page, URL))


class TestLoadSeen(unittest.TestCase):
    def test_reads_rows_and_skips_truncated(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "store.jsonl"
            p.write_text(
                '{"id": 111, "nombre": "A"}\n'
                '{"id": 222, "nombre": "B"}\n'
                '{"id": 333, "nombre": "C"  <-- linea truncada\n',
                encoding="utf-8",
            )
            rows = scraper.load_seen(str(p))
            self.assertEqual(set(rows.keys()), {"111", "222"})

    def test_includes_rejected_markers(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "store.jsonl"
            p.write_text(
                '{"id": 111, "nombre": "A"}\n'
                '{"id": 999, "rejected": true}\n',
                encoding="utf-8",
            )
            rows = scraper.load_seen(str(p))
            self.assertEqual(set(rows.keys()), {"111", "999"})
            self.assertTrue(rows["999"].get("rejected"))

    def test_missing_file_returns_empty(self):
        self.assertEqual(scraper.load_seen("/no/existe.jsonl"), {})


class TestOutputs(unittest.TestCase):
    def test_rows_for_output_excludes_rejected(self):
        seen = {
            "1": {"id": 1, "nombre": "A"},
            "2": {"id": 2, "rejected": True},
            "3": {"id": 3, "nombre": "C"},
        }
        rows = scraper.rows_for_output(seen)
        self.assertEqual(sorted(r["id"] for r in rows), [1, 3])

    def test_write_outputs_creates_json_and_csv(self):
        page = build_page(
            title="Se busca: Abel — La Guaira",
            name="Abel",
            description="Alguien busca a esta persona. Edad: 35. Lugar: La Guaira, Venezuela.",
        )
        rows = [scraper.parse_report(page, URL)]
        with tempfile.TemporaryDirectory() as d:
            base = str(Path(d) / "out")
            out_json, out_csv = scraper.write_outputs(rows, base)
            self.assertTrue(Path(out_json).exists() and Path(out_csv).exists())

            data = json.load(open(out_json, encoding="utf-8"))
            self.assertEqual(len(data), 1)
            self.assertEqual(list(data[0].keys()), SCHEMA_FIELDS)

            with open(out_csv, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, SCHEMA_FIELDS)
                self.assertEqual(len(list(reader)), 1)


if __name__ == "__main__":
    unittest.main()
