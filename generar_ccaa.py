"""
generar_ccaa.py — Genera páginas HTML estáticas por comunidad autónoma.

Consulta Supabase para cada CCAA y genera /ccaa/{slug}.html con las
convocatorias más recientes. Las páginas son estáticas (SEO-friendly)
y se regeneran en cada ejecución del workflow diario.

Uso:
  SUPABASE_URL=... SUPABASE_API_KEY=... WEB_REPO_PATH=. python3 generar_ccaa.py
"""

import os
import json
import html as html_lib
import re
import unicodedata
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from email.utils import parsedate_to_datetime

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
WEB_REPO_PATH    = Path(os.environ.get("WEB_REPO_PATH", "."))
ADSENSE_CLIENT   = "ca-pub-4832095429696459"

CCAA_DIR         = WEB_REPO_PATH / "ccaa"
SITEMAP_PATH     = WEB_REPO_PATH / "sitemap.xml"
CONVOCATORIA_DIR = WEB_REPO_PATH / "convocatoria"

HOY = datetime.now().strftime("%Y-%m-%d")
AÑO = datetime.now().year

MESES = ['enero','febrero','marzo','abril','mayo','junio',
         'julio','agosto','septiembre','octubre','noviembre','diciembre']
MESES_CORTO = ['ene','feb','mar','abr','may','jun',
               'jul','ago','sep','oct','nov','dic']

CCAA = [
    ("Andalucía",            "andalucia"),
    ("Aragón",               "aragon"),
    ("Asturias",             "asturias"),
    ("Baleares",             "baleares"),
    ("Canarias",             "canarias"),
    ("Cantabria",            "cantabria"),
    ("Castilla-La Mancha",   "castilla-la-mancha"),
    ("Castilla y León",      "castilla-leon"),
    ("Cataluña",             "cataluna"),
    ("Comunidad Valenciana", "comunidad-valenciana"),
    ("Extremadura",          "extremadura"),
    ("Galicia",              "galicia"),
    ("La Rioja",             "la-rioja"),
    ("Madrid",               "madrid"),
    ("Murcia",               "murcia"),
    ("Navarra",              "navarra"),
    ("País Vasco",           "pais-vasco"),
    ("Ceuta",                "ceuta"),
    ("Melilla",              "melilla"),
    ("Nacional/Estatal",     "nacional"),
]

SLUG_A_NOMBRE = {slug: nombre for nombre, slug in CCAA}


# ── Supabase ──────────────────────────────────────────────────────────────────

def consultar_convocatorias(ccaa_nombre, limite=40):
    params = urllib.parse.urlencode({
        'comunidad_autonoma': f'eq.{ccaa_nombre}',
        'order': 'fecha.desc',
        'limit': str(limite),
        'select': 'titulo,fecha,enlace,resumen_claude,cuerpo,categoria',
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
        print(f"  ❌ Error consultando {ccaa_nombre}: {e}")
        return []


# ── Utilidades ────────────────────────────────────────────────────────────────

def _parse_fecha(fecha):
    """Parsea fecha RFC ('Sat, 13 Jun 2026 …') o ISO. Devuelve datetime o None."""
    if not fecha:
        return None
    try:
        return parsedate_to_datetime(fecha)
    except Exception:
        try:
            return datetime.fromisoformat(fecha[:10])
        except Exception:
            return None


def formatear_fecha(fecha):
    """Fecha corta en español: '13 jun'. Igual que el render de 'BOE de hoy'."""
    d = _parse_fecha(fecha)
    if not d:
        return ''
    return f"{d.day} {MESES_CORTO[d.month-1]}"


def parsear_resumen(resumen_claude):
    """Parsea '3 PLAZAS - POLICÍA LOCAL - CÁDIZ' → {plazas, puesto, lugar}."""
    if not resumen_claude:
        return None
    limpio = re.sub(r'\*\*', '', resumen_claude)
    limpio = re.sub(r'#+\s', '', limpio).strip()
    partes = limpio.split(' - ')
    if len(partes) < 2:
        return None
    return {
        'plazas': partes[0].strip(),
        'puesto': partes[1].strip(),
        'lugar':  ' · '.join(p.strip() for p in partes[2:]),
    }


def extraer_organismo(titulo):
    """Extrae el organismo del título largo del BOE (título corto y legible)."""
    m = re.search(
        r',\s+(?:de la|del|de los|de las|de)\s+(.+?)'
        r'(?:,\s+(?:por la que|por el que|referente|en la que|sobre|relativa)|$)',
        titulo, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    partes = titulo.split(',')
    if len(partes) >= 2:
        return re.sub(r'^(de la |del |de los |de las |de )', '',
                      partes[1].strip(), flags=re.IGNORECASE)
    return titulo[:80]


def ref_boe_desde_enlace(enlace):
    """Extrae 'BOE-A-2026-12731' de la URL del BOE."""
    if not enlace:
        return ""
    m = re.search(r'id=(BOE-[A-Z]-\d{4}-\d+)', enlace)
    return m.group(1) if m else ""


def generar_slug(titulo, ref_boe=""):
    """Replica exacta de generar_slug() en leer_boe.py."""
    slug = titulo.lower()
    slug = unicodedata.normalize('NFKD', slug)
    slug = ''.join([c for c in slug if not unicodedata.combining(c)])
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    slug = re.sub(r'-+', '-', slug)
    slug = slug[:60]
    if ref_boe and ref_boe != "BOE":
        sufijo = re.sub(r'[^a-z0-9]+', '-', ref_boe.lower()).strip('-')
        return f"{slug}-{sufijo}.html"
    return f"{slug}.html"


def url_convocatoria(titulo, enlace_boe):
    """Devuelve la URL en oponoticias.com si existe la página, si no el BOE."""
    ref = ref_boe_desde_enlace(enlace_boe)
    slug = generar_slug(titulo, ref)
    if (CONVOCATORIA_DIR / slug).exists():
        return f"https://oponoticias.com/convocatoria/{slug.replace('.html', '')}", True
    return html_lib.escape(enlace_boe or '#'), False


def links_otras_ccaa(slug_actual):
    partes = []
    for nombre, slug in CCAA:
        if slug == slug_actual:
            continue
        partes.append(
            f'<a href="{slug}.html" class="ccaa-pill">{nombre}</a>'
        )
    return '\n          '.join(partes)


# ── Generador HTML ────────────────────────────────────────────────────────────

def generar_html(ccaa_nombre, slug, convocatorias):
    n = len(convocatorias)
    meta_desc = (f"Convocatorias de oposiciones en {ccaa_nombre} {AÑO} publicadas en el BOE. "
                 f"{n} plazas de empleo público actualizadas diariamente por OpoNoticias.")
    canonical = f"https://oponoticias.com/ccaa/{slug}"

    # Tarjetas de convocatorias
    tarjetas = []
    for c in convocatorias:
        titulo  = c.get('titulo', '')
        fecha   = formatear_fecha(c.get('fecha', ''))
        cat     = c.get('categoria', '') or ''
        enlace_boe = c.get('enlace', '')

        parsed    = parsear_resumen(c.get('resumen_claude'))
        plazas    = parsed['plazas'] if parsed else ''
        puesto    = parsed['puesto'] if parsed else ''
        organismo = extraer_organismo(titulo)

        url, es_interna = url_convocatoria(titulo, enlace_boe)
        rel   = '' if es_interna else ' rel="noopener" target="_blank"'
        label = '' if es_interna else ' ↗'

        plazas_html = f'<span class="conv-plazas">{html_lib.escape(plazas)}</span>' if plazas else ''
        cat_html    = f'<span class="conv-categoria">{html_lib.escape(cat)}</span>' if cat else ''
        puesto_html = f'<p class="conv-puesto">{html_lib.escape(puesto)}</p>' if puesto else ''

        tarjetas.append(f"""\
    <article class="conv-card">
      <div class="conv-meta">
        <span class="conv-fecha">{fecha}</span>
        {cat_html}
        {plazas_html}
      </div>
      <h2 class="conv-titulo"><a href="{url}"{rel}>{html_lib.escape(organismo)}{label}</a></h2>
      {puesto_html}
    </article>""")

    tarjetas_html = '\n'.join(tarjetas) if tarjetas else (
        '<p class="sin-resultados">No hay convocatorias recientes para esta comunidad. '
        'Vuelve mañana — actualizamos cada día laborable.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Oposiciones en {ccaa_nombre} {AÑO} | OpoNoticias</title>
  <meta name="description" content="{html_lib.escape(meta_desc)}">
  <link rel="canonical" href="{canonical}">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#5A5047">
  <script>document.documentElement.className += ' js';</script>

  <link rel="icon" type="image/svg+xml" href="../assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/style.css?v=6">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "Oposiciones en {ccaa_nombre} {AÑO}",
    "description": "{meta_desc.replace('"', '')}",
    "url": "{canonical}",
    "publisher": {{"@type": "Organization", "name": "OpoNoticias", "url": "https://oponoticias.com"}}
  }}
  </script>
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-4832095429696459" crossorigin="anonymous"></script>
</head>
<body>

  <header class="site-header">
    <div class="container">
      <nav class="nav" aria-label="Principal">
        <a href="../index.html" aria-label="OpoNoticias - Inicio"><img src="../assets/logo.svg" alt="OpoNoticias" class="nav-logo"></a>
        <div class="nav-links">
          <a href="../index.html#comunidades">Comunidades</a>
          <a href="../index.html#categorias">Categorías</a>
          <a href="../index.html#ultimas">Últimas</a>
          <a href="../index.html#como-funciona">Cómo funciona</a>
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
        <a href="../index.html">Inicio</a>
        <span class="sep">/</span>
        <a href="../index.html#comunidades">Comunidades</a>
        <span class="sep">/</span>
        <span aria-current="page">{ccaa_nombre}</span>
      </nav>

      <article class="legal-doc">
        <header class="article-header">
          <span class="article-tag">Comunidad Autónoma</span>
          <h1>Oposiciones en {ccaa_nombre} {AÑO}</h1>
          <div class="article-meta">
            <span>Actualizado: <b>{HOY}</b></span>
            &nbsp;·&nbsp;
            <span><b>{n}</b> convocatorias recientes</span>
          </div>
        </header>

        <div class="prose">
          <p class="lead">Todas las convocatorias de oposiciones en <strong>{ccaa_nombre}</strong> {AÑO}
          publicadas en el Boletín Oficial del Estado (BOE). OpoNoticias recopila y resume
          diariamente las nuevas plazas de empleo público para que puedas estar al día
          sin tener que leer el BOE.</p>
        </div>

        <div class="ccaa-convocatorias">
{tarjetas_html}
        </div>

        <div class="ccaa-otras">
          <h3>Oposiciones en otras comunidades</h3>
          <div class="ccaa-pills">
          {links_otras_ccaa(slug)}
          </div>
        </div>

      </article>
    </div>
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <img src="../assets/logo-white.svg" alt="OpoNoticias">
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
          <a href="../categoria/educacion.html">Educación</a>
          <a href="../categoria/sanidad.html">Sanidad</a>
          <a href="../categoria/justicia.html">Justicia</a>
          <a href="../categoria/administracion.html">Administración</a>
        </div>
        <div class="footer-col">
          <h4>Recursos</h4>
          <a href="../index.html#ultimas">Últimas convocatorias</a>
          <a href="../index.html#como-funciona">Cómo funciona</a>
          <a href="https://www.boe.es" rel="noopener" target="_blank">BOE oficial</a>
        </div>
        <div class="footer-col">
          <h4>Legal</h4>
          <a href="../aviso-legal.html">Aviso legal</a>
          <a href="../privacidad.html">Privacidad (RGPD)</a>
          <a href="../cookies.html">Cookies</a>
          <a href="mailto:info@oponoticias.com">info@oponoticias.com</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© {AÑO} OpoNoticias · oponoticias.com</span>
        <span>Fuente oficial: api.boe.es · Actualización diaria cada mañana</span>
      </div>
    </div>
  </footer>

  <script src="../assets/script.js?v=5" defer></script>
</body>
</html>"""


# ── Sitemap ───────────────────────────────────────────────────────────────────

def actualizar_sitemap(slugs_ccaa):
    """Añade las páginas CCAA al sitemap existente si no están ya."""
    if not SITEMAP_PATH.exists():
        print("⚠️  sitemap.xml no encontrado, omitiendo actualización.")
        return

    contenido = SITEMAP_PATH.read_text(encoding='utf-8')
    nuevas = []
    for slug in slugs_ccaa:
        url = f"https://oponoticias.com/ccaa/{slug}"
        if url not in contenido:
            nuevas.append(f"""  <url>
    <loc>{url}</loc>
    <lastmod>{HOY}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>""")

    if not nuevas:
        print("ℹ️  Páginas CCAA ya están en el sitemap.")
        return

    insertar = '\n'.join(nuevas) + '\n'
    contenido = contenido.replace('</urlset>', insertar + '</urlset>')
    SITEMAP_PATH.write_text(contenido, encoding='utf-8')
    print(f"✅ Sitemap actualizado con {len(nuevas)} páginas CCAA.")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not all([SUPABASE_URL, SUPABASE_API_KEY]):
        print("❌ Faltan variables de entorno: SUPABASE_URL, SUPABASE_API_KEY")
        raise SystemExit(1)

    CCAA_DIR.mkdir(parents=True, exist_ok=True)
    slugs_generados = []

    for ccaa_nombre, slug in CCAA:
        print(f"\n🗺️  {ccaa_nombre}...")
        convocatorias = consultar_convocatorias(ccaa_nombre)
        print(f"   {len(convocatorias)} convocatorias encontradas")

        html = generar_html(ccaa_nombre, slug, convocatorias)
        path = CCAA_DIR / f"{slug}.html"
        path.write_text(html, encoding='utf-8')
        slugs_generados.append(slug)
        print(f"   ✓ Generada: ccaa/{slug}.html")

    actualizar_sitemap(slugs_generados)
    print(f"\n✅ Listo. {len(slugs_generados)} páginas CCAA generadas en {CCAA_DIR}")
