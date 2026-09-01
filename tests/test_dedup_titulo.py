"""tests/test_dedup_titulo.py — dedupe y flag de Telegram por TÍTULO, no por enlace.

Ejecuta:  python3 tests/test_dedup_titulo.py

Por qué existe (bug del 1 sep 2026): la tabla `convocatorias` tiene la clave
única en el TÍTULO (UNIQUE(titulo)), pero el pipeline deduplicaba y marcaba
"ya enviado a Telegram" por ENLACE. El enlace se construye determinista desde
ref_boe (`txt.php?id={ref_boe}`), así que cuando el BOE republica el MISMO
título con OTRO ref_boe, el enlace cambia → las comprobaciones por enlace no
casan → la convocatoria se reanaliza con Claude y se REENVÍA a Telegram en cada
ejecución (se detectó al saltar dos crons seguidos: las mismas 7 llegaron dos
veces). Estos tests fijan que dedupe/flag van por `titulo` (la clave estable),
sin tocar la red (monkeypatch de urllib.request.urlopen).
"""
import os
import sys
import json
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_API_KEY", "k")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import leer_boe as lb  # noqa: E402

lb.SUPABASE_URL = "http://x"
lb.SUPABASE_API_KEY = "k"

# Un título con espacios, comas y acentos: obliga a que el filtro se codifique bien.
TITULO = ("Resolución de 24 de agosto de 2026, de la Diputación Provincial de "
          "Cádiz, referente a la convocatoria para proveer varias plazas.")


class _Resp:
    """Respuesta HTTP falsa usable como context manager (with ... as r)."""
    def __init__(self, body):
        self._b = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


def _llamar(fn, body):
    """Ejecuta fn() con urllib.request.urlopen sustituido por uno que captura la
    petición (url/método/datos) y responde `body`. Restaura el original al salir."""
    capt = {}

    def fake(req, timeout=None):
        capt["url"] = req.full_url
        capt["method"] = req.get_method()
        capt["data"] = req.data
        return _Resp(body)

    orig = lb.urllib.request.urlopen
    lb.urllib.request.urlopen = fake
    try:
        res = fn()
    finally:
        lb.urllib.request.urlopen = orig
    return res, capt


casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


# ── telegram_ya_enviado: consulta por titulo ────────────────────────────────
def _tye(body):
    return _llamar(lambda: lb.telegram_ya_enviado(TITULO), body)

test("telegram_ya_enviado consulta por titulo, no por enlace",
     lambda: (lambda r: "titulo=eq." in r[1]["url"] and "enlace=" not in r[1]["url"])
             (_tye(b'[{"telegram_enviado": true}]')))
test("telegram_ya_enviado: True si el titulo está marcado",
     lambda: _tye(b'[{"telegram_enviado": true}]')[0] is True)
test("telegram_ya_enviado: False si no hay fila para ese titulo",
     lambda: _tye(b'[]')[0] is False)


# ── marcar_telegram_enviado: PATCH por titulo ───────────────────────────────
def _marca():
    return _llamar(lambda: lb.marcar_telegram_enviado(TITULO), b'')

test("marcar_telegram_enviado hace PATCH filtrando por titulo, no por enlace",
     lambda: (lambda r: r[1]["method"] == "PATCH" and "titulo=eq." in r[1]["url"]
              and "enlace=" not in r[1]["url"])(_marca()))


# ── rows_existentes_supabase: consulta y clave por titulo ───────────────────
def _existentes():
    body = json.dumps([{
        "titulo": TITULO, "resumen_claude": "x",
        "categoria": "Administración", "comunidad_autonoma": None,
    }]).encode("utf-8")
    return _llamar(lambda: lb.rows_existentes_supabase({TITULO}), body)

test("rows_existentes_supabase consulta por titulo (in.)",
     lambda: "titulo=in." in _existentes()[1]["url"])
test("rows_existentes_supabase indexa el resultado por titulo",
     lambda: TITULO in _existentes()[0])


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
