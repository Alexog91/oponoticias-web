#!/usr/bin/env python3
"""
compartir_blog_redes.py — Publica en Facebook e Instagram los artículos
del blog que aún no se han compartido en redes sociales.

Facebook: post de texto con el contenido del artículo + enlace al final.
Instagram: screenshot real del HTML del artículo (1080×1350) con Chrome.

Toma los 2 artículos más antiguos sin compartir y los publica.
Llamar una vez por día (cron o GitHub Actions). NO llama a Claude.

Requiere:
  SUPABASE_URL, SUPABASE_API_KEY, FB_PAGE_TOKEN, FB_PAGE_ID, FB_IG_ID,
  Chrome (google-chrome o chromium-browser en PATH / CHROME_BIN)

Antes de la primera ejecución, correr en Supabase → SQL Editor:
  ALTER TABLE articulos_blog
    ADD COLUMN IF NOT EXISTS compartido_redes BOOLEAN DEFAULT FALSE;
"""

import os
import re
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_blog as gb
import publicar_meta
import generar_imagen_instagram as gii

SUPABASE_URL      = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY  = os.environ.get("SUPABASE_API_KEY", "")
BASE_URL          = "https://oponoticias.com"
ARTICULOS_POR_DIA = int(os.environ.get("ARTICULOS_POR_DIA", "2"))
BLOG_DIR          = Path(__file__).resolve().parent / "blog"

HEADERS_SB = {
    "apikey":        SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type":  "application/json",
}


def obtener_pendientes():
    """Artículos publicados que aún no se han compartido en redes."""
    params = urllib.parse.urlencode({
        "select":           "id,titulo,slug,resumen,contenido,categoria,fecha_pub",
        "publicado":        "eq.true",
        "compartido_redes": "eq.false",
        "order":            "fecha_pub.asc",
        "limit":            str(ARTICULOS_POR_DIA),
    })
    try:
        return gb.supabase_get("articulos_blog", params)
    except Exception:
        # Columna puede no existir aún → fallback sin filtro
        params2 = urllib.parse.urlencode({
            "select":    "id,titulo,slug,resumen,contenido,categoria,fecha_pub",
            "publicado": "eq.true",
            "order":     "fecha_pub.asc",
            "limit":     str(ARTICULOS_POR_DIA),
        })
        arts = gb.supabase_get("articulos_blog", params2)
        if not arts:
            return []
        print("⚠️  Columna 'compartido_redes' no encontrada — usando fallback.")
        print("    Corre en Supabase → SQL Editor:")
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


def _strip_markdown(texto):
    """Elimina el marcado Markdown básico para obtener texto plano."""
    texto = re.sub(r'^#{1,6}\s+', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'\*{1,2}([^*\n]+)\*{1,2}', r'\1', texto)
    texto = re.sub(r'_{1,2}([^_\n]+)_{1,2}', r'\1', texto)
    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)
    texto = re.sub(r'^[\-\*\d+\.]\s+', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()


def compartir_articulo(art):
    """Publica en FB (texto+enlace) e IG (screenshot) y marca el artículo."""
    url_articulo  = f"{BASE_URL}/blog/{art['slug']}.html"
    hashtags      = (
        f"#oposiciones #{art['categoria']} #BOE #empleopublico #opositar"
    )

    # ── Facebook: texto del artículo + enlace ──────────────────────────────
    print("  📝 Construyendo post de Facebook…")
    contenido_limpio = _strip_markdown(art.get("contenido", ""))
    parrafos = [p.strip() for p in contenido_limpio.split("\n\n") if p.strip()]
    extracto = ""
    for p in parrafos:
        if len(extracto) + len(p) + 2 > 2500:
            break
        extracto = (extracto + "\n\n" + p).strip()
    msg_fb = (
        f"📚 {art['titulo']}\n\n"
        f"{extracto}\n\n"
        f"👉 Lee el artículo completo:\n{url_articulo}\n\n"
        f"{hashtags}"
    )
    ok_fb = publicar_meta.publicar_enlace_facebook(msg_fb)

    # ── Instagram: screenshot del HTML del artículo ─────────────────────────
    print("  📸 Generando screenshot del artículo para Instagram…")
    slug_corto    = art["slug"][:40]
    nombre_remoto = f"blog/ig-{datetime.now(timezone.utc).strftime('%Y%m')}-{slug_corto}.jpg"
    html_path     = BLOG_DIR / f"{art['slug']}.html"
    img_url       = gii.screenshot_blog_html(str(html_path), nombre_remoto)

    ok_ig = False
    if img_url:
        caption_ig = (
            f"📚 {art['titulo']}\n\n"
            f"{art.get('resumen', '')}\n\n"
            f"🔗 Enlace en bio · oponoticias.com\n\n"
            f"{hashtags}"
        )
        ok_ig = publicar_meta.publicar_foto_instagram(img_url, caption_ig)
    else:
        print("  ⚠️  No se pudo generar screenshot para Instagram.")

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
        else:
            print(f"  ⚠️  No se publicó en ninguna red\n")

    print(f"{'=' * 62}")
    print(f"✅ {publicados}/{len(pendientes)} artículo(s) compartidos hoy.")
    print("=" * 62)


if __name__ == "__main__":
    main()
