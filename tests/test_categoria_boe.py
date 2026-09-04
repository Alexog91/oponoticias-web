"""tests/test_categoria_boe.py — categoría del newsletter por el PUESTO real, no
solo el título; y cajón neutro "Otras" para lo no clasificable.

Ejecuta:  python3 tests/test_categoria_boe.py

Contexto (4 sep 2026): un suscriptor (Moisés) que filtra por "Administración"
recibía albañiles, jueces, etc. Causa: (1) el título municipal no nombra el
puesto y el clasificador solo miraba el título → cajón por defecto
"Administración"; (2) faltaban palabras clave (p. ej. "JUEZ" no existía). Fixes:
- extraer_cuerpo reconoce más puestos (JUEZ/FISCAL→Justicia, ALBAÑIL/OPERARIO→Oficios, BOMBERO→Seguridad).
- clasificar_categoria: si el título es mudo, clasifica por el PUESTO del resumen
  (que viene del texto oficial del BOE); si nada casa → "Otras" (no filtrable).
Ver [[oponoticias-arquitectura-repos]].
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import leer_boe as lb  # noqa: E402


def _cat(titulo):
    return lb.extraer_cuerpo(titulo)[1]


casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731

# ── extraer_cuerpo: nuevas palabras clave ─────────────────────────────────────
test("extraer_cuerpo: JUEZ → Justicia", lambda: _cat("Convocatoria para Juez de Paz") == "Justicia")
test("extraer_cuerpo: FISCAL → Justicia", lambda: _cat("plaza de Fiscal") == "Justicia")
test("extraer_cuerpo: ALBAÑIL → Oficios", lambda: _cat("una plaza de Albañil") == "Oficios")
test("extraer_cuerpo: OPERARIO DE MANTENIMIENTO → Oficios",
     lambda: _cat("Operario de Mantenimiento") == "Oficios")
test("extraer_cuerpo: PEÓN → Oficios", lambda: _cat("dos plazas de Peón de servicios") == "Oficios")
test("extraer_cuerpo: BOMBERO → Seguridad", lambda: _cat("plaza de Bombero") == "Seguridad")
# Regresiones de extraer_cuerpo
test("extraer_cuerpo: ADMINISTRATIVO sigue Administración",
     lambda: _cat("Auxiliar Administrativo") == "Administración")
test("extraer_cuerpo: POLICÍA sigue Seguridad", lambda: _cat("Policía Local") == "Seguridad")
test("extraer_cuerpo: TÉCNICO de mantenimiento gana a Oficios (Técnica)",
     lambda: _cat("Técnico de Mantenimiento") == "Técnica")

# ── clasificar_categoria: título mudo → clasifica por el PUESTO del resumen ────
MUTO = "Resolución de 27 de agosto de 2026, del Ayuntamiento de X (Madrid)"
test("mudo + PUESTO Policías Locales → Seguridad",
     lambda: lb.clasificar_categoria(MUTO, "12 PLAZAS - POLICÍAS LOCALES - MÁLAGA") == "Seguridad")
test("mudo + PUESTO Juez → Justicia",
     lambda: lb.clasificar_categoria(MUTO, "1 PLAZA - JUEZ - MADRID") == "Justicia")
test("mudo + PUESTO Albañil → Oficios",
     lambda: lb.clasificar_categoria(MUTO, "2 PLAZAS - ALBAÑIL - CÁDIZ") == "Oficios")
test("mudo + PUESTO Auxiliar Administrativo → Administración (se recupera)",
     lambda: lb.clasificar_categoria(MUTO, "1 PLAZA - AUXILIAR ADMINISTRATIVO - MADRID") == "Administración")
test("mudo + PUESTO genérico CONVOCATORIA → Otras (no contamina Administración)",
     lambda: lb.clasificar_categoria(MUTO, "1 PLAZA - CONVOCATORIA - MADRID") == "Otras")
test("mudo + sin resumen → Otras",
     lambda: lb.clasificar_categoria(MUTO, "") == "Otras")
# El título manda: si el título ya dice el puesto, no se reclasifica por el resumen
test("título con Policía manda aunque el resumen diga otra cosa",
     lambda: lb.clasificar_categoria("Convocatoria de Policía Local (Cádiz)",
                                     "1 PLAZA - CONVOCATORIA - CÁDIZ") == "Seguridad")


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try:
            ok = fn()
        except Exception as e:                       # noqa: BLE001
            ok, nombre = False, f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}")
        fallos += not ok
    print("─" * 62)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
