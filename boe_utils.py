"""
boe_utils.py — Parseo/formato de convocatorias compartido entre leer_boe.py
(generar_slug) y los generadores de páginas estáticas generar_ccaa.py /
generar_categorias.py (que antes tenían cada uno su propia copia idéntica de
estas 7 funciones — divergían solo en comentarios).
"""

import re
import html as html_lib
import unicodedata
from datetime import datetime
from email.utils import parsedate_to_datetime

MESES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
               'jul', 'ago', 'sep', 'oct', 'nov', 'dic']


# ── ¿Es este título del BOE una convocatoria que nos interesa? ──────────────
# Se buscan RAÍCES, no palabras exactas: el BOE alterna género, número y forma
# verbal («pruebas selectivas», «plaza de», «se convoca») y un filtro de
# palabras completas se deja fuera ~1 convocatoria real al día — medido sobre
# 39 días de BOE (1.415 publicaciones, 39 perdidas en silencio).
_ES_CONVOCATORIA = re.compile(r'oposici|selectiv|convocatori|se convoca|plaza', re.I)

# Lo anterior es demasiado ancho por sí solo: «se convoca» también encabeza los
# movimientos internos entre funcionarios, que NO son acceso al empleo público
# y no le sirven a un opositor.
_NO_ES_ACCESO = re.compile(
    # Provisión de puestos entre quienes YA son funcionarios (a dedo o por concurso).
    r'libre designaci'
    r'|provisi[óo]n de puesto'
    r'|concurso espec[íi]fico'
    # Cátedras y titularidades: nicho distinto del opositor (decisión de producto,
    # 24 jul 2026). El PAS universitario SÍ entra: no casa con ninguno de estos.
    r'|cuerpos docentes universitarios'
    r'|plaza vinculada'
    r'|profesorado'
    r'|catedr[áa]tic'
    r'|profesor titular'
    r'|titular de universidad',
    re.I,
)


def es_convocatoria(titulo):
    """True si el título del BOE es una convocatoria de acceso al empleo público."""
    t = titulo or ""
    return bool(_ES_CONVOCATORIA.search(t)) and not _NO_ES_ACCESO.search(t)


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


# Fecha en español ("9 de julio", "15 de enero de 2026") — se usa para no
# confundir la FECHA de la disposición con el organismo (ver extraer_organismo).
_FECHA_ES = (
    r'\d{1,2}\s+de\s+'
    r'(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|'
    r'septiembre|octubre|noviembre|diciembre)'
    r'(?:\s+de\s+\d{4})?'
)


def extraer_organismo(titulo):
    """Extrae el organismo del título largo del BOE (título corto y legible)."""
    m = re.search(
        r',\s+(?:de la|del|de los|de las|de)\s+(.+?)'
        r'(?:,\s+(?:por la que|por el que|referente|en la que|sobre|relativa)|$)',
        titulo, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        # Títulos "Orden/Resolución [código], de [FECHA](, de la [ORG]), por la
        # que...": el primer hueco tras la coma lo ocupa la FECHA de la
        # disposición, no el organismo. Se quita la fecha inicial (y el conector
        # que la sigue) y queda el organismo real si lo hay.
        cand = re.sub(rf'^{_FECHA_ES}\s*(?:,\s+(?:de la|del|de los|de las|de)\s+)?',
                      '', cand, flags=re.IGNORECASE).strip()
        if cand:
            return cand
        # Solo había una fecha: son órdenes/resoluciones ministeriales numeradas
        # (sin organismo explícito en el título) → Administración General del Estado.
        return "Administración General del Estado"
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
    """Genera un slug único usando el título + referencia BOE como sufijo."""
    slug = titulo.lower()
    slug = unicodedata.normalize('NFKD', slug)
    slug = ''.join([c for c in slug if not unicodedata.combining(c)])
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    slug = re.sub(r'-+', '-', slug)
    slug = slug[:60]
    # El ref_boe (ej: BOE-A-2026-12461) garantiza unicidad aunque los títulos coincidan
    if ref_boe and ref_boe != "BOE":
        sufijo = re.sub(r'[^a-z0-9]+', '-', ref_boe.lower()).strip('-')
        return f"{slug}-{sufijo}.html"
    return f"{slug}.html"


def url_convocatoria(titulo, enlace_boe, convocatoria_dir):
    """Devuelve la URL en oponoticias.com si existe la página, si no el BOE."""
    ref = ref_boe_desde_enlace(enlace_boe)
    slug = generar_slug(titulo, ref)
    if (convocatoria_dir / slug).exists():
        return f"https://oponoticias.com/convocatoria/{slug.replace('.html', '')}", True
    return html_lib.escape(enlace_boe or '#'), False
