#!/usr/bin/env python3
"""
rellenar_convocatorias.py — Backfill de convocatorias incompletas.

Rellena las filas de la tabla `convocatorias` que tienen `categoria` o
`resumen_claude` en NULL (por ejemplo, las guardadas con la versión de
leer_boe.py que no escribía esos campos).

Para cada fila incompleta:
  1. Calcula la categoría a partir del título (extraer_cuerpo).
  2. Genera el resumen IA con Claude (generar_resumen_con_claude).
  3. Clasifica la comunidad autónoma (clasificar_comunidad).
  4. Hace PATCH de la fila en Supabase.

Requiere: SUPABASE_URL, SUPABASE_API_KEY (service_role), ANTHROPIC_API_KEY.
Ejecutar manualmente (workflow_dispatch) una sola vez.
"""

import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error

# Reutilizamos la lógica ya probada de leer_boe.py
from leer_boe import extraer_cuerpo, generar_resumen_con_claude, clasificar_comunidad

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")

HEADERS = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
}


def fetch_incompletas(limite=1000):
    """Devuelve las filas con categoria O resumen_claude en NULL."""
    params = urllib.parse.urlencode({
        "select": "id,titulo,resumen",
        "or": "(categoria.is.null,resumen_claude.is.null)",
        "order": "created_at.desc",
        "limit": limite,
    })
    url = f"{SUPABASE_URL}/rest/v1/convocatorias?{params}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def patch_fila(id_fila, data):
    """Actualiza una fila por id."""
    url = f"{SUPABASE_URL}/rest/v1/convocatorias?id=eq.{id_fila}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={**HEADERS, "Prefer": "return=minimal"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def main():
    print("=" * 60)
    print("🔧 Backfill de convocatorias incompletas")
    print("=" * 60)

    if not (SUPABASE_URL and SUPABASE_API_KEY and os.environ.get("ANTHROPIC_API_KEY")):
        print("❌ Faltan variables: SUPABASE_URL, SUPABASE_API_KEY, ANTHROPIC_API_KEY")
        return

    filas = fetch_incompletas()
    print(f"📋 {len(filas)} filas incompletas por rellenar.\n")

    arregladas = 0
    for i, fila in enumerate(filas, 1):
        titulo = fila.get("titulo", "")
        resumen = fila.get("resumen", "")
        print(f"[{i}/{len(filas)}] {titulo[:60]}…")

        cuerpo, categoria = extraer_cuerpo(titulo)
        resumen_ia = generar_resumen_con_claude(titulo, resumen)
        comunidad = clasificar_comunidad(titulo, resumen)

        data = {
            "categoria": categoria,
            "cuerpo": cuerpo,
            "resumen_claude": resumen_ia,
        }
        if comunidad:
            data["comunidad_autonoma"] = comunidad

        try:
            status = patch_fila(fila["id"], data)
            if status in (200, 204):
                print(f"   ✅ {categoria} · {resumen_ia[:50]}")
                arregladas += 1
            else:
                print(f"   ⚠️  PATCH status {status}")
        except Exception as e:
            print(f"   ❌ Error PATCH: {e}")

        time.sleep(1)  # no saturar la API de Claude

    print(f"\n{'=' * 60}")
    print(f"✅ Completado — {arregladas}/{len(filas)} filas rellenadas")
    print("=" * 60)


if __name__ == "__main__":
    main()
