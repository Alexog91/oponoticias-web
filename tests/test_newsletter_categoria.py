"""tests/test_newsletter_categoria.py — filtro independiente comunidad + categoría.

Ejecuta:  python3 tests/test_newsletter_categoria.py

Por qué existe: un suscriptor pidió filtrar por categoría (administrativo). El
correo diario ahora aplica DOS filtros independientes (comunidad Y categoría);
cada uno es no-op si su preferencia está vacía. Estos tests fijan la matriz.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_API_KEY", "x")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import enviar_newsletter_ses as nl  # noqa: E402

CONV = [
    {"titulo": "A", "comunidad_autonoma": "Madrid",           "categoria": "Administración"},
    {"titulo": "B", "comunidad_autonoma": "Madrid",           "categoria": "Sanidad"},
    {"titulo": "C", "comunidad_autonoma": "Galicia",          "categoria": "Administración"},
    {"titulo": "D", "comunidad_autonoma": "Nacional/Estatal", "categoria": "Administración"},
    {"titulo": "E", "comunidad_autonoma": "Nacional/Estatal", "categoria": "Sanidad"},
    {"titulo": "F", "comunidad_autonoma": "Madrid",           "categoria": None},
]


def titulos(comunidad, categoria):
    return sorted(c["titulo"] for c in nl.convocatorias_para(comunidad, categoria, CONV))


casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731

# Sin filtros → todo (comportamiento actual de los 343 subs)
test("sin comunidad ni categoría → todo",
     lambda: titulos("", "") == ["A", "B", "C", "D", "E", "F"])
# Solo comunidad → su comunidad + estatales (comportamiento actual)
test("solo Madrid → Madrid + estatales",
     lambda: titulos("Madrid", "") == ["A", "B", "D", "E", "F"])
# Solo categoría → esa categoría de toda España (incl. estatales de esa categoría)
test("solo Administración → todas las de Administración",
     lambda: titulos("", "Administración") == ["A", "C", "D"])
# Comunidad + categoría → (comunidad O estatal) Y categoría
test("Madrid + Administración",
     lambda: titulos("Madrid", "Administración") == ["A", "D"])
test("Galicia + Sanidad → solo estatal de Sanidad",
     lambda: titulos("Galicia", "Sanidad") == ["E"])
# Convocatoria con categoría None NO llega a quien filtró por categoría
test("categoría None excluida al filtrar por categoría",
     lambda: "F" not in titulos("Madrid", "Administración"))
# Estatal como comunidad del suscriptor → ve todo (categoría vacía)
test("suscriptor estatal → todo",
     lambda: titulos("Nacional/Estatal", "") == ["A", "B", "C", "D", "E", "F"])


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try:
            ok = fn()
        except Exception as e:                       # noqa: BLE001
            ok, nombre = False, f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}")
        fallos += not ok
    print("─" * 58)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
