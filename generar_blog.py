#!/usr/bin/env python3
"""
generar_blog.py — Genera artículos de blog con Claude para OpoNoticias.

Para cada categoría activa:
  1. Lee convocatorias reales de Supabase.
  2. Genera un artículo humano y optimizado para SEO con Claude.
  3. Lo guarda en la tabla articulos_blog (para el listado de la portada).
  4. Escribe una página HTML estática independiente en /blog/<slug>.html
     (con meta tags, Open Graph, datos estructurados Article y breadcrumb).
  5. Regenera el índice /blog.html con todos los artículos.
  6. Regenera /sitemap-blog.xml para que Google indexe cada artículo.

Frecuencia recomendada: semanal (lunes). Máx. 2 artículos por ejecución.
"""

import os
import re
import html
import json
import time
import random
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# ── Configuración ──────────────────────────────────────────────────────────────

SUPABASE_URL      = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY  = os.environ.get("SUPABASE_API_KEY", "")   # service_role key
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

BASE_URL = "https://oponoticias.com"
BLOG_DIR = "blog"

HEADERS_SB = {
    "apikey": SUPABASE_API_KEY,
    "Authorization": f"Bearer {SUPABASE_API_KEY}",
    "Content-Type": "application/json",
}

HEADERS_AN = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

CATEGORIAS = [
    "educacion", "sanidad", "administracion", "justicia",
    "seguridad", "hacienda", "correos", "tecnica",
]

NOMBRE_CATEGORIA = {
    "educacion": "Educación", "sanidad": "Sanidad",
    "administracion": "Administración", "justicia": "Justicia",
    "seguridad": "Seguridad", "hacienda": "Hacienda",
    "correos": "Correos", "tecnica": "Técnica",
}

FUENTES_REFERENCIA = [
    {"nombre": "BOE oficial", "url": "https://www.boe.es"},
    {"nombre": "el portal del INAP", "url": "https://www.inap.es"},
    {"nombre": "el SEPE", "url": "https://www.sepe.es"},
]

MAX_ARTICULOS_POR_EJECUCION = 3
DIAS_ENTRE_ARTICULOS = 25  # no regenerar una categoría hasta pasados ~3-4 semanas

# ── Helpers de texto ─────────────────────────────────────────────────────────

def slugify(text):
    text = text.lower()
    reemplazos = {'á':'a','à':'a','ä':'a','â':'a','é':'e','è':'e','ë':'e','ê':'e',
                  'í':'i','ì':'i','ï':'i','î':'i','ó':'o','ò':'o','ö':'o','ô':'o',
                  'ú':'u','ù':'u','ü':'u','û':'u','ñ':'n','ç':'c'}
    for a, b in reemplazos.items():
        text = text.replace(a, b)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text.strip())
    text = re.sub(r'-+', '-', text)
    return text[:70].strip('-')


def md_inline(texto):
    """Convierte negritas y enlaces markdown en HTML (a nivel de línea)."""
    # Escapar HTML primero para seguridad
    texto = html.escape(texto, quote=False)
    # Negritas **texto**
    texto = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', texto)
    # Enlaces [texto](url)
    def _link(m):
        label, url = m.group(1), m.group(2)
        if url.startswith("http") and "oponoticias.com" not in url:
            return f'<a href="{url}" rel="noopener" target="_blank">{label}</a>'
        return f'<a href="{url}">{label}</a>'
    texto = re.sub(r'\[(.+?)\]\((.+?)\)', _link, texto)
    return texto


def markdown_a_html(md):
    """Conversor de markdown acotado al formato que genera el modelo."""
    lineas = md.split("\n")
    html_out = []
    parrafo = []
    lista = []

    def cerrar_parrafo():
        if parrafo:
            html_out.append("<p>" + md_inline(" ".join(parrafo)) + "</p>")
            parrafo.clear()

    def cerrar_lista():
        if lista:
            items = "".join(f"<li>{md_inline(li)}</li>" for li in lista)
            html_out.append(f"<ul>{items}</ul>")
            lista.clear()

    for linea in lineas:
        l = linea.rstrip()
        if not l.strip():
            cerrar_parrafo(); cerrar_lista(); continue
        if l.startswith("### "):
            cerrar_parrafo(); cerrar_lista()
            html_out.append(f"<h3>{md_inline(l[4:].strip())}</h3>")
        elif l.startswith("## "):
            cerrar_parrafo(); cerrar_lista()
            html_out.append(f"<h2>{md_inline(l[3:].strip())}</h2>")
        elif l.startswith("# "):
            # El H1 lo pone la plantilla con el título; lo ignoramos aquí
            cerrar_parrafo(); cerrar_lista()
        elif re.match(r'^[-*]\s+', l):
            cerrar_parrafo()
            lista.append(re.sub(r'^[-*]\s+', '', l).strip())
        else:
            cerrar_lista()
            parrafo.append(l.strip())

    cerrar_parrafo(); cerrar_lista()
    return "\n".join(html_out)


def fecha_es(dt):
    meses = ["enero","febrero","marzo","abril","mayo","junio","julio",
             "agosto","septiembre","octubre","noviembre","diciembre"]
    return f"{dt.day} de {meses[dt.month-1]} de {dt.year}"


# ── Supabase ────────────────────────────────────────────────────────────────

def supabase_get(table, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    req = urllib.request.Request(url, headers=HEADERS_SB)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ⚠️  Error Supabase GET ({table}): {e}")
        return []


def supabase_post(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={**HEADERS_SB, "Prefer": "return=minimal"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return 409
        print(f"  ⚠️  Error Supabase POST ({table}): {e.code} — {e.read().decode()[:200]}")
        return e.code
    except Exception as e:
        print(f"  ⚠️  Error Supabase POST ({table}): {e}")
        return 0


# ── Claude ─────────────────────────────────────────────────────────────────

def claude(prompt, max_tokens=4000):
    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers=HEADERS_AN)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
            return data["content"][0]["text"].strip()
    except Exception as e:
        print(f"  ⚠️  Error Claude: {e}")
        return None


# ── Generación de artículo ───────────────────────────────────────────────────

def obtener_convocatorias(categoria, limite=5):
    # La BD guarda la categoría con mayúscula y acento ("Sanidad", "Administración"…)
    nombre = NOMBRE_CATEGORIA.get(categoria, categoria)
    params = urllib.parse.urlencode({
        "select": "titulo,resumen,resumen_claude,cuerpo,comunidad_autonoma,plazas",
        "categoria": f"eq.{nombre}",
        "order": "created_at.desc",
        "limit": limite,
    })
    return supabase_get("convocatorias", params)


def articulo_reciente(categoria):
    params = urllib.parse.urlencode({
        "select": "fecha_pub", "categoria": f"eq.{categoria}",
        "order": "fecha_pub.desc", "limit": 1,
    })
    res = supabase_get("articulos_blog", params)
    if not res:
        return False
    try:
        f = datetime.fromisoformat(res[0]["fecha_pub"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - f).days < DIAS_ENTRE_ARTICULOS
    except Exception:
        return False


def generar_articulo(categoria, convocatorias):
    año = datetime.now().year
    nombre = NOMBRE_CATEGORIA[categoria]

    contexto = ""
    for i, c in enumerate(convocatorias, 1):
        contexto += f"{i}. {c.get('titulo','')}"
        # resumen_claude = línea compacta IA: "3 PLAZAS - POLICÍA LOCAL - MADRID"
        linea_ia = c.get("resumen_claude") or c.get("cuerpo") or ""
        if linea_ia:
            contexto += f"\n   ↳ {linea_ia}"
        if c.get("plazas"):
            contexto += f" ({c['plazas']} plazas)"
        if c.get("comunidad_autonoma"):
            contexto += f" — {c['comunidad_autonoma']}"
        resumen_txt = c.get('resumen') or ''
        contexto += f"\n   {resumen_txt[:200]}\n\n"

    fuente = random.choice(FUENTES_REFERENCIA)

    prompt = f"""Eres periodista especializado en oposiciones y empleo público en España. Has cubierto el sector durante años y escribes como alguien que conoce de primera mano lo que vive un opositor: la espera del BOE, los nervios de las fechas, las dudas sobre requisitos. Escribe para OpoNoticias un artículo sobre las oposiciones de {nombre} en {año}.

CONVOCATORIAS REALES PUBLICADAS (son los únicos datos verificados; no inventes cifras, fechas ni plazas que no aparezcan aquí):
{contexto}

CÓMO DEBES ESCRIBIR (lo más importante):
- Escribe como una persona, no como una IA. Habla directamente al lector ("si te presentas", "te conviene saber").
- Varía la longitud de las frases. Mezcla frases cortas y contundentes con otras más largas. El ritmo monótono delata el texto automático.
- Empieza con un gancho concreto: un dato real de las convocatorias de arriba, una fecha o un número de plazas. NUNCA empieces con "En el mundo actual", "Las oposiciones son una de las mejores opciones" o "Es importante destacar".
- Da contexto útil de verdad: a quién va dirigida, qué titulación suele pedirse, qué conviene preparar. Si no tienes el dato exacto, habla en general sin inventar números.
- PROHIBIDO usar muletillas de IA: "En resumen", "En definitiva", "Cabe destacar", "Es fundamental", "el mundo de las oposiciones", "embarcarte en", "abre las puertas a", "no es tarea fácil", ni listas de tres adjetivos.
- Evita las viñetas salvo que aporten algo real (requisitos concretos). Prefiere la prosa.

ESTRUCTURA Y SEO:
- Entre 900 y 1300 palabras de contenido real.
- Usa ## para H2 y ### para H3. Que los subtítulos contengan lo que la gente busca ("Requisitos", "Plazas convocadas", "Fechas y plazos", "Cómo prepararte").
- Pon en **negrita** los términos clave de forma natural (1-3 por sección).
- Incluye 3 enlaces internos dentro de frases, eligiendo entre: [oposiciones de Educación](/categoria/educacion.html), [Sanidad](/categoria/sanidad.html), [Administración](/categoria/administracion.html), [Justicia](/categoria/justicia.html), [Seguridad](/categoria/seguridad.html), [Hacienda](/categoria/hacienda.html), [Correos](/categoria/correos.html).
- Incluye 1 enlace externo natural a {fuente['nombre']}: [{fuente['nombre']}]({fuente['url']}).
- Añade al final "## Preguntas frecuentes" con 3 preguntas reales (cada una con ### y respuesta de 2-3 frases). Ayuda a aparecer en resultados destacados de Google.
- Cierra con un párrafo breve y honesto invitando a seguir las novedades en el canal de Telegram [OpoNoticias](https://t.me/OPONOTICIAS), sin sonar a anuncio.

DEVUELVE SOLO ESTE JSON (sin ```, sin texto antes ni después):
{{
  "titulo": "Título de máximo 60 caracteres, palabra clave al principio, sin clickbait",
  "resumen": "Meta descripción de 150-160 caracteres, atractiva y con la palabra clave",
  "contenido": "Artículo completo en markdown"
}}"""

    respuesta = claude(prompt, max_tokens=4000)
    if not respuesta:
        return None
    respuesta = re.sub(r'^```json\s*', '', respuesta.strip())
    respuesta = re.sub(r'^```\s*', '', respuesta)
    respuesta = re.sub(r'\s*```$', '', respuesta)
    try:
        return json.loads(respuesta)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', respuesta, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        print("  ⚠️  No se pudo parsear el JSON de Claude")
        return None


# ── Plantilla de página de artículo ──────────────────────────────────────────

def plantilla_articulo(art):
    """Genera el HTML estático completo de un artículo."""
    titulo = html.escape(art["titulo"])
    resumen = html.escape(art["resumen"])
    nombre_cat = NOMBRE_CATEGORIA.get(art["categoria"], art["categoria"].capitalize())
    cuerpo = markdown_a_html(art["contenido"])
    url = f"{BASE_URL}/{BLOG_DIR}/{art['slug']}"
    fecha_iso = art["fecha_pub"][:10]
    fecha_legible = fecha_es(datetime.fromisoformat(art["fecha_pub"].replace("Z", "+00:00")))

    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": art["titulo"],
        "description": art["resumen"],
        "datePublished": fecha_iso,
        "dateModified": fecha_iso,
        "author": {"@type": "Organization", "name": "OpoNoticias"},
        "publisher": {
            "@type": "Organization", "name": "OpoNoticias",
            "logo": {"@type": "ImageObject", "url": f"{BASE_URL}/assets/icon-512.svg"},
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "articleSection": nombre_cat,
    }

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{titulo} — OpoNoticias</title>
  <meta name="description" content="{resumen}">
  <link rel="canonical" href="{url}">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#5A5047">
  <script>document.documentElement.className += ' js';</script>

  <meta property="og:type" content="article">
  <meta property="og:site_name" content="OpoNoticias">
  <meta property="og:title" content="{titulo}">
  <meta property="og:description" content="{resumen}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{BASE_URL}/assets/banner-telegram.svg">
  <meta property="og:locale" content="es_ES">
  <meta name="twitter:card" content="summary_large_image">

  <link rel="icon" type="image/svg+xml" href="../assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/style.css?v=2">

  <script type="application/ld+json">
  {json.dumps(schema, ensure_ascii=False, indent=2)}
  </script>
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-4832095429696459" crossorigin="anonymous"></script>
</head>
<body>

  <header class="site-header">
    <div class="container">
      <nav class="nav" aria-label="Principal">
        <a href="../index.html" aria-label="OpoNoticias - Inicio"><img src="../assets/logo.svg" alt="OpoNoticias" class="nav-logo"></a>
        <div class="nav-links">
          <a href="../index.html#categorias">Categorías</a>
          <a href="../blog.html">Blog</a>
          <a href="../index.html#como-funciona">Cómo funciona</a>
        </div>
        <div class="nav-cta">
          <div class="nav-social">
            <a href="https://t.me/OPONOTICIAS" rel="noopener" target="_blank" aria-label="Telegram" title="Telegram"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg></a>
            <a href="https://www.facebook.com/profile.php?id=61590965302457" rel="noopener" target="_blank" aria-label="Facebook" title="Facebook"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.1 24 18.1 24 12.07z"/></svg></a>
            <a href="mailto:info@oponoticias.com" aria-label="Email" title="info@oponoticias.com"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M2 4h20c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H2c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm10 7L2.5 6h19L12 11zm0 2.2L2 7.3V18h20V7.3l-10 5.9z"/></svg></a>
          </div>
          <a href="../index.html#categorias" class="btn btn-ghost">Explorar</a>
          <a href="https://t.me/OPONOTICIAS" class="btn btn-primary" rel="noopener" target="_blank">Telegram</a>
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
        <a href="../blog.html">Blog</a>
        <span class="sep">/</span>
        <span aria-current="page">{nombre_cat}</span>
      </nav>

      <article class="legal-doc">
        <header class="article-header">
          <span class="article-tag">{nombre_cat}</span>
          <h1>{titulo}</h1>
          <div class="article-meta">
            <span>Publicado el <b>{fecha_legible}</b></span>
          </div>
        </header>
        <div class="prose">
{cuerpo}
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
        <div class="footer-col">
          <h4>Comunidades</h4>
          <a href="../ccaa/madrid.html">Madrid</a>
          <a href="../ccaa/andalucia.html">Andalucía</a>
          <a href="../ccaa/cataluna.html">Cataluña</a>
          <a href="../ccaa/comunidad-valenciana.html">C. Valenciana</a>
          <a href="../index.html#comunidades">Ver todas →</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© {datetime.now().year} OpoNoticias · oponoticias.com</span>
        <span>Fuente oficial: api.boe.es · Actualización diaria a las 9:30 h</span>
      </div>
    </div>
  </footer>

  <script src="../assets/script.js?v=2" defer></script>
</body>
</html>
"""


def plantilla_indice(articulos):
    """Genera /blog.html con el listado de todos los artículos."""
    cards = ""
    for a in articulos:
        nombre_cat = NOMBRE_CATEGORIA.get(a.get("categoria",""), (a.get("categoria") or "").capitalize())
        fecha = fecha_es(datetime.fromisoformat(a["fecha_pub"].replace("Z", "+00:00")))
        cards += f"""
        <a href="{BLOG_DIR}/{html.escape(a['slug'])}.html" class="blog-card">
          <span class="blog-card-tag">{html.escape(nombre_cat)}</span>
          <h2 class="blog-card-title">{html.escape(a['titulo'])}</h2>
          <p class="blog-card-summary">{html.escape(a.get('resumen',''))}</p>
          <span class="blog-card-date">{fecha}</span>
        </a>"""

    if not cards:
        cards = '<p class="blog-empty">Pronto publicaremos los primeros artículos. ¡Vuelve pronto!</p>'

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Blog de oposiciones — OpoNoticias</title>
  <meta name="description" content="Guías, análisis y consejos sobre oposiciones y empleo público en España. Artículos actualizados sobre convocatorias del BOE por categoría.">
  <link rel="canonical" href="{BASE_URL}/blog">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#5A5047">
  <script>document.documentElement.className += ' js';</script>

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="OpoNoticias">
  <meta property="og:title" content="Blog de oposiciones — OpoNoticias">
  <meta property="og:description" content="Guías y análisis sobre oposiciones y empleo público en España.">
  <meta property="og:url" content="{BASE_URL}/blog">

  <link rel="icon" type="image/svg+xml" href="assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/style.css?v=2">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-4832095429696459" crossorigin="anonymous"></script>
</head>
<body>

  <header class="site-header">
    <div class="container">
      <nav class="nav" aria-label="Principal">
        <a href="index.html" aria-label="OpoNoticias - Inicio"><img src="assets/logo.svg" alt="OpoNoticias" class="nav-logo"></a>
        <div class="nav-links">
          <a href="index.html#categorias">Categorías</a>
          <a href="blog.html">Blog</a>
          <a href="index.html#como-funciona">Cómo funciona</a>
        </div>
        <div class="nav-cta">
          <a href="index.html#categorias" class="btn btn-ghost">Explorar</a>
          <a href="https://t.me/OPONOTICIAS" class="btn btn-primary" rel="noopener" target="_blank">Telegram</a>
        </div>
        <button class="nav-toggle" aria-label="Abrir menú" aria-expanded="false"><span></span><span></span><span></span></button>
      </nav>
    </div>
  </header>

  <main>
    <div class="container">
      <nav class="breadcrumb" aria-label="Migas de pan">
        <a href="index.html">Inicio</a>
        <span class="sep">/</span>
        <span aria-current="page">Blog</span>
      </nav>

      <div class="blog-hero">
        <span class="eyebrow">Para estudiar mejor</span>
        <h1 class="section-title">El blog del opositor</h1>
        <p class="section-lead">Guías, análisis de convocatorias y consejos prácticos para preparar tu oposición. Contenido actualizado a partir de lo que publica el BOE.</p>
      </div>

      <div class="blog-grid">{cards}
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
            <a href="mailto:info@oponoticias.com" aria-label="Email" title="info@oponoticias.com"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M2 4h20c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H2c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm10 7L2.5 6h19L12 11zm0 2.2L2 7.3V18h20V7.3l-10 5.9z"/></svg></a>
          </div>
        </div>
        <div class="footer-col">
          <h4>Categorías</h4>
          <a href="categoria/educacion.html">Educación</a>
          <a href="categoria/sanidad.html">Sanidad</a>
          <a href="categoria/justicia.html">Justicia</a>
          <a href="categoria/administracion.html">Administración</a>
        </div>
        <div class="footer-col">
          <h4>Recursos</h4>
          <a href="index.html#ultimas">Últimas convocatorias</a>
          <a href="index.html#como-funciona">Cómo funciona</a>
          <a href="https://www.boe.es" rel="noopener" target="_blank">BOE oficial</a>
        </div>
        <div class="footer-col">
          <h4>Legal</h4>
          <a href="aviso-legal.html">Aviso legal</a>
          <a href="privacidad.html">Privacidad (RGPD)</a>
          <a href="cookies.html">Cookies</a>
          <a href="mailto:info@oponoticias.com">info@oponoticias.com</a>
        </div>
        <div class="footer-col">
          <h4>Comunidades</h4>
          <a href="ccaa/madrid.html">Madrid</a>
          <a href="ccaa/andalucia.html">Andalucía</a>
          <a href="ccaa/cataluna.html">Cataluña</a>
          <a href="ccaa/comunidad-valenciana.html">C. Valenciana</a>
          <a href="index.html#comunidades">Ver todas →</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© {datetime.now().year} OpoNoticias · oponoticias.com</span>
        <span>Fuente oficial: api.boe.es · Actualización diaria a las 9:30 h</span>
      </div>
    </div>
  </footer>

  <script src="assets/script.js?v=2" defer></script>
</body>
</html>
"""


def generar_sitemap_blog(articulos):
    hoy = datetime.now().strftime("%Y-%m-%d")
    urls = [f"""  <url>
    <loc>{BASE_URL}/blog</loc>
    <lastmod>{hoy}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>"""]
    for a in articulos:
        fecha = a["fecha_pub"][:10]
        urls.append(f"""  <url>
    <loc>{BASE_URL}/{BLOG_DIR}/{a['slug']}</loc>
    <lastmod>{fecha}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


# ── Guardado ─────────────────────────────────────────────────────────────────

def guardar_articulo(art, categoria):
    slug = f"{slugify(art['titulo'])}-{datetime.now().strftime('%Y%m')}"
    art["slug"] = slug
    art["categoria"] = categoria
    art["fecha_pub"] = datetime.now(timezone.utc).isoformat()

    data = {
        "titulo": art["titulo"], "slug": slug,
        "resumen": art.get("resumen", ""), "contenido": art["contenido"],
        "categoria": categoria, "tipo": "ia", "publicado": True,
        "fecha_pub": art["fecha_pub"],
    }
    status = supabase_post("articulos_blog", data)
    if status == 409:
        print(f"  ⚠️  Ya existe slug '{slug}', saltando…")
        return False
    if status not in (200, 201):
        print(f"  ❌  Error guardando en Supabase (status {status})")
        return False

    # Página HTML estática
    os.makedirs(BLOG_DIR, exist_ok=True)
    ruta = os.path.join(BLOG_DIR, f"{slug}.html")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(plantilla_articulo(art))
    print(f"  ✅  Guardado en Supabase + página: {ruta}")
    return True


def regenerar_indice_y_sitemap():
    """Reconstruye blog.html y sitemap-blog.xml con todos los artículos publicados."""
    params = urllib.parse.urlencode({
        "select": "titulo,slug,resumen,categoria,fecha_pub",
        "publicado": "eq.true", "order": "fecha_pub.desc", "limit": 200,
    })
    articulos = supabase_get("articulos_blog", params)
    with open("blog.html", "w", encoding="utf-8") as f:
        f.write(plantilla_indice(articulos))
    with open("sitemap-blog.xml", "w", encoding="utf-8") as f:
        f.write(generar_sitemap_blog(articulos))
    print(f"  🔄  Índice y sitemap regenerados ({len(articulos)} artículos)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"🖊️  Generador de Blog IA — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    if not (SUPABASE_URL and SUPABASE_API_KEY and ANTHROPIC_API_KEY):
        print("❌ Faltan variables de entorno: SUPABASE_URL, SUPABASE_API_KEY, ANTHROPIC_API_KEY")
        return
    print(f"🔗 Supabase: {SUPABASE_URL}")  # debug — ayuda a detectar URL incorrecta

    cats = CATEGORIAS.copy()
    random.shuffle(cats)
    generados = 0

    for categoria in cats:
        if generados >= MAX_ARTICULOS_POR_EJECUCION:
            print(f"\n✋ Límite de {MAX_ARTICULOS_POR_EJECUCION} artículos alcanzado.")
            break

        print(f"\n📂 {NOMBRE_CATEGORIA[categoria]}")
        if articulo_reciente(categoria):
            print("  ⏭️  Ya hay artículo reciente, saltando…")
            continue

        convocatorias = obtener_convocatorias(categoria, limite=5)
        if not convocatorias:
            print("  ⚠️  Sin convocatorias, saltando…")
            continue

        print(f"  📋 {len(convocatorias)} convocatorias · 🤖 generando…")
        art = generar_articulo(categoria, convocatorias)
        if not art or not art.get("titulo") or not art.get("contenido"):
            print("  ❌ Generación fallida")
            continue

        print(f"  📝 {art['titulo'][:60]}…")
        if guardar_articulo(art, categoria):
            generados += 1
        time.sleep(3)

    if generados:
        regenerar_indice_y_sitemap()

    print(f"\n{'=' * 60}")
    print(f"✅ Completado — {generados} artículo(s) nuevo(s)")
    print("=" * 60)


if __name__ == "__main__":
    main()
