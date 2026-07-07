"""
generar_convocatorias_hub.py — Genera /convocatorias.html, el índice general
de convocatorias de oposición (el "hub de hubs").

Por qué: /categoria/X y /ccaa/Y cubren cada dimensión por separado, pero
faltaba una página para búsquedas amplias como "convocatoria"/"convocatorias"
(en Search Console: 81 impresiones combinadas, ya en posición 4-6 — página 1
— pero 0 clics, porque lo que rankeaba era una ficha individual suelta, no
una página pensada para esa búsqueda genérica).

Selecciona las convocatorias más sustanciales y recientes (mismo criterio
anti-index-bloat que generar_cruces.py: fuera 1-plaza-fallback y trámites),
con diversidad por categoría, y enlaza a los hubs de categoría/CCAA para
repartir autoridad hacia abajo.

Uso:
  SUPABASE_URL=... SUPABASE_API_KEY=... WEB_REPO_PATH=. python3 generar_convocatorias_hub.py
"""

import os
import json
import html as html_lib
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

from web_utils import limpiar_hrefs
from leer_boe import _ficha_indexable
from boe_utils import parsear_resumen, extraer_organismo, formatear_fecha, url_convocatoria
from generar_categorias import CATEGORIAS
from generar_ccaa import CCAA

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
WEB_REPO_PATH    = Path(os.environ.get("WEB_REPO_PATH", "."))
ADSENSE_CLIENT   = "ca-pub-4832095429696459"

CONVOCATORIA_DIR = WEB_REPO_PATH / "convocatoria"
SITEMAP_PATH     = WEB_REPO_PATH / "sitemap.xml"
SALIDA           = WEB_REPO_PATH / "convocatorias.html"

HOY = datetime.now().strftime("%Y-%m-%d")
AÑO = datetime.now().year

# Cuántas destacadas mostrar y cuántas como máximo de la misma categoría
# (diversidad — evita que una categoría con mucho volumen monopolice el hub).
N_DESTACADAS       = 7
MAX_POR_CATEGORIA  = 2

# CCAA destacadas en los pills (más "Ver todas →"); mismo criterio que blog.html/footer.
CCAA_DESTACADAS = ["madrid", "andalucia", "cataluna", "comunidad-valenciana", "galicia"]


# ── Supabase ──────────────────────────────────────────────────────────────────

def consultar_todas_convocatorias(page_size=1000):
    """Trae TODAS las convocatorias en una sola pasada (paginado vía Range) —
    mismo patrón que generar_ccaa.py/generar_categorias.py: evita depender de
    un `limit` que el tope de filas de PostgREST podría truncar en silencio."""
    todas = []
    offset = 0
    while True:
        params = urllib.parse.urlencode({
            'order': 'fecha.desc',
            'select': 'titulo,fecha,enlace,resumen_claude,categoria,comunidad_autonoma',
        })
        url = f"{SUPABASE_URL}/rest/v1/convocatorias?{params}"
        headers = {
            'apikey': SUPABASE_API_KEY,
            'Authorization': f'Bearer {SUPABASE_API_KEY}',
            'Accept': 'application/json',
            'Range-Unit': 'items',
            'Range': f'{offset}-{offset + page_size - 1}',
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                pagina = json.loads(resp.read())
        except Exception as e:
            print(f"  ❌ Error consultando convocatorias (offset {offset}): {e}")
            break
        todas.extend(pagina)
        if len(pagina) < page_size:
            break
        offset += page_size
    return todas


# ── Selección ─────────────────────────────────────────────────────────────────

def _es_sustancial(c):
    """Mismo criterio anti-index-bloat que generar_cruces.py/leer_boe.py:
    fuera 1-plaza-fallback y trámites (correcciones, modificaciones...)."""
    parsed = parsear_resumen(c.get('resumen_claude'))
    plazas = parsed['plazas'] if parsed else ''
    return _ficha_indexable(plazas, c.get('titulo', ''))


def seleccionar_destacadas(todas, n=N_DESTACADAS, max_por_categoria=MAX_POR_CATEGORIA):
    """Las N convocatorias más sustanciales, priorizando las más recientes
    (la consulta ya viene ordenada por fecha.desc), con diversidad: máximo
    `max_por_categoria` de la misma categoría."""
    seleccionadas = []
    conteo_cat = {}
    for c in todas:
        if not _es_sustancial(c):
            continue
        cat = c.get('categoria', '') or ''
        if conteo_cat.get(cat, 0) >= max_por_categoria:
            continue
        seleccionadas.append(c)
        conteo_cat[cat] = conteo_cat.get(cat, 0) + 1
        if len(seleccionadas) >= n:
            break
    return seleccionadas


# ── Generador HTML ────────────────────────────────────────────────────────────

def _tarjeta(c):
    titulo     = c.get('titulo', '')
    fecha      = formatear_fecha(c.get('fecha', ''))
    categoria  = c.get('categoria', '') or ''
    comunidad  = c.get('comunidad_autonoma', '') or ''
    enlace_boe = c.get('enlace', '')

    parsed    = parsear_resumen(c.get('resumen_claude'))
    plazas    = parsed['plazas'] if parsed else ''
    organismo = extraer_organismo(titulo)

    url, es_interna = url_convocatoria(titulo, enlace_boe, CONVOCATORIA_DIR)
    rel   = '' if es_interna else ' rel="noopener" target="_blank"'
    label = '' if es_interna else ' ↗'

    ambito = "Ámbito nacional" if comunidad.lower() in (
        "", "nacional", "nacional/estatal", "estatal", "espana", "españa") else comunidad
    plazas_html = f'<span class="conv-plazas">{html_lib.escape(plazas)}</span>' if plazas else ''

    return f"""\
    <article class="conv-card">
      <div class="conv-meta">
        <span class="conv-fecha">{fecha}</span>
        {plazas_html}
      </div>
      <h2 class="conv-titulo"><a href="{url}"{rel}>{html_lib.escape(organismo)}{label}</a></h2>
      <p class="conv-puesto">{html_lib.escape(categoria.upper())} · {html_lib.escape(ambito)}</p>
    </article>"""


def generar_html(destacadas):
    tarjetas_html = '\n'.join(_tarjeta(c) for c in destacadas)

    pills_categorias = '\n          '.join(
        f'<a href="/categoria/{slug}" class="ccaa-pill">{nombre} →</a>'
        for nombre, slug, _desc in CATEGORIAS
    )
    ccaa_por_slug = {slug: nombre for nombre, slug in CCAA}
    pills_ccaa = '\n          '.join(
        f'<a href="/ccaa/{slug}" class="ccaa-pill">{ccaa_por_slug[slug]} →</a>'
        for slug in CCAA_DESTACADAS if slug in ccaa_por_slug
    )

    meta_desc = (f"Todas las convocatorias de oposiciones activas en España: educación, sanidad, "
                 f"justicia, seguridad y administración pública. Actualizado cada día a partir del BOE.")

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "¿Qué es una convocatoria de oposición?",
             "acceptedAnswer": {"@type": "Answer", "text":
              "Es el anuncio oficial, publicado en el Boletín Oficial del Estado (BOE) o en el "
              "boletín autonómico correspondiente, que abre el proceso selectivo para acceder a "
              "una plaza de empleo público. Incluye el número de plazas, los requisitos, el "
              "temario y el plazo de presentación de solicitudes."}},
            {"@type": "Question", "name": "¿Dónde se publican las convocatorias de oposiciones?",
             "acceptedAnswer": {"@type": "Answer", "text":
              "Las de ámbito estatal se publican en el BOE. Las autonómicas y locales suelen "
              "publicarse primero en el boletín de su comunidad o provincia, y después un "
              "extracto en el BOE. OpoNoticias rastrea el BOE cada día laborable y resume cada "
              "convocatoria nueva."}},
            {"@type": "Question", "name": "¿Cuánto tiempo hay para presentar la solicitud?",
             "acceptedAnswer": {"@type": "Answer", "text":
              "El plazo habitual es de 20 días hábiles desde el día siguiente a la publicación, "
              "aunque el plazo exacto lo fija siempre el texto oficial de cada convocatoria."}},
        ],
    }
    faq_schema_json = json.dumps(faq_schema, ensure_ascii=False, indent=2)
    faq_items_html = "".join(
        f'<details class="faq-item" style="background:var(--surface); border:1px solid var(--line); '
        f'border-radius:10px; padding:12px 16px; margin-bottom:8px;">'
        f'<summary style="cursor:pointer; font-weight:600; color:var(--ink);">{q["name"]}</summary>'
        f'<p style="margin:10px 0 0; line-height:1.6; color:var(--gray);">{q["acceptedAnswer"]["text"]}</p></details>'
        for q in faq_schema["mainEntity"]
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Convocatorias de oposiciones en España {AÑO} | OpoNoticias</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="https://oponoticias.com/convocatorias">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#5A5047">
  <script>document.documentElement.className += ' js';</script>

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="OpoNoticias">
  <meta property="og:title" content="Convocatorias de oposiciones en España {AÑO} | OpoNoticias">
  <meta property="og:description" content="Todas las convocatorias de oposiciones activas en España, organizadas por categoría y comunidad autónoma.">
  <meta property="og:url" content="https://oponoticias.com/convocatorias">

  <link rel="icon" type="image/svg+xml" href="assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/style.css?v=6">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "Convocatorias de oposiciones en España {AÑO}",
    "description": "{meta_desc}",
    "url": "https://oponoticias.com/convocatorias",
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
        <a href="/" aria-label="OpoNoticias - Inicio"><img src="assets/logo.svg" alt="OpoNoticias" class="nav-logo"></a>
        <div class="nav-links">
          <a href="/#comunidades">Comunidades</a>
          <a href="/#categorias">Categorías</a>
          <a href="/blog">Blog</a>
          <a href="/recursos">Recursos</a>
          <a href="/#como-funciona">Cómo funciona</a>
        </div>
        <div class="nav-cta">
          <div class="nav-social">
            <span class="nav-social-label">Síguenos</span>
            <a href="https://t.me/OPONOTICIAS" rel="noopener" target="_blank" aria-label="Telegram" title="Telegram"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg></a>
            <a href="https://www.facebook.com/profile.php?id=61590965302457" rel="noopener" target="_blank" aria-label="Facebook" title="Facebook"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.1 24 18.1 24 12.07z"/></svg></a>
            <a href="https://x.com/OpoNoticiasON" rel="noopener" target="_blank" aria-label="X" title="X"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
            <a href="https://www.instagram.com/oponoticiason/" rel="noopener" target="_blank" aria-label="Instagram" title="Instagram"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg></a>
            <a href="https://whatsapp.com/channel/0029Vb8BReo89ind8LpWxp26" rel="noopener" target="_blank" aria-label="WhatsApp" title="WhatsApp"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg></a>
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
        <a href="/">Inicio</a>
        <span class="sep">/</span>
        <span aria-current="page">Convocatorias</span>
      </nav>

      <div class="blog-hero">
        <span class="eyebrow">Boletín Oficial del Estado</span>
        <h1 class="section-title">Convocatorias de oposiciones en España</h1>
        <p class="section-lead">Estas son las convocatorias de empleo público más relevantes que siguen en plazo ahora mismo, de todas las categorías y comunidades autónomas. Se actualiza cada día laborable con lo publicado en el BOE.</p>
      </div>

      <div class="prose" style="margin-bottom:32px;">
        <h2 style="font-size:1.2rem; margin:0 0 10px;">¿Qué es una convocatoria de oposición?</h2>
        <p style="line-height:1.65; color:var(--gray);">
          Una convocatoria es el anuncio oficial que abre un proceso selectivo para acceder a una plaza de empleo público:
          fija el número de plazas, los requisitos para presentarse, el temario y, sobre todo, el plazo para solicitar
          participar. Las de ámbito estatal se publican en el <strong>BOE</strong>; las autonómicas y locales suelen
          aparecer primero en el boletín de su región o provincia. En ambos casos, el reloj empieza a correr el día
          siguiente a la publicación — normalmente hay <strong>20 días hábiles</strong> para presentar la solicitud,
          aunque el plazo exacto lo fija siempre el texto oficial de cada convocatoria.
        </p>
      </div>

      <h2 style="font-size:1.2rem; margin:0 0 16px;">Convocatorias destacadas</h2>
      <div class="ccaa-convocatorias">
{tarjetas_html}
      </div>

      <div class="ccaa-otras" style="margin-top:36px;">
        <h3>Explora por categoría</h3>
        <div class="ccaa-pills">
          {pills_categorias}
        </div>
      </div>

      <div class="ccaa-otras">
        <h3>Explora por comunidad autónoma</h3>
        <div class="ccaa-pills">
          {pills_ccaa}
          <a href="/#comunidades" class="ccaa-pill">Ver todas →</a>
        </div>
      </div>

      <div class="prose" style="margin-top:36px;">
        <h2 style="font-size:1.2rem; margin:0 0 10px;">Preguntas frecuentes</h2>
        <div class="faq-list">{faq_items_html}</div>
      </div>

    </div>
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <img src="assets/logo-white.svg" alt="OpoNoticias">
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
          <a href="/categoria/educacion">Educación</a>
          <a href="/categoria/sanidad">Sanidad</a>
          <a href="/categoria/justicia">Justicia</a>
          <a href="/categoria/administracion">Administración</a>
        </div>
        <div class="footer-col">
          <h4>Recursos</h4>
          <a href="/#ultimas">Últimas convocatorias</a>
          <a href="/#como-funciona">Cómo funciona</a>
          <a href="https://www.boe.es" rel="noopener" target="_blank">BOE oficial</a>
        </div>
        <div class="footer-col">
          <h4>Legal</h4>
          <a href="/aviso-legal">Aviso legal</a>
          <a href="/privacidad">Privacidad (RGPD)</a>
          <a href="/cookies">Cookies</a>
          <a href="mailto:info@oponoticias.com">info@oponoticias.com</a>
        </div>
        <div class="footer-col">
          <h4>Comunidades</h4>
          <a href="/ccaa/madrid">Madrid</a>
          <a href="/ccaa/andalucia">Andalucía</a>
          <a href="/ccaa/cataluna">Cataluña</a>
          <a href="/ccaa/comunidad-valenciana">C. Valenciana</a>
          <a href="/#comunidades">Ver todas →</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© {AÑO} OpoNoticias · oponoticias.com</span>
        <span>Fuente oficial: api.boe.es · Actualización diaria cada mañana</span>
      </div>
    </div>
  </footer>

  <script src="assets/script.js?v=7" defer></script>
</body>
</html>"""


# ── Sitemap ───────────────────────────────────────────────────────────────────

def actualizar_sitemap():
    """Añade /convocatorias al sitemap si no está ya (regenerar_sitemap() en
    leer_boe.py también la incluye en su lista base; esto es un respaldo por
    si este script corre antes o de forma aislada)."""
    if not SITEMAP_PATH.exists():
        print("⚠️  sitemap.xml no encontrado, omitiendo actualización.")
        return
    contenido = SITEMAP_PATH.read_text(encoding='utf-8')
    url = "https://oponoticias.com/convocatorias"
    if url in contenido:
        print("ℹ️  /convocatorias ya está en el sitemap.")
        return
    entrada = f"""  <url>
    <loc>{url}</loc>
    <lastmod>{HOY}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>"""
    contenido = contenido.replace('</urlset>', entrada + '\n</urlset>')
    SITEMAP_PATH.write_text(contenido, encoding='utf-8')
    print("✅ /convocatorias añadida al sitemap.")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not all([SUPABASE_URL, SUPABASE_API_KEY]):
        print("❌ Faltan variables de entorno: SUPABASE_URL, SUPABASE_API_KEY")
        raise SystemExit(1)

    todas = consultar_todas_convocatorias()
    print(f"📥 {len(todas)} convocatorias cargadas.")

    destacadas = seleccionar_destacadas(todas)
    if not destacadas:
        print("⚠️  Sin convocatorias sustanciales para destacar, no se genera la página.")
        raise SystemExit(0)

    html_out = generar_html(destacadas)
    SALIDA.write_text(limpiar_hrefs(html_out), encoding='utf-8')
    actualizar_sitemap()

    print(f"\n✅ Listo. {len(destacadas)} convocatorias destacadas en convocatorias.html:")
    for c in destacadas:
        print(f"   · {c.get('categoria','')} — {extraer_organismo(c.get('titulo',''))}")
