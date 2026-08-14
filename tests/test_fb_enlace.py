"""tests/test_fb_enlace.py — el enlace al artículo SIEMPRE debe ir en el post de FB.

Ejecuta:  python3 tests/test_fb_enlace.py

Por qué existe: antes el enlace se ponía como PRIMER COMENTARIO (mejor alcance
orgánico en FB), pero el Page token no tiene permiso pages_manage_engagement
para comentar → 403 → el enlace no aparecía en NINGÚN sitio y el post de blog
se quedaba sin forma de llegar al artículo. Ahora el enlace va en el cuerpo.

Se prueba solo la construcción del cuerpo (sin red).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("FB_PAGE_TOKEN", "x")
os.environ.setdefault("FB_PAGE_ID", "x")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import publicar_meta as pm  # noqa: E402

MSG = "📚 Título del artículo\n\nExtracto del contenido…\n\n#oposiciones"
LINK = "https://oponoticias.com/blog/mi-articulo.html"

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


test("🔴 el enlace aparece en el cuerpo", lambda: LINK in pm._cuerpo_con_enlace(MSG, LINK))

test("conserva el mensaje original", lambda: (
    "Título del artículo" in pm._cuerpo_con_enlace(MSG, LINK)
    and "#oposiciones" in pm._cuerpo_con_enlace(MSG, LINK)
))

test("no duplica el enlace si ya venía en el mensaje", lambda: (
    pm._cuerpo_con_enlace(MSG + "\n\n" + LINK, LINK).count(LINK) == 1
))

test("sin enlace, devuelve el mensaje tal cual", lambda: (
    pm._cuerpo_con_enlace(MSG, "") == MSG and pm._cuerpo_con_enlace(MSG, None) == MSG
))

test("mensaje vacío no revienta", lambda: (
    isinstance(pm._cuerpo_con_enlace("", LINK), str) and LINK in pm._cuerpo_con_enlace("", LINK)
))


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
