"""tests/test_leer_boe_sumario.py — el lector determinista del sumario del BOE.

Ejecuta:  python3 tests/test_leer_boe_sumario.py

Por qué existe: el 15 ago 2026 el daily-boe corrió a las 7:19 CEST, cuando el RSS
del BOE (ventana móvil) aún servía el boletín de AYER → releyó lo de ayer, reportó
"Nuevas: 0" y las 22 convocatorias reales de ese día no se capturaron. El arreglo
lee el sumario oficial POR FECHA (determinista) en una ventana de varios días.
Estos tests fijan ese comportamiento sin tocar la red (monkeypatch de la descarga).
"""

import os
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import leer_boe as lb  # noqa: E402

# Sumario de muestra con la estructura real de la API (dict/list mezclados).
SAMPLE = {"data": {"sumario": {"diario": [{"seccion": [
    {"codigo": "2B", "nombre": "II.B Oposiciones", "departamento": [
        {"nombre": "AYUNTAMIENTO", "item": [
            {"identificador": "BOE-A-2026-100",
             "titulo": "Resolución de 10 de agosto, del Ayuntamiento de X, referente a la convocatoria para proveer una plaza de administrativo."},
            {"identificador": "BOE-A-2026-101",
             "titulo": "Resolución de 5 de agosto, de la Subsecretaría, por la que se convoca la provisión de puestos por el sistema de libre designación."},
        ]},
        {"nombre": "DIPUTACIÓN", "epigrafe": [{"item":
            {"identificador": "BOE-A-2026-102",   # item único → dict, no lista
             "titulo": "Resolución de 10 de agosto, de la Diputación de Y, referente a la convocatoria para proveer varias plazas."}}]},
    ]},
    {"codigo": "3", "nombre": "III Otras disposiciones", "departamento": [
        {"item": [{"identificador": "BOE-A-2026-200",
                   "titulo": "Resolución sobre una convocatoria de subvenciones y plazas hoteleras."}]}]},
]}]}}}

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


# ── Parser de la sección 2B ────────────────────────────────────────────────────
def _ids_2b():
    return [i for (i, _t, _f) in lb._parse_sumario_2b(SAMPLE, "FECHA")]

test("2B: extrae las 3 disposiciones de Oposiciones", lambda: len(_ids_2b()) == 3)
test("2B: NO se cuela la sección 3 (Otras disposiciones)",
     lambda: "BOE-A-2026-200" not in _ids_2b())
test("2B: soporta item único (dict) además de lista",
     lambda: "BOE-A-2026-102" in _ids_2b())


# ── Filtro es_convocatoria aplicado en leer_boe_sumario ─────────────────────────
def _sumario_fake(dias):
    """Monkeypatch: devuelve la muestra para 'hoy' y vacío para días anteriores."""
    llamadas = {"n": 0}
    def fake(_yyyymmdd):
        llamadas["n"] += 1
        return lb._parse_sumario_2b(SAMPLE, "Fri, 15 Aug 2026 00:00:00 +0200") if llamadas["n"] == 1 else []
    return fake

def _run(dias=3):
    orig = lb._sumario_un_dia
    lb._sumario_un_dia = _sumario_fake(dias)
    try:
        return lb.leer_boe_sumario(dias=dias)
    finally:
        lb._sumario_un_dia = orig

test("libre designación se DESCARTA (no es acceso libre)",
     lambda: all("libre designación" not in c["titulo"].lower() for c in _run()))
test("convocatoria de plaza SÍ pasa el filtro",
     lambda: any(c["ref_boe"] == "BOE-A-2026-100" for c in _run()))
test("resultado: 2 convocatorias válidas (100 y 102)",
     lambda: sorted(c["ref_boe"] for c in _run()) == ["BOE-A-2026-100", "BOE-A-2026-102"])


# ── Forma del dict (compatible con leer_boe_rss) ───────────────────────────────
def _uno():
    return next(c for c in _run() if c["ref_boe"] == "BOE-A-2026-100")

test("enlace en el MISMO formato que el RSS (dedup por enlace)",
     lambda: _uno()["enlace"] == "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-100")
test("tiene las claves que espera el pipeline",
     lambda: all(k in _uno() for k in ("fecha", "titulo", "enlace", "resumen", "ref_boe")))


# ── fecha en RFC 2822 (la parsea el newsletter con parsedate_to_datetime) ──────
test("fecha es RFC 2822 y su .date() es correcta",
     lambda: parsedate_to_datetime(_uno()["fecha"]).date().isoformat() == "2026-08-15")
test("_fecha_rfc produce una fecha parseable con el día correcto",
     lambda: parsedate_to_datetime(lb._fecha_rfc("20260815")).date().isoformat() == "2026-08-15")


# ── Deduplicación entre días de la ventana ─────────────────────────────────────
def _run_mismo_todos_los_dias():
    orig = lb._sumario_un_dia
    lb._sumario_un_dia = lambda _d: lb._parse_sumario_2b(SAMPLE, "Fri, 15 Aug 2026 00:00:00 +0200")
    try:
        return lb.leer_boe_sumario(dias=3)   # 3 días devolviendo lo MISMO
    finally:
        lb._sumario_un_dia = orig

test("dedup: la misma disposición en varios días aparece una sola vez",
     lambda: len(_run_mismo_todos_los_dias()) == 2)


# ── Aviso al admin los días sin convocatorias (2B vacía) ───────────────────────
def _run_con_sumario(fake_un_dia):
    orig = lb._sumario_un_dia
    lb._sumario_un_dia = fake_un_dia
    try:
        return lb.leer_boe_sumario(dias=3)
    finally:
        lb._sumario_un_dia = orig

# Hoy CON convocatorias → no se avisa; _STATS_HOY refleja 3 crudas / 2 válidas.
def _hoy_con():
    llam = {"n": 0}
    def fake(_d):
        llam["n"] += 1
        return lb._parse_sumario_2b(SAMPLE, "Fri, 15 Aug 2026 00:00:00 +0200") if llam["n"] == 1 else []
    _run_con_sumario(fake)
    return lb._STATS_HOY

test("día con convocatorias: publicado=True, validas>0, NO se avisa",
     lambda: (_hoy_con()["publicado"] is True and _hoy_con()["validas"] == 2
              and lb._debe_avisar_admin(lb._STATS_HOY) is False))

# Hoy con 2B VACÍA (boletín existe, [] ) → SÍ se avisa.
def _hoy_vacio():
    _run_con_sumario(lambda _d: [])          # todos los días: boletín existe, 2B vacía
    return lb._STATS_HOY

test("día con 2B vacía: publicado=True, raw=0, validas=0 → SÍ se avisa",
     lambda: (_hoy_vacio()["publicado"] is True and _hoy_vacio()["raw"] == 0
              and lb._debe_avisar_admin(lb._STATS_HOY) is True))

# Hoy SIN boletín (404 → None) → NO se avisa (falso día vacío).
def _hoy_sin_boletin():
    _run_con_sumario(lambda _d: None)        # 404 en todos
    return lb._STATS_HOY

test("día sin boletín (404): publicado=False → NO se avisa",
     lambda: (_hoy_sin_boletin()["publicado"] is False
              and lb._debe_avisar_admin(lb._STATS_HOY) is False))

# Hoy con entradas pero TODAS libre designación (0 válidas) → SÍ se avisa.
SOLO_LIBRE = {"data": {"sumario": {"diario": [{"seccion": [
    {"codigo": "2B", "departamento": [{"item": [
        {"identificador": "BOE-A-2026-900",
         "titulo": "Resolución por la que se convoca la provisión de puestos por libre designación."},
    ]}]}]}]}}}
def _hoy_solo_libre():
    llam = {"n": 0}
    def fake(_d):
        llam["n"] += 1
        return lb._parse_sumario_2b(SOLO_LIBRE, "x") if llam["n"] == 1 else []
    _run_con_sumario(fake)
    return lb._STATS_HOY

test("día con solo libre designación: raw>0 pero validas=0 → SÍ se avisa",
     lambda: (_hoy_solo_libre()["raw"] == 1 and _hoy_solo_libre()["validas"] == 0
              and lb._debe_avisar_admin(lb._STATS_HOY) is True))


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try:
            ok = fn()
        except Exception as e:                       # noqa: BLE001
            ok, nombre = False, f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}")
        fallos += not ok
    print("─" * 60)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
