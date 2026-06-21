#!/usr/bin/env python3
"""
compartir_blog_redes.py — Publica en Facebook e Instagram los artículos
del blog que aún no se han compartido en redes sociales.

Diseñado para ponerse al día con artículos ya publicados antes de que
se añadiera la publicación automática en redes.

Toma los 2 artículos más antiguos sin compartir y los publica (tarjeta
personalizada en FB e IG). Llamar una vez por día (cron o GitHub Actions).

NO llama a Claude → no gasta créditos de IA.

Requiere:
  SUPABASE_URL, SUPABASE_API_KEY, FB_PAGE_TOKEN, FB_PAGE_ID, FB_IG_ID

Antes de la primera ejecución, correr en Supabase → SQL Editor:
  ALTER TABLE articulos_blog
    ADD COLUMN IF NOT EXISTS compartido_redes BOOLEAN DEFAULT FALSE;
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_blog as gb
import publicar_meta
import generar_imagen_instagram as gii

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
BASE_URL         = "https://oponoticias.com"
ARTICULOS_POR_DIA = int(os.environ.get("ARTICULOS_POR_DIA", "2"))

HEADERS_SB = {
    "apikey":        SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type":  "application/json",
}


def obtener_pendientes():
    """Artículos publicados que aún no se han compartido en redes."""
    params = urllib.parse.urlencode({
        "select":            "id,titulo,slug,resumen,categoria,fecha_pub",
        "publicado":         "eq.true",
        "compartido_redes":  "eq.false",
        "order":             "fecha_pub.asc",
        "limit":             str(ARTICULOS_POR_DIA),
    })
    try:
        return gb.supabase_get("articulos_blog", params)
    except Exception:
        # La columna puede no existir aún → fallback sin filtro
        params2 = urllib.parse.urlencode({
            "select":    "id,titulo,slug,resumen,categoria,fecha_pub",
            "publicado": "eq.true",
            "order":     "fecha_pub.asc",
            "limit":     str(ARTICULOS_POR_DIA),
        })
        arts = gb.supabase_get("articulos_blog", params2)
        if not arts:
            return []
        print("⚠️  Columna 'compartido_redes' no encontrada — usando fallback sin filtro.")
        print("    Corre este SQL en Supabase → SQL Editor:")
        print("    ALTER TABLE articulos_blog")
        print("      ADD COLUMN IF NOT EXISTS compartido_redes BOOLEAN DEFAULT FALSE;")
        return arts


def marcar_compartido(art_id):
    """Marca compartido_redes=True para el artículo dado."""
    if not SUPABASE_URL:
        return
    url = f"{SUPABASE_URL}/rest/v1/articulos_blog?id=eq.{art_id}"
    data = json.dumps({"compartido_redes": True}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={**HEADERS_SB, "Prefer": "return=minimal"},
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print(f"  ⚠️  No se pudo marcar compartido_redes ({e})")


def compartir_articulo(art):
    """Genera la tarjeta, publica en FB e IG y marca el artículo como compartido."""
    categoria_nombre = gb.NOMBRE_CATEGORIA.get(art["categoria"], art["categoria"].capitalize())
    url_articulo = f"{BASE_URL}/blog/{art['slug']}.html"
    slug_corto   = art["slug"][:40]
    nombre_img   = f"blog/{datetime.now(timezone.utc).strftime('%Y%m')}-{slug_corto}.jpg"

    print(f"  🖼️  Generando tarjeta…")
    img_url = gii.generar_y_subir_blog({
        "categoria": categoria_nombre,
        "titulo":    art["titulo"],
        "resumen":   art.get("resumen", ""),
    }, nombre_img)

    if not img_url:
        print("  ⚠️  No se pudo generar la imagen, omitiendo este artículo.")
        return False

    caption_base = (
        f"📚 {art['titulo']}\n\n"
        f"{art.get('resumen', '')}\n\n"
        f"#oposiciones #{art['categoria']} #BOE #empleopublico #opositar"
    )

    # Facebook: foto + enlace al artículo
    ok_fb = publicar_meta.publicar_foto_facebook(
        img_url,
        caption_base + f"\n\n👉 {url_articulo}",
    )

    # Instagram: foto + enlace en bio
    ok_ig = publicar_meta.publicar_foto_instagram(
        img_url,
        caption_base + "\n\n🔗 Enlace en bio · oponoticias.com",
    )

    if ok_fb or ok_ig:
        marcar_compartido(art["id"])
        return True
    return False


def main():
    print("=" * 62)
    print(f"📤  Compartir Blog en Redes — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 62)

    if not (SUPABASE_URL and SUPABASE_API_KEY):
        print("❌ Faltan SUPABASE_URL / SUPABASE_API_KEY")
        return

    if not publicar_meta.configurado():
        print("❌ Falta FB_PAGE_TOKEN o FB_PAGE_ID")
        return

    pendientes = obtener_pendientes()
    if not pendientes:
        print("✅ Todos los artículos ya están compartidos en redes.")
        return

    print(f"📋 Publicando {len(pendientes)} artículo(s) hoy:\n")
    publicados = 0
    for art in pendientes:
        print(f"  [{gb.NOMBRE_CATEGORIA.get(art['categoria'], art['categoria'])}]"
              f" {art['titulo'][:55]}")
        if compartir_articulo(art):
            publicados += 1
            print(f"  ✅ Compartido en FB + IG\n")

    print(f"{'=' * 62}")
    print(f"✅ {publicados}/{len(pendientes)} artículo(s) compartidos hoy.")
    if publicados < len(obtener_pendientes()):
        print("   Quedan más artículos. Se publicarán en la próxima ejecución.")
    print("=" * 62)


if __name__ == "__main__":
    main()
