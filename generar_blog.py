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
from web_utils import limpiar_hrefs
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
    # Pista de contenido metodológico (artículos de preparación/estudio).
    # No es una categoría de convocatorias: no entra en el bucle de generación
    # por categoría, solo da nombre y miga de pan a los artículos temáticos.
    "preparacion": "Preparación",
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
        "model": "claude-sonnet-5",
        # Sonnet 5 activa "adaptive thinking" por defecto; se desactiva para no
        # gastar tokens de razonamiento (facturados) ni recortar el artículo.
        "thinking": {"type": "disabled"},
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


def reclamar_categoria_hoy(categoria):
    """Reserva la categoría para HOY antes de generar nada (evita que dos
    ejecuciones paralelas —manual + cron el mismo día— generen 2 artículos
    de la misma categoría: ver sql/crear_tabla_blog_claims.sql). El INSERT choca
    con la clave primaria (categoria, fecha) si otra ejecución ya la reservó
    hoy, y Supabase lo resuelve de forma atómica (a diferencia de comprobar
    y luego actuar en Python, que dejaría una ventana de carrera).
    Si la tabla aún no existe (falta ejecutar la migración), NO bloquea:
    se asume reservado para no romper el flujo existente."""
    hoy = datetime.now(timezone.utc).date().isoformat()
    status = supabase_post("blog_claims", {"categoria": categoria, "fecha": hoy})
    if status == 409:
        return False
    if status not in (200, 201):
        print(f"  ⚠️  No se pudo reservar la categoría (status {status}), se continúa igualmente.")
    return True


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

    prompt = f"""Eres un redactor experto en oposiciones y empleo público en España, con profundo conocimiento técnico del acceso a la función pública: cuerpos y escalas, grupos de clasificación, sistemas selectivos y bases de convocatoria. Has cubierto el sector durante años y escribes con autoridad profesional, pero de forma humana y cercana, como alguien que conoce de primera mano lo que vive un opositor. Escribe para OpoNoticias un artículo sobre las oposiciones de {nombre} en {año}.

CONVOCATORIAS REALES PUBLICADAS (son los únicos datos verificados; no inventes cifras, fechas ni plazas que no aparezcan aquí):
{contexto}

CÓMO DEBES ESCRIBIR (lo más importante):
- Registro profesional, técnico y formal, pero humano: escribe como un experto que explica con rigor y claridad, no como una IA ni como un folleto publicitario.
- Sé preciso y exacto con la terminología de la función pública. Emplea correctamente los términos del acceso al empleo público: cuerpos, escalas y especialidades; grupos de clasificación (A1, A2, B, C1, C2); sistemas selectivos (oposición, concurso-oposición, concurso); turno libre y promoción interna; bases de la convocatoria, temario, fase de oposición y fase de concurso. No uses un término por otro.
- Nombra cada profesión con exactitud y su denominación oficial (p. ej. "Cuerpo de Maestros", "Enfermero/a Interno/a Residente", "Policía Local", "Cuerpo de Gestión Procesal y Administrativa"), sin generalizar ni inventar denominaciones.
- Varía la longitud de las frases. Mezcla frases cortas y contundentes con otras más largas. El ritmo monótono delata el texto automático.
- Empieza con un gancho concreto: un dato real de las convocatorias de arriba, una fecha, un organismo o un número de plazas. NUNCA empieces con "En el mundo actual", "Las oposiciones son una de las mejores opciones" o "Es importante destacar".
- Da contexto útil y verificable: a quién va dirigida, qué titulación o requisitos suelen exigirse, en qué consiste el proceso selectivo. Si no tienes el dato exacto, exprésalo en términos generales sin inventar cifras ni denominaciones.
- PROHIBIDO usar muletillas de IA: "En resumen", "En definitiva", "Cabe destacar", "Es fundamental", "el mundo de las oposiciones", "embarcarte en", "abre las puertas a", "no es tarea fácil", ni listas de tres adjetivos.
- Evita las viñetas salvo que aporten algo real (requisitos o pruebas concretas). Prefiere la prosa.

ESTRUCTURA Y SEO:
- Entre 900 y 1300 palabras de contenido real.
- Usa ## para H2 y ### para H3. Que los subtítulos contengan lo que la gente busca ("Requisitos", "Plazas convocadas", "Fechas y plazos", "Cómo prepararte").
- Pon en **negrita** los términos clave de forma natural (1-3 por sección).
- Incluye 3 enlaces internos dentro de frases, con URL EXACTAS (sin ".html"), eligiendo entre: [oposiciones de Educación](/categoria/educacion), [Sanidad](/categoria/sanidad), [Administración](/categoria/administracion), [Justicia](/categoria/justicia), [Seguridad](/categoria/seguridad), [Hacienda](/categoria/hacienda), [Correos](/categoria/correos), [el BOE de hoy](/boe-hoy) o [recursos gratis para opositores](/recursos). No repitas dos veces el mismo destino.
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

    # Portada propia del artículo (1200×630) si está disponible; si no, banner genérico.
    imagen = art.get("imagen") or ""
    og_image = imagen or f"{BASE_URL}/social/telegram-banner.png"
    cover_html = ""
    if imagen:
        cover_html = (
            f'\n        <figure class="article-cover">'
            f'<img src="{html.escape(imagen)}" alt="{titulo}" '
            f'width="1200" height="630" loading="eager"></figure>'
        )

    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": art["titulo"],
        "description": art["resumen"],
        "image": og_image,
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
  <meta property="og:image" content="{og_image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:locale" content="es_ES">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="{og_image}">

  <link rel="icon" type="image/svg+xml" href="../assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/style.css?v=6">

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
          <a href="../index.html#comunidades">Comunidades</a>
          <a href="../index.html#categorias">Categorías</a>
          <a href="../blog.html">Blog</a>
          <a href="../recursos.html">Recursos</a>
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
        </header>{cover_html}
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
          <p>Todas las convocatorias de oposiciones del BOE, organizadas y resumidas para que no se te escape tu plaza.</p>
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
        <span>Fuente oficial: api.boe.es · Actualización diaria cada mañana</span>
      </div>
    </div>
  </footer>

  <script src="../assets/script.js?v=8" defer></script>
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
  <title>Noticias y actualidad de oposiciones {datetime.now().year} | OpoNoticias</title>
  <meta name="description" content="Noticias y actualidad de oposiciones y empleo público en España: análisis de las convocatorias del BOE, guías y consejos para preparar tu oposición en {datetime.now().year}.">
  <link rel="canonical" href="{BASE_URL}/blog">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#5A5047">
  <script>document.documentElement.className += ' js';</script>

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="OpoNoticias">
  <meta property="og:title" content="Noticias y actualidad de oposiciones {datetime.now().year} | OpoNoticias">
  <meta property="og:description" content="Noticias, actualidad y análisis de oposiciones y empleo público en España.">
  <meta property="og:url" content="{BASE_URL}/blog">

  <link rel="icon" type="image/svg+xml" href="assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/style.css?v=6">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-4832095429696459" crossorigin="anonymous"></script>
</head>
<body>

  <header class="site-header">
    <div class="container">
      <nav class="nav" aria-label="Principal">
        <a href="index.html" aria-label="OpoNoticias - Inicio"><img src="assets/logo.svg" alt="OpoNoticias" class="nav-logo"></a>
        <div class="nav-links">
          <a href="index.html#comunidades">Comunidades</a>
          <a href="index.html#categorias">Categorías</a>
          <a href="blog.html">Blog</a>
          <a href="recursos.html">Recursos</a>
          <a href="index.html#como-funciona">Cómo funciona</a>
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
        <a href="index.html">Inicio</a>
        <span class="sep">/</span>
        <span aria-current="page">Blog</span>
      </nav>

      <div class="blog-hero">
        <span class="eyebrow">El blog del opositor</span>
        <h1 class="section-title">Noticias y actualidad de oposiciones</h1>
        <p class="section-lead">Análisis de las convocatorias del BOE, guías y consejos prácticos para preparar tu oposición. Actualidad del empleo público en España, actualizada a partir de lo que se publica cada día.</p>
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
          <p>Todas las convocatorias de oposiciones del BOE, organizadas y resumidas para que no se te escape tu plaza.</p>
          <div class="footer-social">
            <a href="https://t.me/OPONOTICIAS" rel="noopener" target="_blank" aria-label="Telegram" title="Telegram"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg></a>
            <a href="https://www.facebook.com/profile.php?id=61590965302457" rel="noopener" target="_blank" aria-label="Facebook" title="Facebook"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.1 24 18.1 24 12.07z"/></svg></a>
            <a href="https://x.com/OpoNoticiasON" rel="noopener" target="_blank" aria-label="X" title="X"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
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
        <span>Fuente oficial: api.boe.es · Actualización diaria cada mañana</span>
      </div>
    </div>
  </footer>

  <script src="assets/script.js?v=8" defer></script>
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
        f.write(limpiar_hrefs(plantilla_articulo(art)))
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
        f.write(limpiar_hrefs(plantilla_indice(articulos)))
    with open("sitemap-blog.xml", "w", encoding="utf-8") as f:
        f.write(generar_sitemap_blog(articulos))
    print(f"  🔄  Índice y sitemap regenerados ({len(articulos)} artículos)")


# ── Publicación en redes sociales ─────────────────────────────────────────────

def _strip_markdown(texto):
    """Elimina el marcado Markdown básico para obtener texto plano."""
    import re
    texto = re.sub(r'^#{1,6}\s+', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'\*{1,2}([^*\n]+)\*{1,2}', r'\1', texto)
    texto = re.sub(r'_{1,2}([^_\n]+)_{1,2}', r'\1', texto)
    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)
    texto = re.sub(r'^[\-\*\d+\.]\s+', '', texto, flags=re.MULTILINE)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()


def _publicar_en_redes(art):
    """Publica el artículo en Facebook (foto nativa + enlace en comentario) e Instagram (screenshot).

    Best-effort: cualquier fallo se reporta sin interrumpir el flujo.
    Requiere FB_PAGE_TOKEN, FB_PAGE_ID, FB_IG_ID y Supabase configurados.
    """
    try:
        import publicar_meta
        import generar_imagen_instagram as gii
    except ImportError as e:
        print(f"  ℹ️  Redes: módulo no disponible ({e}), omitiendo.")
        return

    if not publicar_meta.configurado():
        print("  ℹ️  Redes: FB_PAGE_TOKEN no configurado, omitiendo.")
        return

    url_articulo = f"{BASE_URL}/{BLOG_DIR}/{art['slug']}.html"
    hashtags = f"#oposiciones #{art['categoria']} #BOE #empleopublico #opositar"

    # ── Screenshot del HTML del artículo (FB foto nativa + IG) ──────────────
    html_path = os.path.join(BLOG_DIR, f"{art['slug']}.html")
    slug_corto = art["slug"][:40]
    nombre_remoto = f"blog/ig-{datetime.now().strftime('%Y%m')}-{slug_corto}.jpg"
    img_url = gii.screenshot_blog_html(html_path, nombre_remoto)

    contenido_limpio = _strip_markdown(art.get("contenido", ""))
    # Recorta al primer párrafo natural o a 2 500 chars para no saturar el post
    parrafos = [p.strip() for p in contenido_limpio.split("\n\n") if p.strip()]
    extracto = ""
    for p in parrafos:
        if len(extracto) + len(p) + 2 > 2500:
            break
        extracto = (extracto + "\n\n" + p).strip()

    # ── Facebook: foto NATIVA + enlace en primer comentario ─────────────────
    # FB penaliza el alcance de los posts con enlace en el cuerpo; la imagen va
    # nativa y el enlace al artículo queda como primer comentario. Sin
    # screenshot se cae al post de texto+enlace.
    if img_url:
        msg_fb = (
            f"📚 {art['titulo']}\n\n"
            f"{extracto}\n\n"
            f"📖 Artículo completo en el primer comentario 👇\n\n"
            f"{hashtags}"
        )
        publicar_meta.publicar_foto_facebook_enlace(img_url, msg_fb, url_articulo)
    else:
        msg_fb = (
            f"📚 {art['titulo']}\n\n"
            f"{extracto}\n\n"
            f"👉 Lee el artículo completo:\n{url_articulo}\n\n"
            f"{hashtags}"
        )
        publicar_meta.publicar_enlace_facebook(msg_fb)

    # ── Instagram: misma imagen del artículo ────────────────────────────────
    if img_url:
        caption_ig = (
            f"📚 {art['titulo']}\n\n"
            f"{art.get('resumen', '')}\n\n"
            f"🔗 Enlace en bio · oponoticias.com\n\n"
            f"{hashtags}"
        )
        publicar_meta.publicar_foto_instagram(img_url, caption_ig)
    else:
        print("  ⚠️  Redes: no se pudo generar screenshot para Instagram, omitiendo IG.")


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
        if not reclamar_categoria_hoy(categoria):
            print("  ⏭️  Otra ejecución ya está generando esta categoría hoy, saltando…")
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
            # El artículo ya está guardado (Supabase + HTML); un fallo al
            # publicarlo en redes es secundario y NO debe abortar el resto
            # del bucle ni saltarse regenerar_indice_y_sitemap() de abajo
            # (antes, una excepción sin capturar aquí dejaba sin procesar las
            # categorías restantes y sin actualizar blog.html/sitemap-blog.xml
            # pese a tener ya artículos nuevos guardados).
            try:
                _publicar_en_redes(art)
            except Exception as e:
                print(f"  ⚠️  Guardado, pero falló la publicación en redes: {e}")
        time.sleep(3)

    if generados:
        regenerar_indice_y_sitemap()

    print(f"\n{'=' * 60}")
    print(f"✅ Completado — {generados} artículo(s) nuevo(s)")
    print("=" * 60)


if __name__ == "__main__":
    main()
