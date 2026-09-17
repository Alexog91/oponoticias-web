"""tests/test_ccaa_meta_ctr.py — la meta description de los hubs CCAA está
optimizada para CTR e intención de búsqueda ("empleo público [ciudad]",
"ayuntamiento…").

Ejecuta:  python3 tests/test_ccaa_meta_ctr.py

Auditoría GSC 17 sep 2026: "empleo publico ayuntamiento de madrid" rankea en
página 1 (pos 5,2, 128 impresiones) pero con CTR 1,6% — lo sirve el hub
/ccaa/madrid, que es sustancioso; el problema es el snippet. Estos tests fijan
que la meta case la intención (empleo público, ayuntamiento, ccaa, año),
aporte valor y quepa sin truncarse. Ver [[oponoticias-seo-web]].
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generar_ccaa as gc  # noqa: E402

AÑO = str(gc.AÑO)

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731

m_madrid = gc._meta_desc_ccaa("Madrid", 40)
m_larga = gc._meta_desc_ccaa("Comunidad Valenciana", 200)
m_vacia = gc._meta_desc_ccaa("Madrid", 0)

# ── Intención de búsqueda ─────────────────────────────────────────────────────
test("incluye 'empleo público' (la familia de queries que rankea)",
     lambda: "empleo público" in m_madrid.lower())
test("incluye 'ayuntamiento' (casa 'ayuntamiento de madrid')",
     lambda: "ayuntamiento" in m_madrid.lower())
test("incluye el nombre de la CCAA y el año",
     lambda: "Madrid" in m_madrid and AÑO in m_madrid)
test("incluye el número de convocatorias cuando n>0",
     lambda: "40" in m_madrid)
test("aporta valor/CTA (plazas/requisitos/plazos)",
     lambda: any(k in m_madrid.lower() for k in ("requisito", "plazo", "plazas")))

# ── Longitud (evitar truncado en el SERP) ─────────────────────────────────────
test("Madrid: meta ≤ 160 caracteres",
     lambda: len(m_madrid) <= 160)
test("nombre largo (Comunidad Valenciana): meta ≤ 165 caracteres",
     lambda: len(m_larga) <= 165)

# ── n=0 (hub sin convocatorias, noindex): sin '0 convocatorias' raro ──────────
test("n=0: no dice '0 convocatorias' y sigue siendo texto válido",
     lambda: "0 convocatorias" not in m_vacia and 40 < len(m_vacia) <= 165)


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
