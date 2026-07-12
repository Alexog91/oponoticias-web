#!/usr/bin/env python3
"""Test de boe_utils.extraer_organismo con títulos reales del BOE.

Ejecuta:  python3 tests/test_extraer_organismo.py

Cubre el bug por el que las órdenes/resoluciones ministeriales numeradas
("Orden PJC/705/2026, de 9 de julio, por la que...") mostraban la FECHA de la
disposición como organismo, en vez del convocante. También verifica que los
títulos que ya funcionaban (Ayuntamientos, Universidades, "Resolución de FECHA,
de la ORG") no se rompen.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from boe_utils import extraer_organismo  # noqa: E402

# (título real del BOE, organismo esperado)
CASOS = [
    # BUG variante A — código + fecha, SIN organismo en el título → AGE.
    ("Orden PJC/705/2026, de 9 de julio, por la que se convoca proceso selectivo "
     "para ingreso, por el sistema de general de acceso libre y promoción interna, "
     "como personal laboral fijo en los grupos profesionales M3, M2 y M1.",
     "Administración General del Estado"),
    # BUG variante B — código + fecha + organismo pegados → solo el organismo.
    ("Resolución 430/38317/2026, de 2 de julio, de la Subsecretaría, por la que se "
     "modifica la distribución por programas de las plazas.",
     "Subsecretaría"),
    # NO regresión — "Resolución de FECHA de AÑO, de la ORG" (fecha sin coma previa).
    ("Resolución de 7 de julio de 2026, de la Dirección General de la Policía, por "
     "la que se convoca oposición libre para cubrir plazas de policía.",
     "Dirección General de la Policía"),
    # NO regresión — Ayuntamiento.
    ("Resolución de 30 de junio de 2026, del Ayuntamiento de Lugo, referente a la "
     "convocatoria para proveer varias plazas.",
     "Ayuntamiento de Lugo"),
    # NO regresión — Universidad.
    ("Resolución de 1 de julio de 2026, de la Universidad de Alcalá, por la que se "
     "convoca concurso de acceso.",
     "Universidad de Alcalá"),
]


def _norm(s):
    return " ".join(s.split()).lower()


def main():
    fallos = 0
    for titulo, esperado in CASOS:
        got = extraer_organismo(titulo)
        ok = _norm(got) == _norm(esperado)
        # el organismo NUNCA debe empezar por una fecha
        empieza_fecha = got.strip()[:2].isdigit() and " de " in got[:15].lower()
        if not ok or empieza_fecha:
            fallos += 1
            print(f"✗ {titulo[:45]}…\n    esperado: {esperado!r}\n    obtenido: {got!r}")
        else:
            print(f"✓ {got}")
    print("─" * 55)
    print("TODO OK" if not fallos else f"{fallos} test(s) fallaron")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
