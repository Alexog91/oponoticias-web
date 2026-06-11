"""
actualizar_noticias.py — Alimenta la columna de NOTICIAS del Diario del Opositor.

Lee el RSS de oposiciones de 20minutos (titular + resumen corto + enlace) y guarda
las noticias en la tabla `noticias_rss` de Supabase. Solo se almacena el titular,
una descripción breve y el enlace a la fuente — NUNCA el artículo completo —, que es
exactamente el uso para el que existe un feed RSS.

Pensado para ejecutarse cada hora (cron / GitHub Actions), igual que leer_boe.py.

Uso:
  SUPABASE_URL=... SUPABASE_API_KEY=... python3 actualizar_noticias.py

Requisitos en Supabase: tabla `noticias_rss` (ver SQL en crear_tabla_noticias.sql).
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import json
import os
import re
import html
import unicodedata
from email.utils import parsedate_to_datetime

# ── Configuración ───────────────────────────────────────────────────────────
SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")

# Fuentes RSS (todas de oposiciones/empleo público, pensadas para sindicación).
# Formato: (nombre_fuente, url_feed)
FUENTES_RSS = [
    ("20minutos",      "https://www.20minutos.es/rss/tag/oposiciones/"),
    ("oposiciones.net", "https://www.oposiciones.net/feed/"),
    ("Preparadores",   "https://www.preparadores.eu/feed/"),
]

# Cuántas noticias guardar como máximo por ejecución (las más recientes)
MAX_NOTICIAS = 25

# Descartar items cuyo titular sea claramente de portada/sección, no una noticia
TITULOS_BASURA = [
    "20MINUTOS.ES", "LO ÚLTIMO", "LO ULTIMO",
    "PORTAL DE OPOSICIONES", "PREPARADORES DE OPOSICIONES",
]

# Filtro de relevancia: el titular o la descripción debe contener algo de esto.
# Mantiene la columna centrada en oposiciones aunque se añadan feeds más amplios.
PALABRAS_RELEVANTES = [
    "oposici", "plaza", "convocatoria", "empleo públic", "empleo public",
    "funcionari", "examen", "admitidos", "excluidos", "tribunal", "boe",
    "oferta de empleo", "ope ", "interin", "bolsa de", "concurso", "selectivo",
    "docente", "maestro", "profesor", "policía", "policia", "guardia civil",
]


def limpiar_html(texto):
    """Quita etiquetas HTML y normaliza espacios (los feeds WordPress meten HTML)."""
    if not texto:
        return ''
    texto = re.sub(r'<[^>]+>', ' ', texto)   # quitar etiquetas
    texto = html.unescape(texto)             # &amp; → &, etc.
    texto = re.sub(r'\s+', ' ', texto)       # colapsar espacios
    return texto.strip()


def _sin_tildes(texto):
    return unicodedata.normalize('NFKD', texto.casefold()).encode('ascii', 'ignore').decode('ascii')


def es_relevante(titulo, descripcion):
    """True si el item trata de oposiciones/empleo público."""
    blob = _sin_tildes(titulo + ' ' + descripcion)
    return any(_sin_tildes(p) in blob for p in PALABRAS_RELEVANTES)


def leer_feed(nombre, url):
    """Descarga y parsea un feed RSS. Devuelve lista de dicts de noticias."""
    print(f"🔄 Leyendo feed de {nombre}: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f"  ❌ Error descargando el feed: {e}")
        return []

    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        print(f"  ❌ Error parseando XML: {e}")
        return []

    noticias = []
    for item in root.findall('.//item'):
        titulo = limpiar_html(item.findtext('title') or '')
        enlace = (item.findtext('link') or '').strip()
        desc   = limpiar_html(item.findtext('description') or '')
        pub    = (item.findtext('pubDate') or '').strip()

        if not titulo or not enlace:
            continue
        if any(b in titulo.upper() for b in TITULOS_BASURA):
            continue
        if not es_relevante(titulo, desc):
            continue

        # Imagen (enclosure), si la hay
        imagen = ''
        enclosure = item.find('enclosure')
        if enclosure is not None:
            imagen = enclosure.get('url', '') or ''

        # Fecha de publicación → ISO 8601 para Supabase (timestamptz)
        fecha_iso = None
        if pub:
            try:
                fecha_iso = parsedate_to_datetime(pub).isoformat()
            except Exception:
                fecha_iso = None

        # Recortar la descripción a un resumen breve (nunca el texto completo)
        if len(desc) > 220:
            desc = desc[:220].rsplit(' ', 1)[0] + '…'

        noticias.append({
            'titulo': titulo,
            'descripcion': desc,
            'enlace': enlace,
            'fuente': nombre,
            'imagen': imagen,
            'fecha_pub': fecha_iso,
        })

    print(f"  ✓ {len(noticias)} noticias encontradas")
    return noticias


def guardar_noticia(noticia):
    """Inserta una noticia en Supabase. Devuelve True si es nueva, False si ya existía."""
    url = f"{SUPABASE_URL}/rest/v1/noticias_rss"
    headers = {
        'apikey': SUPABASE_API_KEY,
        'Authorization': f'Bearer {SUPABASE_API_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }
    data = json.dumps(noticia).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        print(f"  ✓ Guardada: {noticia['titulo'][:65]}…")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 409:          # enlace duplicado (constraint UNIQUE)
            return False
        print(f"  ❌ Error Supabase ({e.code}): {e.read().decode('utf-8', 'ignore')[:120]}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


if __name__ == "__main__":
    if not all([SUPABASE_URL, SUPABASE_API_KEY]):
        print("❌ Faltan variables de entorno: SUPABASE_URL, SUPABASE_API_KEY")
        raise SystemExit(1)

    todas = []
    for nombre, url in FUENTES_RSS:
        todas.extend(leer_feed(nombre, url))

    # Más recientes primero, limitar volumen por ejecución
    todas = [n for n in todas if n['fecha_pub']]
    todas.sort(key=lambda n: n['fecha_pub'], reverse=True)
    todas = todas[:MAX_NOTICIAS]

    print(f"\n💾 Guardando hasta {len(todas)} noticias en Supabase…\n")
    nuevas = 0
    for n in todas:
        if guardar_noticia(n):
            nuevas += 1

    print(f"\n✅ Hecho. Noticias nuevas: {nuevas} / {len(todas)} procesadas")
