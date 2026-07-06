#!/usr/bin/env python3
"""
planificar_blog.py — Genera artículos de blog para TODAS las categorías
como borradores con fechas de publicación distribuidas en los próximos días.

Uso (manual o GitHub Actions):
  SUPABASE_URL=... SUPABASE_API_KEY=... ANTHROPIC_API_KEY=... python3 planificar_blog.py

Comportamiento:
  - Genera 1 artículo por cada categoría activa (8 total), saltando el límite
    normal y la comprobación de artículo reciente.
  - Los guarda con publicado=False y fecha_pub distribuida en los próximos días
    (1 artículo por día, saltando domingos), empezando por mañana.
  - Crea las páginas HTML (accesibles por URL directa pero no listadas en el
    índice ni en el sitemap hasta que se publiquen).
  - NO publica en redes sociales (eso ocurre al publicar el borrador).

Para publicar los borradores:
  - Automático: generar-blog.yml corre publicar_programados.py cada lunes y jueves.
  - Manual: python3 publicar_programados.py
"""

import os
import sys
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_blog as gb

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
BASE_URL         = "https://oponoticias.com"
BLOG_DIR         = "blog"

HEADERS_SB = lambda: {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
}


def _proxima_fecha(usadas):
    """Devuelve la siguiente fecha disponible, 1 artículo por día, sin domingos."""
    d = datetime.now(timezone.utc).date() + timedelta(days=1)
    while True:
        if d.isoweekday() != 7 and usadas.count(d) < 1:
            return d
        d += timedelta(days=1)


def _existe_borrador(categoria):
    """True si ya hay un borrador reciente sin publicar para esta categoría."""
    params = urllib.parse.urlencode({
        "select": "id",
        "categoria": f"eq.{categoria}",
        "publicado": "eq.false",
        "limit": 1,
    })
    res = gb.supabase_get("articulos_blog", params)
    return bool(res)


def guardar_borrador(art, categoria, fecha_pub):
    """Guarda el artículo como borrador con fecha de publicación programada."""
    slug = gb.slugify(art["titulo"]) + "-" + datetime.now().strftime("%Y%m")
    art["slug"] = slug
    art["categoria"] = categoria
    art["fecha_pub"] = fecha_pub.isoformat() + "T08:00:00+00:00"

    data = {
        "titulo":    art["titulo"],
        "slug":      slug,
        "resumen":   art.get("resumen", ""),
        "contenido": art["contenido"],
        "categoria": categoria,
        "tipo":      "ia",
        "publicado": False,
        "fecha_pub": art["fecha_pub"],
    }
    status = gb.supabase_post("articulos_blog", data)
    if status == 409:
        print(f"  ⚠️  Slug duplicado '{slug}', saltando…")
        return False
    if status not in (200, 201):
        print(f"  ❌  Error Supabase (status {status})")
        return False

    # Página HTML (oculta del índice hasta publicado=True)
    os.makedirs(BLOG_DIR, exist_ok=True)
    ruta = os.path.join(BLOG_DIR, f"{slug}.html")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(gb.plantilla_articulo(art))
    return True


def main():
    print("=" * 62)
    print(f"📅  Planificador de Blog — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 62)

    if not (SUPABASE_URL and SUPABASE_API_KEY and os.environ.get("ANTHROPIC_API_KEY")):
        print("❌ Faltan SUPABASE_URL, SUPABASE_API_KEY o ANTHROPIC_API_KEY")
        return

    fechas_usadas = []
    plan = []

    for categoria in gb.CATEGORIAS:
        nombre = gb.NOMBRE_CATEGORIA[categoria]
        print(f"\n📂 {nombre}")

        if _existe_borrador(categoria):
            print("  ⏭️  Ya hay un borrador pendiente para esta categoría, saltando…")
            continue

        convs = gb.obtener_convocatorias(categoria, limite=5)
        if not convs:
            print("  ⚠️  Sin convocatorias, saltando…")
            continue

        print(f"  📋 {len(convs)} convocatorias · 🤖 generando artículo con Claude…")
        art = gb.generar_articulo(categoria, convs)
        if not art or not art.get("titulo"):
            print("  ❌ Generación fallida")
            continue

        fecha_pub = _proxima_fecha(fechas_usadas)
        fechas_usadas.append(fecha_pub)

        print(f"  📝 {art['titulo'][:55]}{'…' if len(art['titulo']) > 55 else ''}")
        print(f"  📅 Programado: {fecha_pub.strftime('%A %d/%m/%Y')}")

        if guardar_borrador(art, categoria, fecha_pub):
            plan.append({
                "fecha":     fecha_pub,
                "categoria": nombre,
                "titulo":    art["titulo"],
                "slug":      art.get("slug", ""),
            })
            print(f"  ✅ Borrador guardado")
        time.sleep(4)

    # ── Plan de publicación ────────────────────────────────────────────────────
    print()
    print("=" * 62)
    print("📅  CALENDARIO DE PUBLICACIÓN")
    print("=" * 62)
    dias = {}
    for item in plan:
        d = item["fecha"].strftime("%A %d/%m")
        dias.setdefault(d, []).append(item)
    for dia, items in dias.items():
        print(f"\n🗓️  {dia.upper()}")
        for i in items:
            print(f"  [{i['categoria']}] {i['titulo'][:58]}")
            print(f"   → {BASE_URL}/blog/{i['slug']}.html")
    print()
    print(f"✅ {len(plan)} borrador(es) generado(s).")
    print("   Publicación automática: lunes y jueves (generar-blog.yml).")
    print("   Publicación manual: python3 publicar_programados.py")
    print("=" * 62)

    # El commit/push del HTML generado lo hace el propio workflow
    # (planificar-blog.yml → paso "Subir páginas HTML de borradores"), que ya
    # usa las credenciales persistidas de actions/checkout correctamente. Antes
    # había aquí un os.system() redundante con `git push` sin pull/rebase
    # previo ni comprobación de resultado (mismo patrón de bug arreglado hoy en
    # leer_boe.py); se retira en vez de duplicar la lógica en dos sitios.


if __name__ == "__main__":
    main()
