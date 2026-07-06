#!/usr/bin/env python3
"""
publicar_programados.py — Publica los borradores de blog cuya fecha ha llegado.

Para cada artículo con publicado=False y fecha_pub <= ahora:
  1. Marca publicado=True en Supabase.
  2. Publica la tarjeta personalizada en Facebook e Instagram.
  3. Regenera el índice del blog (blog.html) y el sitemap.

Uso:
  python3 publicar_programados.py

Se llama automáticamente desde generar-blog.yml (lunes y jueves).
También se puede lanzar manualmente para forzar la publicación de hoy.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_blog as gb

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")

HEADERS_SB = {
    "apikey":        SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type":  "application/json",
}


def obtener_pendientes():
    """Artículos con publicado=False cuya fecha_pub ya ha llegado."""
    ahora = datetime.now(timezone.utc).isoformat()
    params = urllib.parse.urlencode({
        "select":    "id,titulo,slug,resumen,contenido,categoria,fecha_pub",
        "publicado": "eq.false",
        "fecha_pub": f"lte.{ahora}",
        "order":     "fecha_pub.asc",
    })
    return gb.supabase_get("articulos_blog", params)


def marcar_publicado(art_id):
    """Pone publicado=True para un artículo dado su id."""
    if not SUPABASE_URL:
        return False
    url = f"{SUPABASE_URL}/rest/v1/articulos_blog?id=eq.{art_id}"
    data = json.dumps({"publicado": True}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={**HEADERS_SB, "Prefer": "return=minimal"},
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:
        print(f"  ❌ PATCH publicado=True falló: {e}")
        return False


def main():
    print("=" * 62)
    print(f"📢  Publicar Programados — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 62)

    if not (SUPABASE_URL and SUPABASE_API_KEY):
        print("❌ Faltan SUPABASE_URL / SUPABASE_API_KEY")
        return

    pendientes = obtener_pendientes()
    if not pendientes:
        print("ℹ️  Sin borradores pendientes para hoy.")
        return

    print(f"📋 {len(pendientes)} artículo(s) listos para publicar:\n")
    publicados = 0

    for art in pendientes:
        print(f"  📝 [{gb.NOMBRE_CATEGORIA.get(art['categoria'], art['categoria'])}] "
              f"{art['titulo'][:55]}")

        if not marcar_publicado(art["id"]):
            continue

        # La publicación en la web (publicado=True) ya está hecha; un fallo al
        # publicar en redes es secundario y NO debe abortar el resto del lote
        # ni impedir la regeneración de índice/sitemap de abajo (antes, una
        # excepción sin capturar aquí paraba el script entero a mitad,
        # dejando también sin regenerar el índice de los artículos ya
        # publicados en iteraciones anteriores).
        try:
            gb._publicar_en_redes(art)
            print(f"  ✅ Publicado en web + redes\n")
        except Exception as e:
            print(f"  ⚠️  Publicado en la web, pero falló la publicación en redes: {e}\n")
        publicados += 1

    if publicados:
        gb.regenerar_indice_y_sitemap()
        print(f"✅ {publicados} artículo(s) publicados — índice y sitemap actualizados.")
    print("=" * 62)


if __name__ == "__main__":
    main()
