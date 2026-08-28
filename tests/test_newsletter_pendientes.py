"""tests/test_newsletter_pendientes.py — selección de convocatorias a enviar y
ventana matinal del newsletter.

Ejecuta:  python3 tests/test_newsletter_pendientes.py

Fija: (1) la ventana matinal (fuera de hora no se envía); (2) que se usa el flag
email_enviado cuando existe la columna, y (3) que cae a la selección por fecha si
la columna aún no está (deploy antes de la migración).
"""
import os
import sys
from email.utils import format_datetime
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_API_KEY", "x")
os.environ.setdefault("ENVIO_LIMITE_UTC", "11:00")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import enviar_newsletter_ses as nl  # noqa: E402

HOY_RFC = format_datetime(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0))

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731

# ── Ventana matinal ────────────────────────────────────────────────────────────
test("ventana: 09:00 dentro", lambda: nl.dentro_ventana_envio("09:00") is True)
test("ventana: 11:00 dentro (límite)", lambda: nl.dentro_ventana_envio("11:00") is True)
test("ventana: 17:45 FUERA", lambda: nl.dentro_ventana_envio("17:45") is False)


# ── Selección con flag email_enviado (columna existe) ──────────────────────────
def _con_flag():
    orig = nl.supabase_get
    def fake(endpoint, params):
        assert params.get("email_enviado") == "eq.false", "debe filtrar por el flag"
        return [{"id": 1, "titulo": "A", "fecha": HOY_RFC}]
    nl.supabase_get = fake
    try:
        return nl.obtener_convocatorias_pendientes()
    finally:
        nl.supabase_get = orig

test("flag: usa email_enviado y marca usa_flag=True",
     lambda: _con_flag() == ([{"id": 1, "titulo": "A", "fecha": HOY_RFC}], True))


# ── Fallback por fecha (columna NO existe → supabase_get lanza) ─────────────────
def _sin_columna():
    orig = nl.supabase_get
    def fake(endpoint, params):
        if params.get("email_enviado"):
            raise Exception('column "email_enviado" does not exist')
        # segunda llamada = obtener_convocatorias_por_fecha (sin filtro de flag)
        return [{"id": 2, "titulo": "B", "fecha": HOY_RFC}]
    nl.supabase_get = fake
    try:
        return nl.obtener_convocatorias_pendientes()
    finally:
        nl.supabase_get = orig

test("fallback: sin columna → usa_flag=False y selección por fecha (hoy)",
     lambda: _sin_columna() == ([{"id": 2, "titulo": "B", "fecha": HOY_RFC}], False))


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
