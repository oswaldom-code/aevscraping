import os
import sys
import csv
import json
import uuid
import hashlib
import tempfile
import unittest
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scraper  # noqa: E402

MAX_BIGINT = 9223372036854775807
SCHEMA_FIELDS = [
    "id", "nombre", "cedula", "edad", "ultima_ubicacion",
    "telefono_contacto", "observaciones", "estado",
    "ubicacion_encontrado", "encontrado_por", "encontrado_por_cedula",
    "foto_url", "fecha_registro", "fecha_actualizacion", "es_menor", "fuente",
]


class TestMapId(unittest.TestCase):
    def test_valid_uuid_is_stable_and_in_range(self):
        u = "33625a9b-bdeb-4a48-a790-7fd1173c53b5"
        expected = uuid.UUID(u).int % MAX_BIGINT
        self.assertEqual(scraper.map_id(u), expected)
        self.assertEqual(scraper.map_id(u), scraper.map_id(u))  # determinista
        self.assertTrue(0 <= scraper.map_id(u) < MAX_BIGINT)

    def test_empty_returns_zero(self):
        self.assertEqual(scraper.map_id(None), 0)
        self.assertEqual(scraper.map_id(""), 0)

    def test_non_uuid_falls_back_to_sha256(self):
        val = "no-soy-uuid"
        expected = int(hashlib.sha256(val.encode("utf-8")).hexdigest(), 16) % MAX_BIGINT
        self.assertEqual(scraper.map_id(val), expected)


class TestMapTimestamp(unittest.TestCase):
    def test_iso_with_z_suffix(self):
        self.assertEqual(
            scraper.map_timestamp("2026-06-29T12:27:55.692Z"),
            "2026-06-29T12:27:55.692000+00:00",
        )

    def test_ms_epoch(self):
        # 1700000000000 ms = 2023-11-14T22:13:20 UTC
        self.assertEqual(
            scraper.map_timestamp(1700000000000),
            "2023-11-14T22:13:20+00:00",
        )

    def test_plain_iso_passthrough(self):
        self.assertEqual(
            scraper.map_timestamp("2026-06-29T02:39:27.725000+00:00"),
            "2026-06-29T02:39:27.725000+00:00",
        )

    def test_empty_returns_valid_now(self):
        out = scraper.map_timestamp(None)
        # Debe ser un ISO-8601 parseable
        datetime.fromisoformat(out)

    def test_garbage_returns_string(self):
        self.assertEqual(scraper.map_timestamp("no-es-fecha"), "no-es-fecha")


class TestMapEstado(unittest.TestCase):
    def test_seeking_info(self):
        self.assertEqual(scraper.map_estado("seeking_info"), "Desaparecido")

    def test_found_alive(self):
        self.assertEqual(scraper.map_estado("found_alive"), "Localizado")

    def test_found_dead(self):
        self.assertEqual(scraper.map_estado("found_dead"), "Fallecido")

    def test_none_defaults_to_desaparecido(self):
        self.assertEqual(scraper.map_estado(None), "Desaparecido")

    def test_unknown_defaults_to_desaparecido(self):
        self.assertEqual(scraper.map_estado("otra_cosa"), "Desaparecido")


class TestClean(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(scraper._clean(None))

    def test_strips_and_collapses_newlines(self):
        self.assertEqual(scraper._clean("  a\nb "), "a b")

    def test_empty_or_whitespace_returns_none(self):
        self.assertIsNone(scraper._clean(""))
        self.assertIsNone(scraper._clean("   "))


class TestMapRow(unittest.TestCase):
    def _base(self, **over):
        item = {
            "id": "33625a9b-bdeb-4a48-a790-7fd1173c53b5",
            "status": "seeking_info",
            "cedula_masked": None,
            "display_name": "Carlos Montilla",
            "municipio": None,
            "parroquia": "La Guaira · Catia La Mar · Edificio horizonte bello",
            "hospital_name": None,
            "photo_path": "https://www.desaparecidosvenezuela.com/api/personas/x/foto",
            "source_date": "2026-06-29T12:27:55.692Z",
        }
        item.update(over)
        return scraper.map_row(item)

    def test_has_exactly_the_16_schema_fields(self):
        row = self._base()
        self.assertEqual(list(row.keys()), SCHEMA_FIELDS)

    def test_fuente_is_tagged(self):
        self.assertEqual(self._base()["fuente"], "sosvenezuela2026")

    def test_adult_seeking_info_defaults(self):
        row = self._base()
        self.assertEqual(row["estado"], "Desaparecido")
        self.assertFalse(row["es_menor"])
        self.assertEqual(row["cedula"], "N/D")
        self.assertIsNone(row["edad"])
        self.assertIsNone(row["telefono_contacto"])
        self.assertEqual(row["foto_url"], "https://www.desaparecidosvenezuela.com/api/personas/x/foto")
        self.assertEqual(row["fecha_registro"], row["fecha_actualizacion"])

    def test_minor_is_inferred_from_display_name(self):
        row = self._base(display_name="Menor reportado")
        self.assertTrue(row["es_menor"])

    def test_minor_inference_is_case_insensitive(self):
        self.assertTrue(self._base(display_name="  MENOR REPORTADO ")["es_menor"])

    def test_missing_name_defaults_to_desconocido(self):
        self.assertEqual(self._base(display_name=None)["nombre"], "Desconocido")

    def test_cedula_masked_used_when_present(self):
        self.assertEqual(self._base(cedula_masked="V-123****")["cedula"], "V-123****")

    def test_ultima_ubicacion_prefers_parroquia(self):
        self.assertEqual(
            self._base()["ultima_ubicacion"],
            "La Guaira · Catia La Mar · Edificio horizonte bello",
        )

    def test_ultima_ubicacion_falls_back_to_municipio(self):
        row = self._base(parroquia=None, municipio="Vargas")
        self.assertEqual(row["ultima_ubicacion"], "Vargas")

    def test_desaparecido_with_hospital_goes_to_observaciones(self):
        row = self._base(hospital_name="Hospital Vargas")
        self.assertEqual(row["observaciones"], "Hospital: Hospital Vargas")
        self.assertIsNone(row["ubicacion_encontrado"])

    def test_localizado_with_hospital_goes_to_ubicacion_encontrado(self):
        row = self._base(status="found_alive", hospital_name="Hospital Vargas")
        self.assertEqual(row["estado"], "Localizado")
        self.assertEqual(row["ubicacion_encontrado"], "Hospital Vargas")
        self.assertIsNone(row["observaciones"])

    def test_id_is_mapped_to_bigint(self):
        row = self._base()
        self.assertEqual(row["id"], uuid.UUID("33625a9b-bdeb-4a48-a790-7fd1173c53b5").int % MAX_BIGINT)


class TestWriteOutputs(unittest.TestCase):
    def _rows(self):
        return [
            scraper.map_row({"id": "33625a9b-bdeb-4a48-a790-7fd1173c53b5",
                             "status": "seeking_info", "display_name": "Carlos Montilla",
                             "parroquia": "La Guaira", "source_date": "2026-06-29T12:00:00Z"}),
            scraper.map_row({"id": "64491c1b-b189-49ca-8922-e0ddbb107e24",
                             "status": "found_alive", "display_name": "Ana",
                             "parroquia": "Vargas", "source_date": "2026-06-29T13:00:00Z"}),
        ]

    def test_creates_json_and_csv_with_schema(self):
        with tempfile.TemporaryDirectory() as d:
            base = str(Path(d) / "out")
            out_json, out_csv = scraper.write_outputs(self._rows(), base)
            self.assertTrue(Path(out_json).exists() and Path(out_csv).exists())

            data = json.load(open(out_json, encoding="utf-8"))
            self.assertEqual(len(data), 2)
            self.assertEqual(list(data[0].keys()), SCHEMA_FIELDS)

            with open(out_csv, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, SCHEMA_FIELDS)
                self.assertEqual(len(list(reader)), 2)


if __name__ == "__main__":
    unittest.main()
