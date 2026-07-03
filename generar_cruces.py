"""
generar_cruces.py — Genera landing pages de la INTERSECCIÓN categoría×CCAA
("Oposiciones de Sanidad en Madrid 2026"), enriquecidas y válidas para
SEO/AdSense: solo cuando hay convocatorias reales de sobra que mostrar.

Por qué: /categoria/X y /ccaa/Y cubren cada dimensión por separado, pero la
gente busca la combinación exacta ("oposiciones enfermería madrid 2026"),
que tiene menos competencia y más intención. Para NO repetir el error del
contenido fino (588 fichas → AdSense rechazado), esta vez la generación es
selectiva: si una combinación no tiene al menos MIN_SUSTANCIALES
convocatorias de valor real (no 1-plaza-fallback, no trámites — mismo
criterio que _ficha_indexable en leer_boe.py), sencillamente NO se genera
la página. Nada de placeholders vacíos ni noindex masivo.

Uso:
  SUPABASE_URL=... SUPABASE_API_KEY=... WEB_REPO_PATH=. python3 generar_cruces.py
"""

import os
import json
import html as html_lib
import re
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

from web_utils import limpiar_hrefs
from leer_boe import CONTEXTO_CATEGORIA, _ficha_indexable
from generar_categorias import (
    CATEGORIAS, parsear_resumen, extraer_organismo, formatear_fecha,
    url_convocatoria,
)
from generar_ccaa import CCAA

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
WEB_REPO_PATH    = Path(os.environ.get("WEB_REPO_PATH", "."))
ADSENSE_CLIENT   = "ca-pub-4832095429696459"

CATEGORIA_DIR = WEB_REPO_PATH / "categoria"
SITEMAP_PATH  = WEB_REPO_PATH / "sitemap.xml"

HOY = datetime.now().strftime("%Y-%m-%d")
AÑO = datetime.now().year

# Mínimo de convocatorias "de valor" (varias plazas, no trámite) para que la
# combinación merezca su propia página. Por debajo de esto, no se genera nada.
MIN_SUSTANCIALES = 3

# "Nacional/Estatal" no aporta especificidad regional real sobre /categoria/X
# (ya la incluye la propia categoría), así que se excluye del cruce.
CCAA_CRUCE = [(nombre, slug) for nombre, slug in CCAA if slug != "nacional"]


# ── Supabase ──────────────────────────────────────────────────────────────────

def consultar_convocatorias(cat_nombre, ccaa_nombre, limite=30):
    params = urllib.parse.urlencode({
        'categoria': f'eq.{cat_nombre}',
        'comunidad_autonoma': f'eq.{ccaa_nombre}',
        'order': 'fecha.desc',
        'limit': str(limite),
        'select': 'titulo,fecha,enlace,resumen_claude,cuerpo',
    })
    url = f"{SUPABASE_URL}/rest/v1/convocatorias?{params}"
    headers = {
        'apikey': SUPABASE_API_KEY,
        'Authorization': f'Bearer {SUPABASE_API_KEY}',
        'Accept': 'application/json',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ❌ Error consultando {cat_nombre} × {ccaa_nombre}: {e}")
        return []


def _n_sustanciales(convocatorias):
    """Cuenta cuántas convocatorias son 'de valor' (no 1-plaza-fallback, no
    trámite), con el mismo criterio que las fichas individuales."""
    n = 0
    for c in convocatorias:
        parsed = parsear_resumen(c.get('resumen_claude'))
        plazas = parsed['plazas'] if parsed else ''
        if _ficha_indexable(plazas, c.get('titulo', '')):
            n += 1
    return n


# ── Contenido enriquecido ────────────────────────────────────────────────────

def _bloque_enriquecido(cat_nombre, cat_slug, ccaa_nombre, ccaa_slug, n_total, n_sustanciales):
    contexto = CONTEXTO_CATEGORIA.get(cat_nombre, CONTEXTO_CATEGORIA["Administración"])

    intro = (f"En <strong>{ccaa_nombre}</strong> hay actualmente <strong>{n_total} "
             f"convocatorias</strong> de {cat_nombre.lower()} publicadas en el BOE, "
             f"de las cuales {n_sustanciales} ofrecen varias plazas. Esta página reúne "
             f"todas las que siguen en plazo y se actualiza cada día laborable con las "
             f"nuevas publicaciones del Boletín Oficial del Estado.")

    faqs = [
        (f"¿Cuántas oposiciones de {cat_nombre.lower()} hay ahora en {ccaa_nombre}?",
         f"Ahora mismo hay {n_total} convocatorias publicadas en el BOE para {ccaa_nombre} "
         f"en el área de {cat_nombre.lower()}. El número cambia cada semana; esta página se "
         f"actualiza automáticamente con cada nueva publicación."),
        (f"¿Quién convoca estas plazas en {ccaa_nombre}?",
         f"Dependiendo del cuerpo, las convocatorias las publican la administración "
         f"autonómica de {ccaa_nombre}, los ayuntamientos y organismos locales del "
         f"territorio, o la Administración General del Estado cuando la plaza es de "
         f"ámbito estatal pero destino en {ccaa_nombre}."),
        ("¿Dónde consulto las bases oficiales de cada convocatoria?",
         "Cada convocatoria de esta lista enlaza a su ficha con el resumen y el enlace "
         "directo al texto oficial publicado en el BOE, donde figuran los requisitos, "
         "el plazo de solicitud y el baremo completo."),
    ]
    faq_items = "".join(
        f'<details class="faq-item" style="background:var(--surface); border:1px solid var(--line); '
        f'border-radius:10px; padding:12px 16px; margin-bottom:8px;">'
        f'<summary style="cursor:pointer; font-weight:600; color:var(--ink);">{q}</summary>'
        f'<p style="margin:10px 0 0; line-height:1.6; color:var(--gray);">{a}</p></details>'
        for q, a in faqs
    )
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    }
    faq_schema_json = json.dumps(faq_schema, ensure_ascii=False, indent=2)

    bloque = f"""
        <div class="prose">
          <p class="lead">{intro}</p>
          <p style="line-height:1.65;">{contexto}</p>

          <h2 style="font-size:1.2rem; margin:28px 0 10px;">Cómo seguir estas oposiciones en {ccaa_nombre}</h2>
          <ol style="line-height:1.7; padding-left:1.2em;">
            <li>Revisa el listado de abajo: cada convocatoria enlaza a su ficha con el resumen, las plazas y el enlace directo al texto oficial del BOE.</li>
            <li>Comprueba siempre el plazo de solicitud en las bases; suele ser de 20 días hábiles desde la publicación, pero el plazo vinculante es el que figura en el texto oficial.</li>
            <li>Si tu perfil encaja con varias convocatorias de {cat_nombre.lower()} en {ccaa_nombre}, prioriza las que tengan más plazas: suelen tener mejor ratio de aprobados por plaza convocada.</li>
            <li>Suscríbete al canal de Telegram de OpoNoticias para recibir un aviso el mismo día en que se publique una nueva convocatoria de esta área.</li>
          </ol>

          <h2 style="font-size:1.2rem; margin:28px 0 10px;">Preguntas frecuentes</h2>
          <div class="faq-list">{faq_items}</div>
        </div>"""
    return bloque, faq_schema_json


# ── Generador HTML ────────────────────────────────────────────────────────────

def generar_html(cat_nombre, cat_slug, ccaa_nombre, ccaa_slug, convocatorias, n_sustanciales):
    n = len(convocatorias)
    meta_desc = (f"Oposiciones de {cat_nombre.lower()} en {ccaa_nombre} {AÑO}: {n} convocatorias "
                 f"publicadas en el BOE, resumidas y actualizadas cada día por OpoNoticias.")
    canonical = f"https://oponoticias.com/categoria/{cat_slug}/{ccaa_slug}"

    tarjetas = []
    for c in convocatorias:
        titulo, fecha = c.get('titulo', ''), formatear_fecha(c.get('fecha', ''))
        enlace_boe = c.get('enlace', '')
        parsed = parsear_resumen(c.get('resumen_claude'))
        plazas = parsed['plazas'] if parsed else ''
        puesto = parsed['puesto'] if parsed else ''
        organismo = extraer_organismo(titulo)
        url, es_interna = url_convocatoria(titulo, enlace_boe)
        rel = '' if es_interna else ' rel="noopener" target="_blank"'
        label = '' if es_interna else ' ↗'
        plazas_html = f'<span class="conv-plazas">{html_lib.escape(plazas)}</span>' if plazas else ''
        puesto_html = f'<p class="conv-puesto">{html_lib.escape(puesto)}</p>' if puesto else ''
        tarjetas.append(f"""\
    <article class="conv-card">
      <div class="conv-meta">
        <span class="conv-fecha">{fecha}</span>
        {plazas_html}
      </div>
      <h2 class="conv-titulo"><a href="{url}"{rel}>{html_lib.escape(organismo)}{label}</a></h2>
      {puesto_html}
    </article>""")
    tarjetas_html = '\n'.join(tarjetas)

    bloque_extra, faq_schema_json = _bloque_enriquecido(
        cat_nombre, cat_slug, ccaa_nombre, ccaa_slug, n, n_sustanciales)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Oposiciones de {cat_nombre} en {ccaa_nombre} {AÑO} | OpoNoticias</title>
  <meta name="description" content="{html_lib.escape(meta_desc)}">
  <link rel="canonical" href="{canonical}">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#5A5047">
  <script>document.documentElement.className += ' js';</script>

  <link rel="icon" type="image/svg+xml" href="../../assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../../assets/style.css?v=6">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "Oposiciones de {cat_nombre} en {ccaa_nombre} {AÑO}",
    "description": "{meta_desc.replace('"', '')}",
    "url": "{canonical}",
    "publisher": {{"@type": "Organization", "name": "OpoNoticias", "url": "https://oponoticias.com"}}
  }}
  </script>
  <script type="application/ld+json">
  {faq_schema_json}
  </script>
</head>
<body>

  <header class="site-header">
    <div class="container">
      <nav class="nav" aria-label="Principal">
        <a href="../../index.html" aria-label="OpoNoticias - Inicio"><img src="../../assets/logo.svg" alt="OpoNoticias" class="nav-logo"></a>
        <div class="nav-links">
          <a href="../../index.html#comunidades">Comunidades</a>
          <a href="../../index.html#categorias">Categorías</a>
          <a href="../../boe-hoy">El BOE de hoy</a>
          <a href="../../blog">Blog</a>
          <a href="../../index.html#como-funciona">Cómo funciona</a>
        </div>
        <div class="nav-cta">
          <div class="nav-social">
            <span class="nav-social-label">Síguenos</span>
            <a href="https://t.me/OPONOTICIAS" rel="noopener" target="_blank" aria-label="Telegram" title="Telegram"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg></a>
            <a href="https://www.facebook.com/profile.php?id=61590965302457" rel="noopener" target="_blank" aria-label="Facebook" title="Facebook"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.1 24 18.1 24 12.07z"/></svg></a>
            <a href="https://x.com/OpoNoticiasON" rel="noopener" target="_blank" aria-label="X" title="X"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
            <a href="mailto:info@oponoticias.com" aria-label="Email" title="info@oponoticias.com"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M2 4h20c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H2c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm10 7L2.5 6h19L12 11zm0 2.2L2 7.3V18h20V7.3l-10 5.9z"/></svg></a>
          </div>
        </div>
        <button class="nav-toggle" aria-label="Abrir menú" aria-expanded="false"><span></span><span></span><span></span></button>
      </nav>
    </div>
  </header>

  <main>
    <div class="container">
      <nav class="breadcrumb" aria-label="Migas de pan">
        <a href="../../index.html">Inicio</a>
        <span class="sep">/</span>
        <a href="../../categoria/{cat_slug}">{cat_nombre}</a>
        <span class="sep">/</span>
        <span aria-current="page">{ccaa_nombre}</span>
      </nav>

      <article class="legal-doc">
        <header class="article-header">
          <span class="article-tag">{cat_nombre} · {ccaa_nombre}</span>
          <h1>Oposiciones de {cat_nombre} en {ccaa_nombre} {AÑO}</h1>
          <div class="article-meta">
            <span>Actualizado: <b>{HOY}</b></span>
            &nbsp;·&nbsp;
            <span><b>{n}</b> convocatorias</span>
          </div>
        </header>
{bloque_extra}

        <div class="ccaa-convocatorias">
{tarjetas_html}
        </div>

        <div class="ccaa-otras">
          <h3>Sigue explorando</h3>
          <div class="ccaa-pills">
          <a href="../../categoria/{cat_slug}" class="ccaa-pill">Todas las de {cat_nombre} →</a>
          <a href="../../ccaa/{ccaa_slug}" class="ccaa-pill">Todas las de {ccaa_nombre} →</a>
          </div>
        </div>
      </article>
    </div>
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <img src="../../assets/logo-white.svg" alt="OpoNoticias">
          <p>Las convocatorias de oposiciones del BOE, resumidas en lenguaje claro y organizadas por categoría.</p>
          <div class="footer-social">
            <a href="https://t.me/OPONOTICIAS" rel="noopener" target="_blank" aria-label="Telegram" title="Telegram"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg></a>
            <a href="https://www.facebook.com/profile.php?id=61590965302457" rel="noopener" target="_blank" aria-label="Facebook" title="Facebook"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.1 24 18.1 24 12.07z"/></svg></a>
            <a href="https://x.com/OpoNoticiasON" rel="noopener" target="_blank" aria-label="X" title="X"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
            <a href="mailto:info@oponoticias.com" aria-label="Email" title="info@oponoticias.com"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M2 4h20c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H2c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm10 7L2.5 6h19L12 11zm0 2.2L2 7.3V18h20V7.3l-10 5.9z"/></svg></a>
          </div>
        </div>
        <div class="footer-col">
          <h4>Categorías</h4>
          <a href="../../categoria/educacion">Educación</a>
          <a href="../../categoria/sanidad">Sanidad</a>
          <a href="../../categoria/justicia">Justicia</a>
          <a href="../../categoria/administracion">Administración</a>
        </div>
        <div class="footer-col">
          <h4>Recursos</h4>
          <a href="../../index.html#ultimas">Últimas convocatorias</a>
          <a href="../../recursos">Recursos gratis</a>
          <a href="https://www.boe.es" rel="noopener" target="_blank">BOE oficial</a>
        </div>
        <div class="footer-col">
          <h4>Legal</h4>
          <a href="../../aviso-legal">Aviso legal</a>
          <a href="../../privacidad">Privacidad (RGPD)</a>
          <a href="../../cookies">Cookies</a>
          <a href="mailto:info@oponoticias.com">info@oponoticias.com</a>
        </div>
        <div class="footer-col">
          <h4>Comunidades</h4>
          <a href="../../ccaa/madrid">Madrid</a>
          <a href="../../ccaa/andalucia">Andalucía</a>
          <a href="../../ccaa/cataluna">Cataluña</a>
          <a href="../../ccaa/comunidad-valenciana">C. Valenciana</a>
          <a href="../../index.html#comunidades">Ver todas →</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© {AÑO} OpoNoticias · oponoticias.com</span>
        <span>Fuente oficial: api.boe.es · Actualización diaria cada mañana</span>
      </div>
    </div>
  </footer>

  <script src="../../assets/script.js?v=6" defer></script>
</body>
</html>"""


# ── Sitemap ───────────────────────────────────────────────────────────────────

def actualizar_sitemap(urls_nuevas):
    if not SITEMAP_PATH.exists():
        print("⚠️  sitemap.xml no encontrado, omitiendo actualización.")
        return
    contenido = SITEMAP_PATH.read_text(encoding='utf-8')
    nuevas = []
    for url in urls_nuevas:
        if url not in contenido:
            nuevas.append(f"""  <url>
    <loc>{url}</loc>
    <lastmod>{HOY}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>""")
    if not nuevas:
        print("ℹ️  Páginas de cruce ya están en el sitemap.")
        return
    contenido = contenido.replace('</urlset>', '\n'.join(nuevas) + '\n</urlset>')
    SITEMAP_PATH.write_text(contenido, encoding='utf-8')
    print(f"✅ Sitemap actualizado con {len(nuevas)} páginas de cruce.")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not all([SUPABASE_URL, SUPABASE_API_KEY]):
        print("❌ Faltan variables de entorno: SUPABASE_URL, SUPABASE_API_KEY")
        raise SystemExit(1)

    generadas, saltadas = [], 0
    urls_nuevas = []

    for cat_nombre, cat_slug, _desc in CATEGORIAS:
        cat_dir = CATEGORIA_DIR / cat_slug
        for ccaa_nombre, ccaa_slug in CCAA_CRUCE:
            convocatorias = consultar_convocatorias(cat_nombre, ccaa_nombre)
            n_sust = _n_sustanciales(convocatorias)
            if n_sust < MIN_SUSTANCIALES:
                saltadas += 1
                continue

            cat_dir.mkdir(parents=True, exist_ok=True)
            html_out = generar_html(cat_nombre, cat_slug, ccaa_nombre, ccaa_slug,
                                     convocatorias, n_sust)
            path = cat_dir / f"{ccaa_slug}.html"
            path.write_text(limpiar_hrefs(html_out), encoding='utf-8')
            url = f"https://oponoticias.com/categoria/{cat_slug}/{ccaa_slug}"
            urls_nuevas.append(url)
            generadas.append((cat_slug, ccaa_slug, n_sust))
            print(f"  ✓ {cat_slug}/{ccaa_slug}.html ({n_sust} sustanciales de {len(convocatorias)})")

    if urls_nuevas:
        actualizar_sitemap(urls_nuevas)

    print(f"\n✅ Listo. {len(generadas)} páginas de cruce generadas · "
          f"{saltadas} combinaciones sin contenido suficiente (< {MIN_SUSTANCIALES}).")
