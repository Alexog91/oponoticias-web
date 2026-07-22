"""tests/test_supabase_paginacion.py — supabase_get debe traer TODAS las filas.

Ejecuta:  python3 tests/test_supabase_paginacion.py

Por qué existe: el Data API de Supabase tiene "Max rows = 1000" (verificado en
el panel del proyecto el 22 jul 2026). Sin paginar, el día que haya más de
1.000 suscriptores activos la consulta devolvería 1.000 y el resto dejaría de
recibir la newsletter **sin ningún error**: nadie se enteraría. Es el mismo
patrón que ya ocurrió con Brevo, que estuvo enviando a la mitad de la base
durante días en silencio.

No toca la red: se inyecta un fetcher falso que simula el corte del servidor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import newsletter_utils as u  # noqa: E402

MAX_ROWS = 1000  # lo que impone Supabase por petición


def servidor_falso(total, registro=None):
    """Simula PostgREST con tope de MAX_ROWS por petición."""
    filas = [{"id": i} for i in range(total)]

    def fetch(url):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(url).query)
        limit = int(q.get("limit", [MAX_ROWS])[0])
        offset = int(q.get("offset", [0])[0])
        if registro is not None:
            registro.append((offset, limit))
        return filas[offset:offset + min(limit, MAX_ROWS)]

    return fetch


def get(total, params=None, registro=None):
    return u.supabase_get("https://x.invalid", "k", "suscriptores",
                          params or {"select": "email"},
                          _fetch=servidor_falso(total, registro))


casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


test("caso de hoy (340 filas) — cabe en una petición", lambda: len(get(340)) == 340)

test("EXACTAMENTE 1000 filas: no se pierde ninguna", lambda: len(get(1000)) == 1000)

test("1001 filas — el fallo que esto previene", lambda: len(get(1001)) == 1001)

test("2500 filas se traen enteras", lambda: len(get(2500)) == 2500)

test("las filas salen en orden y sin duplicados", lambda: (
    [f["id"] for f in get(2500)] == list(range(2500))
))

test("pide las páginas justas (2500 → 3 peticiones)", lambda: (
    (lambda r: (get(2500, registro=r), len(r) == 3)[1])([])
))

test("respeta un limit explícito del caller (no trae de más)", lambda: (
    len(get(5000, params={"select": "x", "limit": "150"})) == 150
))

test("un limit menor que una página no dispara más peticiones", lambda: (
    (lambda r: (get(5000, params={"select": "x", "limit": "150"}, registro=r),
                len(r) == 1)[1])([])
))

test("lista vacía no rompe", lambda: get(0) == [])

# Paginar sin ORDER BY es un fallo silencioso: Postgres no garantiza el mismo
# orden entre peticiones, así que entre página y página se pueden colar filas
# repetidas y perderse otras. Si va a haber más de una página, hay que avisar.
def _avisa_si_pagina_sin_order(params, total):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        get(total, params=params)
    return "order" in buf.getvalue().lower()


test("AVISA si tiene que paginar sin un 'order' estable", lambda: (
    _avisa_si_pagina_sin_order({"select": "email"}, 2500) is True
))

test("no avisa cuando el llamante sí pasa 'order'", lambda: (
    _avisa_si_pagina_sin_order({"select": "email", "order": "id"}, 2500) is False
))

test("no avisa si todo cabe en una página (no hay riesgo)", lambda: (
    _avisa_si_pagina_sin_order({"select": "email"}, 340) is False
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
    print("─" * 62)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
