"""Verifica la clasificación del diff: nuevo / actualizado / sin_cambio /
duplicado_lote / rechazado. Hermético: el maestro es un dict en memoria."""

import unittest

from consolidator.lib import diff
from consolidator.lib.registros import content_hash, normalize_record


def rec(rid, nombre, estado="Desaparecido", fuente="f"):
    return {"id": rid, "nombre": nombre, "estado": estado, "fuente": fuente}


def index_for(*records):
    idx = {}
    for r in records:
        n = normalize_record(r)
        idx[(n["fuente"], n["id"])] = content_hash(n)
    return idx


class TestClassify(unittest.TestCase):
    def test_new(self):
        res = diff.classify([rec("1", "Ana")], {})
        self.assertEqual(len(res["nuevos"]), 1)
        self.assertEqual(res["sin_cambio"], 0)

    def test_unchanged(self):
        r = rec("1", "Ana")
        res = diff.classify([r], index_for(r))
        self.assertEqual(res["sin_cambio"], 1)
        self.assertEqual(len(res["nuevos"]), 0)
        self.assertEqual(len(res["actualizados"]), 0)

    def test_updated(self):
        viejo = rec("1", "Ana", estado="Desaparecido")
        nuevo = rec("1", "Ana", estado="Localizado")   # misma llave, contenido distinto
        res = diff.classify([nuevo], index_for(viejo))
        self.assertEqual(len(res["actualizados"]), 1)
        self.assertEqual(res["sin_cambio"], 0)

    def test_duplicate_in_batch(self):
        r = rec("1", "Ana")
        res = diff.classify([r, dict(r)], {})
        self.assertEqual(len(res["nuevos"]), 1)
        self.assertEqual(res["duplicados_lote"], 1)

    def test_rejected_without_name(self):
        res = diff.classify([{"id": "1", "fuente": "f"}], {})
        self.assertEqual(len(res["rechazados"]), 1)
        self.assertEqual(len(res["nuevos"]), 0)

    def test_processed_counts_all(self):
        res = diff.classify([rec("1", "Ana"), rec("2", "Bo"), {"id": "3"}], {})
        self.assertEqual(res["procesados"], 3)


if __name__ == "__main__":
    unittest.main()
