"""
cotejo.py

Detecta la MISMA persona reportada en fuentes distintas (cross-source). Es una
capa de análisis de SOLO LECTURA sobre el maestro: no fusiona ni modifica nada,
emite grupos de coincidencia para revisión humana.

Agrupa con union-find por dos señales (O(n), sin comparar todos los pares):
  - cédula válida compartida          -> confianza "fuerte"
  - mismo conjunto de palabras del
    nombre (normalizado, sin orden)   -> confianza "nombre"

Marca alerta_critica cuando, dentro de un grupo, alguien sigue "buscando" y otra
fuente lo da por "resuelto" (localizado/encontrado/hospitalizado/fallecido):
el caso "buscado en A, localizado en B".
"""

import re
import sqlite3
import unicodedata

STOPWORDS = {"DE", "LA", "DEL", "LOS", "LAS", "Y", "EL", "SAN", "SANTA"}

# Campos del registro que se incluyen en cada coincidencia (para revisión).
OUT_FIELDS = ("fuente", "id", "nombre", "cedula", "edad", "estado",
              "ultima_ubicacion", "telefono_contacto", "foto_url")


def significant_tokens(nombre):
    """Palabras significativas del nombre: sin acentos, mayúsculas, solo letras,
    sin stopwords, de >2 caracteres."""
    if not nombre:
        return []
    s = unicodedata.normalize("NFD", str(nombre))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")  # quita acentos
    s = re.sub(r"[^A-Za-z ]", " ", s).upper()
    return [w for w in s.split() if len(w) > 2 and w not in STOPWORDS]


def cedula_digits(cedula):
    """Dígitos de una cédula si es válida (≥6 dígitos), o None."""
    if not cedula:
        return None
    digits = re.sub(r"\D", "", str(cedula))
    return digits if len(digits) >= 6 else None


def status_class(estado):
    """'buscando' | 'resuelto' | 'otro' a partir del texto de estado."""
    s = str(estado or "").lower()
    if any(k in s for k in ("localiz", "encontr", "salvo", "hospital", "fallec", "muert", "found")):
        return "resuelto"
    if any(k in s for k in ("desaparec", "busca", "activ")):
        return "buscando"
    return "otro"


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def find_matches(records):
    """Devuelve los grupos cross-source. Cada grupo:
    {confianza, alerta_critica, fuentes, n, registros}."""
    recs = list(records)
    uf = _UF(len(recs))
    ced_index, nom_index = {}, {}

    for i, r in enumerate(recs):
        ced = cedula_digits(r.get("cedula"))
        if ced:
            ced_index.setdefault(ced, []).append(i)
        toks = significant_tokens(r.get("nombre"))
        if len(toks) >= 2:
            nom_index.setdefault(" ".join(sorted(toks)), []).append(i)

    # Unir por cédula y por nombre.
    for idxs in ced_index.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)
    for idxs in nom_index.values():
        for j in idxs[1:]:
            uf.union(idxs[0], j)

    # Tras TODAS las uniones: un componente es "fuerte" si tiene una cédula
    # compartida (raíz final calculada ahora, no durante la unión).
    fuerte_roots = {uf.find(idxs[0]) for idxs in ced_index.values() if len(idxs) >= 2}

    # Reagrupar por componente.
    comps = {}
    for i in range(len(recs)):
        comps.setdefault(uf.find(i), []).append(i)

    grupos = []
    for root, idxs in comps.items():
        if len(idxs) < 2:
            continue
        fuentes = {recs[i].get("fuente") for i in idxs}
        if len(fuentes) < 2:                    # solo cross-source
            continue
        clases = {status_class(recs[i].get("estado")) for i in idxs}
        fuentes_ord = sorted(f for f in fuentes if f)
        grupos.append({
            "confianza": "fuerte" if uf.find(root) in fuerte_roots else "nombre",
            "alerta_critica": "buscando" in clases and "resuelto" in clases,
            # fuentes concatenadas: "A/B" — esta persona aparece en varias fuentes.
            "fuente": "/".join(fuentes_ord),
            "fuentes": fuentes_ord,
            "n": len(idxs),
            "registros": [{k: recs[i].get(k) for k in OUT_FIELDS} for i in idxs],
        })

    # Alertas primero, luego más fuentes, luego confianza.
    grupos.sort(key=lambda g: (not g["alerta_critica"], -len(g["fuentes"]),
                               g["confianza"] != "fuerte"))
    return grupos


def load_master_records(db):
    """Carga los registros del maestro (solo los campos que usa el cotejo)."""
    con = sqlite3.connect(str(db))
    cols = ", ".join(OUT_FIELDS)
    rows = con.execute(f"SELECT {cols} FROM registros").fetchall()
    con.close()
    return [dict(zip(OUT_FIELDS, r)) for r in rows]


def summarize(grupos):
    """Conteos para el reporte: total, alertas críticas y por confianza."""
    alertas = sum(1 for g in grupos if g["alerta_critica"])
    fuertes = sum(1 for g in grupos if g["confianza"] == "fuerte")
    return {
        "grupos_coincidencia": len(grupos),
        "alertas_criticas": alertas,
        "por_confianza": {"fuerte": fuertes, "nombre": len(grupos) - fuertes},
    }
