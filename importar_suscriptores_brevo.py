"""
importar_suscriptores_brevo.py — Migra los contactos exportados de Brevo (CSV) a la
tabla `suscriptores` de Supabase. Uso único al migrar a SES (Fase 2 del PLAN-EMAIL-SES).

Cómo obtener el CSV: Brevo → Contactos → (seleccionar todos) → Exportar → descargar CSV.
Debe tener al menos una columna de email; si tiene COMUNIDAD, también se importa.

Uso:
    SUPABASE_URL=... SUPABASE_API_KEY=... python3 importar_suscriptores_brevo.py contactos.csv
    # o con DRY_RUN=1 para ver qué se importaría sin escribir nada:
    DRY_RUN=1 python3 importar_suscriptores_brevo.py contactos.csv

Notas de diseño:
  - Upsert por email (on_conflict=email, merge-duplicates): re-ejecutar es seguro.
  - NO se envía `estado` → las filas nuevas quedan 'activo' (default de la BD) y las
    existentes conservan su estado (no resucita a quien se dio de baja).
  - NO se envía `token_baja` → lo genera el default de la BD en las filas nuevas y se
    conserva en las existentes.
  - `comunidad` sí se actualiza (en la migración Brevo es la fuente de verdad).
"""

import os
import sys
import csv
import json
import urllib.request

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
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        # Detecta el separador (Brevo suele usar ';' o ','), con fallback a ','.
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
        sys.exit("Uso: python3 importar_suscriptores_brevo.py <contactos.csv>")
    ruta = sys.argv[1]

    print(f"📥 Importando suscriptores desde {ruta}" + ("  (DRY RUN)" if DRY_RUN else ""))
    registros = leer_csv(ruta)
    print(f"  {len(registros)} contactos únicos a importar.")
    con_com = sum(1 for r in registros if r.get("comunidad"))
    print(f"  De ellos, {con_com} con comunidad; {len(registros) - con_com} sin comunidad (reciben todo).")

    if DRY_RUN:
        for r in registros[:5]:
            print("   ejemplo:", r)
        print("  (DRY RUN: no se ha escrito nada en Supabase).")
        return 0

    # Upsert en lotes de 500.
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
