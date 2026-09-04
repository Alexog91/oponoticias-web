"""tests/test_puesto_fallback.py — el fallback saca el PUESTO del texto oficial
del BOE cuando el título no lo dice (evita el genérico 'CONVOCATORIA').

Ejecuta:  python3 tests/test_puesto_fallback.py

Contexto (4 sep 2026): ~30 convocatorias municipales salían como
'N PLAZAS - CONVOCATORIA - LUGAR' porque el TÍTULO no nombra el puesto y el
fallback lo derivaba SOLO del título. Pero el puesto SÍ está en los datos
oficiales del BOE (obtener_datos_boe → notas/texto), con el patrón típico
'N plaza(s) de <PUESTO>'. Estos tests fijan que el fallback lo aproveche.
Ver [[oponoticias-arquitectura-repos]] (resiliencia sin saldo / calidad resumen).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import leer_boe as lb  # noqa: E402

# ── Datos REALES del BOE para convocatorias cuyo título NO dice el puesto ──────
OLMEDA_T = "Resolución de 27 de agosto de 2026, del Ayuntamiento de Olmeda de las Fuentes (Madrid)"
OLMEDA_NOTAS = ("Bases de la convocatoria en: «Boletín Oficial de la Comunidad de Madrid» "
                "núm. 203, de 26 de agosto de 2026 · Turno libre: Operario de Mantenimiento.")
OLMEDA_TEXTO = ("Una plaza de Operario de Mantenimiento de la plantilla de personal laboral "
                "fijo, por el sistema de concurso-oposición, en turno libre.")

FUENGI_T = "Resolución de 27 de agosto de 2026, del Ayuntamiento de Fuengirola (Málaga)"
FUENGI_NOTAS = ("Bases de la convocatoria en: «Boletín Oficial de la Provincia de Málaga» "
                "núm. 164, de 26 de agosto de 2026 · Policía Local: Turno libre 12 plazas.")
FUENGI_TEXTO = ("Doce plazas de Policías Locales, pertenecientes a la escala de Administración "
                "Especial, por el sistema de oposición, en turno libre.")

# Rectificación: el BOE NO trae el puesto → debe quedarse genérico (correcto).
SOCU_T = "Resolución de 28 de agosto de 2026, del Ayuntamiento de Socuéllamos (Ciudad Real)"
SOCU_NOTAS = ("Rectificación de las bases de la convocatoria en: «Boletín Oficial de la "
              "Provincia de Ciudad Real» núm. 165, de 28 de agosto de 2026")
SOCU_TEXTO = ""


def _puesto(resumen):
    """El PUESTO es el segmento central de 'PLAZAS - PUESTO - LUGAR'."""
    partes = resumen.split(" - ")
    return partes[1] if len(partes) >= 3 else resumen


casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731

# ── El fallback saca el puesto del BOE cuando el título no lo dice ─────────────
test("Olmeda: puesto 'OPERARIO DE MANTENIMIENTO' desde el texto del BOE",
     lambda: _puesto(lb._resumen_fallback(OLMEDA_T, "", OLMEDA_NOTAS, OLMEDA_TEXTO))
             == "OPERARIO DE MANTENIMIENTO")
test("Fuengirola: puesto 'POLICÍAS LOCALES' desde el texto del BOE",
     lambda: _puesto(lb._resumen_fallback(FUENGI_T, "", FUENGI_NOTAS, FUENGI_TEXTO))
             == "POLICÍAS LOCALES")
test("Socuéllamos (rectificación, sin puesto): se queda en CONVOCATORIA",
     lambda: _puesto(lb._resumen_fallback(SOCU_T, "", SOCU_NOTAS, SOCU_TEXTO)) == "CONVOCATORIA")

# ── Regresiones: no romper lo que ya funcionaba ───────────────────────────────
test("regresión: título con 'Policía' sigue usando el puesto del título",
     lambda: "POLIC" in _puesto(lb._resumen_fallback(
         "Convocatoria de Policía Local del Ayuntamiento de X (Cádiz)", "", "", "")))
test("regresión: 'personal laboral' se mantiene",
     lambda: _puesto(lb._resumen_fallback(
         "Convocatoria del Ayuntamiento de X (Madrid)", "una plaza de personal laboral", "", ""))
             == "PERSONAL LABORAL")
test("regresión: número de plazas del texto del BOE se conserva (12 PLAZAS)",
     lambda: lb._resumen_fallback(FUENGI_T, "", FUENGI_NOTAS, FUENGI_TEXTO).startswith("12 PLAZAS - "))


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
