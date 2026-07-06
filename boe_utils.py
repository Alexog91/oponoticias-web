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
