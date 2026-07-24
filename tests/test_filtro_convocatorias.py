"""tests/test_filtro_convocatorias.py — qué títulos del BOE son convocatorias.

Ejecuta:  python3 tests/test_filtro_convocatorias.py

Por qué existe: el filtro buscaba 5 palabras EXACTAS en el título
('oposición', 'oposiciones', 'selectivo', 'convocatoria', 'plazas'), así que
se le escapaba ~1 convocatoria real al día por pura concordancia gramatical —
el BOE escribe «pruebas selectivas» (femenino), «plaza de» (singular) y «se
convoca» (verbo), y ninguna de las tres coincide. Medido sobre 39 días reales
de BOE (1.415 publicaciones): 39 convocatorias perdidas en silencio.

Todos los títulos de aquí son REALES, sacados del BOE de junio-julio de 2026.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from boe_utils import es_convocatoria  # noqa: E402

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


# ── Lo que YA funcionaba: no romperlo ───────────────────────────────────────
test("proceso selectivo (lo que se publicó hoy)", lambda: es_convocatoria(
    "Resolución de 17 de julio de 2026, de la Universidad de Cádiz, por la que se "
    "modifica la de 8 de julio de 2026, por la que se convoca proceso selectivo para "
    "la provisión de plaza de personal laboral de la categoría de Titulado Superior."
) is True)

test("oposiciones en plural", lambda: es_convocatoria(
    "Resolución por la que se convocan oposiciones al Cuerpo General Administrativo."
) is True)

test("«plazas» en plural", lambda: es_convocatoria(
    "Resolución por la que se ofertan 2.704 plazas de Policía Nacional."
) is True)


# ── EL FALLO: concordancia gramatical ───────────────────────────────────────
test("🔴 «pruebas selectivas» — femenino plural (18 casos reales)", lambda: es_convocatoria(
    "Resolución de 10 de julio de 2026, de la Universitat de València, por la que se "
    "convocan pruebas selectivas de acceso al grupo A (subgrupo A1), sector "
    "administración especial, técnico superior de informática."
) is True)

test("🔴 «plaza» singular (18 casos reales)", lambda: es_convocatoria(
    "Resolución de 30 de junio de 2026, de la Universidad de Almería, por la que se "
    "convocan pruebas selectivas para ingreso en la Escala Técnica de Administración, "
    "plaza de Técnico de Gestión."
) is True)

test("🔴 «se convoca» verbo, sin la palabra «convocatoria»", lambda: es_convocatoria(
    "Orden TDF/684/2026, de 3 de julio, por la que se convocan pruebas selectivas para "
    "el acceso, por el sistema de promoción interna, al Cuerpo de Técnicos Auxiliares."
) is True)


# ── Movimientos internos: NO son oposiciones de acceso ──────────────────────
test("libre designación = nombramiento a dedo entre funcionarios", lambda: es_convocatoria(
    "Resolución de 20 de julio de 2026, de la Subsecretaría, por la que se convoca la "
    "provisión de puesto de trabajo por el sistema de libre designación."
) is False)

test("concurso específico de provisión (interno)", lambda: es_convocatoria(
    "Resolución de 10 de julio de 2026, de la Dirección General de Justicia, por la que "
    "se convoca concurso específico para la provisión de puesto de trabajo."
) is False)

test("corrección de errores de una libre designación", lambda: es_convocatoria(
    "Resolución de 20 de julio de 2026, de la Subsecretaría, por la que se corrigen "
    "errores en la de 13 de julio de 2026, por la que se convoca la provisión de puesto "
    "de trabajo por el sistema de libre designación."
) is False)


# ── Cátedras y docentes universitarios: nicho aparte (decisión del usuario) ──
test("cuerpos docentes universitarios (cátedras) queda fuera", lambda: es_convocatoria(
    "Resolución de 30 de junio de 2026, de la Universidad de León, por la que se convoca "
    "concurso de acceso a plaza de cuerpos docentes universitarios."
) is False)

test("plaza vinculada (docente-sanitaria) queda fuera", lambda: es_convocatoria(
    "Resolución de 8 de julio de 2026, de la Universidad de Málaga, por la que se convoca "
    "concurso de acceso a plaza vinculada de cuerpos docentes universitarios."
) is False)

test("plaza de Profesorado Contratado Doctor queda fuera", lambda: es_convocatoria(
    "Resolución de 24 de junio de 2026, de la UNED, por la que se convoca concurso de "
    "acceso a plaza de Profesorado Contratado Doctor."
) is False)

test("PERO el PAS universitario SÍ entra (no es docente)", lambda: es_convocatoria(
    "Resolución de 6 de julio de 2026, de la Universidad Politécnica de Cartagena, por la "
    "que se convocan pruebas selectivas para ingreso, por el sistema general de acceso "
    "libre, en la Escala de Gestión Administrativa."
) is True)


# ── Ruido evidente ──────────────────────────────────────────────────────────
test("el «Sumario» (índice del BOE) no es una convocatoria", lambda:
     es_convocatoria("Sumario") is False)

test("título vacío no revienta", lambda: es_convocatoria("") is False)

test("None no revienta", lambda: es_convocatoria(None) is False)


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try:
            ok = fn()
        except Exception as e:                       # noqa: BLE001
            ok, nombre = False, f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}")
        fallos += not ok
    print("─" * 66)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
