"""
importar_suscriptores_brevo.py — Migra los contactos de Brevo a la tabla `suscriptores`
de Supabase. Dos modos:

  --api   (RECOMENDADO) Lee los contactos DIRECTAMENTE de la API de Brevo (paginado).
          Siempre trae el estado real, incluida la lista de bloqueados/dados de baja
          (emailBlacklisted) — algo que el CSV exportado desde la web de Brevo NO
          incluye. Se puede re-ejecutar en cualquier momento sin exportar nada a mano;
          útil porque la lista sigue creciendo mientras se espera la aprobación de AWS.
          Requiere BREVO_API_KEY.

  <csv>   Modo antiguo con un CSV exportado a mano (Brevo → Contactos → Exportar).
          OJO: el CSV no distingue contactos bloqueados/dados de baja en Brevo — si se
          usa este modo, hay que descartar esos emails aparte (ver aviso en pantalla).

Uso:
    BREVO_API_KEY=... SUPABASE_URL=... SUPABASE_API_KEY=... python3 importar_suscriptores_brevo.py --api
    SUPABASE_URL=... SUPABASE_API_KEY=... python3 importar_suscriptores_brevo.py contactos.csv
    # DRY_RUN=1 para ver qué se importaría sin escribir nada en Supabase:
    DRY_RUN=1 python3 importar_suscriptores_brevo.py --api

Notas de diseño:
  - Upsert por email (on_conflict=email, merge-duplicates): re-ejecutar es seguro.
  - Si el contacto está bloqueado/dado de baja en Brevo (emailBlacklisted=true, modo
    --api), se marca `estado='baja'` + `fecha_baja` explícitamente — nunca se le vuelve
    a escribir por el motor SES.
  - Si NO está bloqueado, no se envía `estado` → las filas nuevas quedan 'activo'
    (default de la BD) y las existentes conservan su estado (no resucita una baja
    que el usuario hubiera pedido ya en el nuevo sistema).
  - NO se envía `token_baja` → lo genera el default de la BD en las filas nuevas y se
    conserva en las existentes.
  - `comunidad` sí se actualiza (Brevo es la fuente de verdad en esta migración).
"""

import os
import sys
import csv
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

SUPABASE_URL     = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_API_KEY = os.environ["SUPABASE_API_KEY"]
DRY_RUN          = os.environ.get("DRY_RUN") == "1"

# Nombres posibles de columna en el CSV de Brevo (case-insensitive).
COLS_EMAIL     = {"email", "correo", "e-mail", "mail"}
COLS_COMUNIDAD = {"comunidad", "comunidad_autonoma", "ccaa"}
# Comunidades válidas (mismas que /api/preferencias). "" = recibe todas.
COMUNIDADES = {
    'Andalucía', 'Aragón', 'Asturias', 'Baleares', 'Canarias', 'Cantabria',
    'Castilla-La Mancha', 'Castilla y León', 'Cataluña', 'Comunidad Valenciana',
    'Extremadura', 'Galicia', 'La Rioja', 'Madrid', 'Murcia', 'Navarra',
    'País Vasco', 'Ceuta', 'Melilla', 'Nacional/Estatal',
}


# ── Modo API (recomendado) ──────────────────────────────────────────
def obtener_contactos_brevo_api():
    """Pagina GET /v3/contacts y devuelve todos los contactos con su comunidad
    (atributo personalizado) y si están bloqueados/dados de baja en Brevo."""
    api_key = os.environ["BREVO_API_KEY"]
    contactos, offset, limit = [], 0, 1000
    while True:
        qs = urllib.parse.urlencode({"limit": limit, "offset": offset, "sort": "desc"})
        req = urllib.request.Request(
            f"https://api.brevo.com/v3/contacts?{qs}",
            headers={"api-key": api_key, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        lote = data.get("contacts", [])
        contactos.extend(lote)
        if len(lote) < limit:
            break
        offset += limit
    print(f"  {len(contactos)} contactos leídos de la API de Brevo.")

    registros, bloqueados = [], 0
    for c in contactos:
        email = (c.get("email") or "").strip().lower()
        if not email:
            continue
        reg = {"email": email, "origen": "brevo-import"}
        com = ((c.get("attributes") or {}).get("COMUNIDAD") or "").strip()
        if com in COMUNIDADES:
            reg["comunidad"] = com
        if c.get("emailBlacklisted"):
            reg["estado"] = "baja"
            reg["fecha_baja"] = datetime.now(timezone.utc).isoformat()
            bloqueados += 1
        registros.append(reg)
    print(f"  De ellos, {bloqueados} están bloqueados/dados de baja en Brevo → "
          f"se marcarán 'baja' en Supabase (no se les volverá a escribir).")
    return registros


# ── Modo CSV (antiguo, sin estado de bloqueo) ───────────────────────
def detectar_columnas(cabeceras):
    email_col, com_col = None, None
    for h in cabeceras:
        hl = (h or "").strip().lower()
        if email_col is None and hl in COLS_EMAIL:
            email_col = h
        if com_col is None and hl in COLS_COMUNIDAD:
            com_col = h
    return email_col, com_col


def leer_csv(ruta):
    print("  ⚠️  Modo CSV: NO distingue contactos bloqueados/dados de baja en Brevo.")
    print("      Se recomienda el modo --api salvo que ya se haya filtrado el CSV a mano.")
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        muestra = f.read(4096)
        f.seek(0)
        try:
            dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t")
        except csv.Error:
            dialecto = csv.excel
        lector = csv.DictReader(f, dialect=dialecto)
        email_col, com_col = detectar_columnas(lector.fieldnames or [])
        if not email_col:
            sys.exit(f"❌ No encuentro una columna de email en: {lector.fieldnames}")
        print(f"  Columna email: '{email_col}'"
              + (f", comunidad: '{com_col}'" if com_col else " (sin columna de comunidad)"))

        registros, vistos, invalidos = [], set(), 0
        for fila in lector:
            email = (fila.get(email_col) or "").strip().lower()
            if not email or "@" not in email or email in vistos:
                if email and email in vistos:
                    continue
                invalidos += 1
                continue
            vistos.add(email)
            reg = {"email": email, "origen": "brevo-import"}
            if com_col:
                com = (fila.get(com_col) or "").strip()
                if com in COMUNIDADES:
                    reg["comunidad"] = com
            registros.append(reg)
        if invalidos:
            print(f"  ⚠️  {invalidos} filas sin email válido, omitidas.")
        return registros


def upsert_lote(lote):
    url = f"{SUPABASE_URL}/rest/v1/suscriptores?on_conflict=email"
    data = json.dumps(lote).encode("utf-8")
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, ""
    except urllib.request.HTTPError as e:
        return e.code, (e.read() or b"").decode("utf-8", "replace")


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python3 importar_suscriptores_brevo.py --api | <contactos.csv>")
    origen = sys.argv[1]

    print(f"📥 Importando suscriptores" + ("  (DRY RUN)" if DRY_RUN else ""))
    if origen == "--api":
        registros = obtener_contactos_brevo_api()
    else:
        registros = leer_csv(origen)

    print(f"  {len(registros)} contactos únicos a importar.")
    con_com = sum(1 for r in registros if r.get("comunidad"))
    print(f"  De ellos, {con_com} con comunidad; {len(registros) - con_com} sin comunidad (reciben todo).")

    if DRY_RUN:
        for r in registros[:5]:
            print("   ejemplo:", r)
        print("  (DRY RUN: no se ha escrito nada en Supabase).")
        return 0

    total_ok, total_err = 0, 0
    for i in range(0, len(registros), 500):
        lote = registros[i:i + 500]
        status, err = upsert_lote(lote)
        if 200 <= status < 300:
            total_ok += len(lote)
            print(f"  ✓ Lote {i // 500 + 1}: {len(lote)} filas ({status})")
        else:
            total_err += len(lote)
            print(f"  ❌ Lote {i // 500 + 1}: {status} — {err[:200]}")

    print(f"\n✅ Importados {total_ok}; errores {total_err}.")
    return 0 if total_err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
