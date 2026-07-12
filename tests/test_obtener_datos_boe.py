#!/usr/bin/env python3
"""Test de _parsear_datos_boe (leer_boe.py) contra fixtures XML reales del BOE.

Sin red: usa tests/fixtures/*.xml. Ejecuta:  python3 tests/test_obtener_datos_boe.py

Cubre el bug por el que convocatorias con el nº de plazas TABULADO o enumerado en
un ANEXO salían como "VARIAS PLAZAS": el extractor solo leía los <p> y nunca veía
el número. Antes del fix, 15152 (89 plazas en tabla) y 15172 (6 áreas en anexo)
fallaban; 13237 (nota con "9 plazas") ya pasaba y sirve de guarda de no-regresión.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import leer_boe  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _parse(ref):
    root = ET.parse(FIXTURES / f"{ref}.xml").getroot()
    return leer_boe._parsear_datos_boe(root)


def test_tabla_total_visible():
    """15152: el total (89) y la fila 'Total' de la tabla-anexo llegan al texto."""
    notas, texto = _parse("BOE-A-2026-15152")
    assert "89" in texto, "El total de la tabla (89) debe aparecer en el texto"
    assert "Total" in texto, "La fila 'Total' de la tabla debe extraerse"


def test_anexo_plazas_enumeradas():
    """15172: las 6 áreas del Anexo I (bajo 'Cuerpo:') se cuentan como plazas."""
    notas, texto = _parse("BOE-A-2026-15172")
    assert "6 plazas enumeradas" in texto, "Debe contar las plazas del anexo"
    assert "Ingeniería Telemática" in texto, "Las áreas del anexo deben aparecer"


def test_nota_con_numero_no_regresion():
    """13237: la nota con 'Policía Local 9 plazas' se sigue extrayendo igual."""
    notas, texto = _parse("BOE-A-2026-13237")
    assert "9 plazas" in notas, "La nota con el nº de plazas no debe perderse"


def test_anexo_de_reglas_no_cuenta_como_plazas():
    """15055 (Policía): su anexo enumera reglas de pruebas físicas, NO plazas.
    El gate 'Cuerpo:' debe evitar inyectar un conteo espurio (186) que compita
    con la nota real (2.704 plazas)."""
    notas, texto = _parse("BOE-A-2026-15055")
    assert "2.704 plazas" in notas, "La nota con el total debe estar presente"
    assert "plazas enumeradas en el anexo" not in texto, \
        "No debe contar las reglas del anexo como plazas"


def test_documento_sin_texto_no_rompe():
    """Robustez: un árbol sin <texto> devuelve notas y texto vacío, sin excepción."""
    root = ET.fromstring("<documento><analisis><notas>"
                         "<nota>Convocatoria. 10 plazas</nota></notas></analisis></documento>")
    notas, texto = leer_boe._parsear_datos_boe(root)
    assert "10 plazas" in notas
    assert texto == ""


def main():
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✓ {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"✗ {nombre}: {e}")
            except Exception as e:
                fallos += 1
                print(f"✗ {nombre}: ERROR {type(e).__name__}: {e}")
    print("─" * 50)
    print("TODO OK" if not fallos else f"{fallos} test(s) fallaron")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
