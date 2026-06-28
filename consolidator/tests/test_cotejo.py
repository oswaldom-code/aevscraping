"""Verifica el cotejo cross-source: agrupación por cédula/nombre, cross-source
only, y la alerta crítica buscado/resuelto."""

import unittest

from consolidator.lib import cotejo


def rec(fuente, rid, nombre, estado="Desaparecido", cedula=""):
    return {"fuente": fuente, "id": rid, "nombre": nombre, "estado": estado,
            "cedula": cedula, "edad": None, "ultima_ubicacion": "",
            "telefono_contacto": "", "foto_url": ""}


class TestTokens(unittest.TestCase):
    def test_normalizes_and_drops_stopwords(self):
        self.assertEqual(cotejo.significant_tokens("José de la Cruz Pérez"),
                         ["JOSE", "CRUZ", "PEREZ"])

    def test_valid_and_invalid_cedula(self):
        self.assertEqual(cotejo.cedula_digits("V-16248096"), "16248096")
        self.assertIsNone(cotejo.cedula_digits("N/D"))
        self.assertIsNone(cotejo.cedula_digits("No registrado"))

    def test_status_class(self):
        self.assertEqual(cotejo.status_class("Desaparecido"), "buscando")
        self.assertEqual(cotejo.status_class("Localizado"), "resuelto")
        self.assertEqual(cotejo.status_class("Hospitalizado"), "resuelto")


class TestMatches(unittest.TestCase):
    def test_match_by_reordered_name_and_accents(self):
        recs = [rec("A", "1", "José Pérez"), rec("B", "2", "PEREZ JOSE")]
        g = cotejo.find_matches(recs)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["confianza"], "nombre")
        self.assertEqual(g[0]["fuentes"], ["A", "B"])

    def test_concatenated_source(self):
        recs = [rec("terremoto", "1", "Ana Gomez"),
                rec("redayuda", "2", "Ana Gomez")]
        g = cotejo.find_matches(recs)
        self.assertEqual(g[0]["fuente"], "redayuda/terremoto")  # ordenado, con "/"

    def test_match_by_cedula_is_strong(self):
        recs = [rec("A", "1", "Ana Gomez", cedula="V-16248096"),
                rec("B", "2", "Otro Nombre", cedula="16248096")]
        g = cotejo.find_matches(recs)
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["confianza"], "fuerte")

    def test_critical_alert_searched_vs_found(self):
        recs = [rec("A", "1", "Ana Gomez", "Desaparecido"),
                rec("B", "2", "Ana Gomez", "Localizado")]
        g = cotejo.find_matches(recs)
        self.assertTrue(g[0]["alerta_critica"])

    def test_same_source_is_not_a_match(self):
        recs = [rec("A", "1", "Ana Gomez"), rec("A", "2", "Ana Gomez")]
        self.assertEqual(cotejo.find_matches(recs), [])

    def test_distinct_people_do_not_group(self):
        recs = [rec("A", "1", "Ana Gomez"), rec("B", "2", "Luis Parra")]
        self.assertEqual(cotejo.find_matches(recs), [])

    def test_no_alert_if_both_searching(self):
        recs = [rec("A", "1", "Ana Gomez", "Desaparecido"),
                rec("B", "2", "Ana Gomez", "Desaparecido")]
        g = cotejo.find_matches(recs)
        self.assertFalse(g[0]["alerta_critica"])


if __name__ == "__main__":
    unittest.main()
