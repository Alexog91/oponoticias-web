#!/usr/bin/env python3
"""
publicar_hoy_redes.py — Publica en Facebook (agrupado) e Instagram (carrusel)
las convocatorias de HOY que ya están en Supabase pero que NO se publicaron en
redes (p. ej. porque el FB_PAGE_TOKEN estaba caducado en la ejecución del BOE).

NO toca Telegram ni reenvía nada: solo lee de Supabase y publica en FB+IG
reutilizando las funciones de leer_boe.py. NO llama a Claude.

Requiere: SUPABASE_URL, SUPABASE_API_KEY, FB_PAGE_TOKEN, FB_PAGE_ID, FB_IG_ID
y, para las imágenes, librsvg (rsvg-convert) + Pillow (o Chrome de respaldo).

Uso: python3 publicar_hoy_redes.py
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leer_boe

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
HEADERS = {"apikey": SUPABASE_API_KEY, "Authorization": f"Bearer {SUPABASE_API_KEY}"}


def _fetch(qs):
    url = f"{SUPABASE_URL}/rest/v1/convocatorias?{qs}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def obtener_convocatorias_hoy():
    """Convocatorias insertadas HOY (created_at) con telegram_enviado=true.

    Si la columna created_at no existiera, cae a las 40 más recientes por id.
    """
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sel = "titulo,enlace,resumen_claude,comunidad_autonoma,categoria,fecha"
    try:
        qs = urllib.parse.urlencode({
            "select": sel + ",created_at",
            "telegram_enviado": "eq.true",
            "created_at": f"gte.{hoy}T00:00:00",
            "order": "created_at.desc",
            "limit": "300",
        })
        rows = _fetch(qs)
        print(f"📦 {len(rows)} convocatorias de hoy ({hoy}) por created_at.")
        return rows
    except Exception as e:
        print(f"⚠️  created_at no disponible ({e}); fallback a id.desc (40).")
        qs = urllib.parse.urlencode({
            "select": sel,
            "telegram_enviado": "eq.true",
            "order": "id.desc",
            "limit": "40",
        })
        rows = _fetch(qs)
        print(f"📦 {len(rows)} convocatorias recientes (fallback).")
        return rows


def main():
    print("=" * 62)
    print(f"📤  Publicar HOY en FB+IG — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 62)

    if not (SUPABASE_URL and SUPABASE_API_KEY):
        print("❌ Faltan SUPABASE_URL / SUPABASE_API_KEY")
        return

    import publicar_meta
    if not publicar_meta.configurado():
        print("❌ Falta FB_PAGE_TOKEN / FB_PAGE_ID")
        return

    rows = obtener_convocatorias_hoy()
    # El frontend guarda el resumen en 'resumen_claude'; las funciones de
    # leer_boe esperan 'resumen_ia'. Mapear.
    convs = []
    for r in rows:
        r["resumen_ia"] = r.get("resumen_claude") or ""
        convs.append(r)

    if not convs:
        print("ℹ️  No hay convocatorias de hoy para publicar.")
        return

    pub_fb = os.environ.get("PUBLICAR_FB", "true").lower() != "false"
    pub_ig = os.environ.get("PUBLICAR_IG", "true").lower() != "false"

    if pub_fb:
        print(f"\n🔵 Facebook (agrupado, máx. 6 posts)…")
        leer_boe.publicar_facebook_agrupado(convs)
    else:
        print("\n⏭️  Facebook omitido (PUBLICAR_FB=false).")

    if pub_ig:
        print(f"\n🟣 Instagram (carrusel de las de más plazas)…")
        leer_boe.publicar_carrusel_instagram(convs)
    else:
        print("\n⏭️  Instagram omitido (PUBLICAR_IG=false).")

    print("=" * 62)
    print("✅ Hecho.")
    print("=" * 62)


if __name__ == "__main__":
    main()
