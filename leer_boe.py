import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import json
import os
import time
import re
import subprocess
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from pathlib import Path
import unicodedata

# CONFIGURACIÓN - Desde GitHub Secrets
RSS_URL = "https://www.boe.es/rss/boe.php?s=2B"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "Alexog91/oponoticias-web"
WEB_REPO_PATH = os.environ.get("WEB_REPO_PATH", "./oponoticias-web")

# Rutas al proyecto web
WEB_CONVOCATORIA_DIR = Path(WEB_REPO_PATH) / "convocatoria"
WEB_SITEMAP_PATH = Path(WEB_REPO_PATH) / "sitemap.xml"


def leer_boe_rss():
    print("🔄 Leyendo RSS del BOE...")

    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    req = urllib.request.Request(RSS_URL, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall('.//item')

        print(f"✓ Se encontraron {len(items)} publicaciones del BOE hoy\n")

        convocatorias = []

        for item in items:
            title_elem = item.find('title')
            link_elem = item.find('link')
            pubDate_elem = item.find('pubDate')
            description_elem = item.find('description')

            if title_elem is not None:
                titulo = title_elem.text or 'Sin título'
                enlace = link_elem.text if link_elem is not None else 'Sin enlace'
                fecha = pubDate_elem.text if pubDate_elem is not None else 'Sin fecha'
                resumen = description_elem.text if description_elem is not None else 'Sin descripción'

                # Limpiar resumen de metadata técnica
                resumen = re.sub(r'[-–]\s*Referencia:.*', '', resumen)
                resumen = re.sub(r'[-–]\s*KBytes:.*', '', resumen)
                resumen = re.sub(r'KBytes:.*', '', resumen)
                resumen = resumen.strip()
                resumen = resumen[:200] if resumen else 'Sin descripción'

                # Extraer referencia BOE del enlace
                ref_boe = "BOE"
                if "id=" in enlace:
                    ref_boe = enlace.split("id=")[-1]

                palabras_clave = ['oposición', 'oposiciones', 'selectivo', 'convocatoria', 'plazas']
                es_oposicion = any(palabra in titulo.lower() for palabra in palabras_clave)

                if es_oposicion:
                    convocatoria = {
                        'fecha': fecha,
                        'titulo': titulo,
                        'enlace': enlace,
                        'resumen': resumen,
                        'ref_boe': ref_boe
                    }
                    convocatorias.append(convocatoria)
                    print(f"📢 {titulo[:80]}...")

        return convocatorias

    except Exception as e:
        print(f"❌ Error al leer el RSS: {e}")
        return []


def _sanitizar_resumen(texto):
    """De la respuesta de Claude extrae UNA sola línea con formato
    'PLAZAS - PUESTO - LUGAR'. Descarta razonamiento, markdown, viñetas y
    saltos de línea. Devuelve la línea limpia (MAYÚSCULAS) o None si no hay
    ninguna línea válida (entonces se usará el fallback determinista)."""
    if not texto:
        return None

    # Quitar markdown y viñetas
    limpio = texto.replace('*', '').replace('#', '').replace('`', '')

    INICIOS_RAZONAMIENTO = (
        'analiz', 'el título', 'el titulo', 'dado que', 'organismo:', 'tipo:',
        'puesto:', 'lugar:', 'ayuntamiento:', 'la descripción', 'la descripcion',
        'no se', 'según', 'segun', 'este ', 'esta ', 'aqui', 'aquí',
    )

    for linea in limpio.splitlines():
        l = linea.strip().lstrip('-•·*').strip()
        if not l:
            continue
        low = l.lower()
        if low.startswith(INICIOS_RAZONAMIENTO):
            continue
        # Debe tener el patrón "<N PLAZAS|VARIAS PLAZAS> - <puesto> - <lugar>"
        if ' - ' in l and re.match(r'^\s*(\d+\s*plazas?|varias\s*plazas?)\b',
                                   l, re.IGNORECASE):
            partes = [p.strip() for p in l.split(' - ') if p.strip()]
            if len(partes) >= 2:
                return ' - '.join(partes[:3]).upper()[:120]
    return None


def _resumen_fallback(titulo, resumen):
    """Construye un resumen válido 'PLAZAS - PUESTO - LUGAR' SOLO con reglas
    locales (sin IA). Se usa cuando Claude no devuelve un formato utilizable,
    para que nunca se publique texto en bruto."""
    texto = f"{titulo} {resumen}"
    low = texto.lower()

    # 1 · Nº de plazas
    m = re.search(r'(\d+)\s*plaza', low)
    if m:
        n = int(m.group(1))
        plazas = "1 PLAZA" if n == 1 else f"{n} PLAZAS"
    elif 'varias plaza' in low or 'plazas' in low:
        plazas = "VARIAS PLAZAS"
    else:
        plazas = "1 PLAZA"

    # 2 · Puesto (genérico, derivado del texto)
    if 'funcionario y laboral' in low or ('funcionario' in low and 'laboral' in low):
        puesto = "PERSONAL FUNCIONARIO Y LABORAL"
    elif 'personal laboral' in low:
        puesto = "PERSONAL LABORAL"
    elif 'personal funcionario' in low:
        puesto = "PERSONAL FUNCIONARIO"
    else:
        cuerpo, _ = extraer_cuerpo(titulo)            # "📋 Administrativo" …
        puesto = re.sub(r'^[^\wÁÉÍÓÚÑ]+', '', cuerpo).strip().upper()

    # 3 · Lugar: paréntesis del título o el organismo convocante
    lugar = "ESPAÑA"
    par = re.search(r'\(([^)]+)\)', titulo)
    if par:
        lugar = par.group(1).strip().upper()
    else:
        loc = re.search(
            r'(?:Ayuntamiento|Diputaci[óo]n|Cabildo|Consejo|Mancomunidad|'
            r'Universidad|Consorcio)\s+(?:Provincial\s+)?de\s+'
            r'([A-ZÁÉÍÓÚÑ][\w\sÁÉÍÓÚÑáéíóúñ/-]+?)(?:,|$)',
            titulo)
        if loc:
            lugar = loc.group(1).strip().upper()[:40]

    return f"{plazas} - {puesto} - {lugar}"


def generar_resumen_con_claude(titulo, resumen):
    """Usa Claude API para generar un resumen inteligente.
    Garantiza SIEMPRE el formato 'PLAZAS - PUESTO - LUGAR' (valida la salida
    y, si Claude se desvía, cae a un fallback determinista local)."""

    try:
        prompt = f"""Analiza esta convocatoria del BOE y extrae la información clave.

Título: {titulo}
Descripción: {resumen}

RESPONDE SOLO con una línea en MAYÚSCULAS con este formato exacto:
[NÚMERO] PLAZAS - [PUESTO ESPECÍFICO] - [LUGAR]

IMPORTANTE: Busca SIEMPRE el puesto ESPECÍFICO, nunca genérico.

Ejemplos de puestos ESPECÍFICOS (NO genéricos):
- POLICÍA LOCAL (NO "Policía")
- ENFERMERO (NO "Sanitario")
- INSPECTOR DE HACIENDA (NO "Hacienda")
- TÉCNICO DE HACIENDA
- AGENTE DE HACIENDA
- JUEZ (NO "Justicia")
- FISCAL
- LETRADO DE LA ADMINISTRACIÓN DE JUSTICIA
- GESTOR PROCESAL
- AUXILIAR JUDICIAL
- PROFESOR DE EDUCACIÓN FÍSICA (NO "Profesor")
- TÉCNICO INFORMÁTICO (NO "Técnico")
- INGENIERO TÉCNICO
- BOMBERO
- JARDINERO
- PEÓN DE SERVICIOS
- ADMINISTRATIVO
- SECRETARIO DE AYUNTAMIENTO

Estrategia:
1. Lee el título completo buscando palabras específicas
2. Si dice "Resolución de X de Y, del Ayuntamiento de Z", busca después qué puesto es
3. Extrae el puesto más específico posible del texto
4. Si encuentras "Inspector", "Técnico", "Agente", "Gestor", "Letrado", "Auxiliar" + categoría, úsalo
5. NUNCA pongas términos genéricos como "Justicia", "Hacienda", "Sanitario", "Funcionario"

Ejemplos correctos:
2 PLAZAS - POLICÍA LOCAL - CÁDIZ
1 PLAZA - INSPECTOR DE HACIENDA - MADRID
3 PLAZAS - LETRADO DE LA ADMINISTRACIÓN DE JUSTICIA - BARCELONA
1 PLAZA - ENFERMERO - VALENCIA
1 PLAZA - PROFESOR DE EDUCACIÓN FÍSICA - SEVILLA

Si NO encuentras un puesto específico, busca cualquier palabra del texto que indique el cargo.
Si realmente no hay nada, pon: 1 PLAZA - PERSONAL - [LUGAR]"""

        # Llamar a Claude API
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        data = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 60,
            "system": (
                "Eres un extractor de datos del BOE. Respondes EXCLUSIVAMENTE "
                "con UNA sola línea en MAYÚSCULAS con el formato "
                "'NÚMERO PLAZAS - PUESTO - LUGAR'. PROHIBIDO escribir "
                "explicaciones, análisis, razonamientos, viñetas, markdown, "
                "comillas o saltos de línea. Tu respuesta es solo esa línea."
            ),
            "temperature": 0,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        json_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=json_data, headers=headers, method='POST')

        response = urllib.request.urlopen(req, timeout=10)
        response_data = json.loads(response.read().decode('utf-8'))
        response.close()

        # Extraer el texto de la respuesta
        resumen_generado = response_data['content'][0]['text'].strip()

        # Validar/sanear: nunca devolver razonamiento ni texto sin formato
        limpio = _sanitizar_resumen(resumen_generado)
        if limpio:
            print(f"✨ Claude generó: {limpio}")
            return limpio

        fallback = _resumen_fallback(titulo, resumen)
        print(f"⚠️  Respuesta sin formato válido ({resumen_generado[:50]!r}). "
              f"Fallback: {fallback}")
        return fallback

    except Exception as e:
        fallback = _resumen_fallback(titulo, resumen)
        print(f"⚠️  Error con Claude: {e}. Fallback: {fallback}")
        return fallback


# Comunidades válidas (debe coincidir con migrar_comunidad.py y el frontend)
COMUNIDADES = [
    "Andalucía", "Aragón", "Asturias", "Baleares", "Canarias", "Cantabria",
    "Castilla-La Mancha", "Castilla y León", "Cataluña", "Comunidad Valenciana",
    "Extremadura", "Galicia", "La Rioja", "Madrid", "Murcia", "Navarra",
    "País Vasco", "Ceuta", "Melilla", "Nacional/Estatal",
]
_CA_VALIDAS = {c.lower(): c for c in COMUNIDADES}


def clasificar_comunidad(titulo, resumen):
    """Pregunta a Claude la comunidad autónoma de la convocatoria. Devuelve str o None."""
    prompt = f"""Convocatoria de oposición (BOE):
Título: {titulo}
Resumen: {resumen}

¿A qué comunidad autónoma de España corresponde el organismo convocante?

Responde ÚNICAMENTE con uno de estos valores EXACTOS, sin nada más:
{", ".join(COMUNIDADES)}

Reglas:
- Ayuntamientos, diputaciones y organismos locales → la comunidad de ese municipio/provincia.
- Juntas, gobiernos y consejerías autonómicas → su comunidad.
- Ministerios, INGESA, Guardia Civil, Policía Nacional, Administración General del Estado,
  agencias estatales, universidades de ámbito estatal → Nacional/Estatal.
- Si no puedes determinarla con seguridad, responde: DESCONOCIDA"""
    try:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        data = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 20,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'),
                                     headers=headers, method='POST')
        response = urllib.request.urlopen(req, timeout=10)
        result = json.loads(response.read().decode('utf-8'))
        response.close()
        texto = result['content'][0]['text'].strip()
        return _CA_VALIDAS.get(texto.lower())   # None si DESCONOCIDA / no válida
    except Exception as e:
        print(f"⚠️  Error clasificando comunidad: {e}")
        return None


def extraer_cuerpo(titulo):
    """Extrae el tipo de puesto del título"""
    texto_busqueda = titulo.upper()

    if "POLIC" in texto_busqueda:
        return ("👮 Policía", "Seguridad")
    elif "ADMINIST" in texto_busqueda:
        return ("📋 Administrativo", "Administración")
    elif "SANITARI" in texto_busqueda or "ENFERM" in texto_busqueda or "MÉDIC" in texto_busqueda:
        return ("🏥 Sanitario", "Sanidad")
    elif "JUSTICIA" in texto_busqueda or "JUZGADO" in texto_busqueda:
        return ("⚖️ Justicia", "Justicia")
    elif "TÉCNIC" in texto_busqueda or "INGENIER" in texto_busqueda:
        return ("🔧 Técnico", "Técnica")
    elif "HACIENDA" in texto_busqueda or "TESORERO" in texto_busqueda:
        return ("💰 Hacienda", "Hacienda")
    elif "EDUCACIÓN" in texto_busqueda or "PROFESOR" in texto_busqueda or "MAESTRO" in texto_busqueda:
        return ("📚 Educación", "Educación")
    elif "CORREOS" in texto_busqueda:
        return ("✉️ Correos", "Correos")
    else:
        return ("📄 Convocatoria", "Administración")


def obtener_icono_puesto(detalles):
    """Retorna el icono según el tipo de puesto extraído por Claude"""
    texto = detalles.upper()

    # SEGURIDAD
    if any(p in texto for p in ["POLICÍA", "POLICIA", "BOMBERO", "GUARDIA CIVIL", "SEGURIDAD", "VIGILANTE"]):
        return "👮"
    # SANIDAD
    elif any(p in texto for p in ["ENFERMERO", "MÉDICO", "MEDICO", "FARMACÉUTICO", "SANITARIO", "AUXILIAR DE ENFERMERÍA", "CELADOR"]):
        return "🏥"
    # JUSTICIA
    elif any(p in texto for p in ["LETRADO", "JUDICIAL", "JUEZ", "FISCAL", "GESTOR PROCESAL", "AUXILIAR JUDICIAL", "TRAMITACIÓN PROCESAL"]):
        return "⚖️"
    # EDUCACIÓN
    elif any(p in texto for p in ["PROFESOR", "DOCENTE", "MAESTRO", "UNIVERSITARIO", "CUERPOS DOCENTES", "EDUCACIÓN", "ENSEÑANZA"]):
        return "📚"
    # ADMINISTRACIÓN
    elif any(p in texto for p in ["ADMINISTRATIVO", "SECRETARIO", "AUXILIAR ADMINISTRATIVO", "GESTIÓN ADMINISTRATIVA"]):
        return "📋"
    # HACIENDA
    elif any(p in texto for p in ["INSPECTOR", "HACIENDA", "TESORERO", "RECAUDADOR", "AGENTE TRIBUTARIO"]):
        return "💰"
    # TÉCNICO / INGENIERÍA
    elif any(p in texto for p in ["TÉCNICO", "TECNICO", "INGENIERO", "INFORMÁTICO", "INFORMATICO", "ARQUITECTO"]):
        return "🔧"
    # SERVICIOS Y MANTENIMIENTO
    elif any(p in texto for p in ["JARDINERO", "PEÓN", "PEON", "LIMPIEZA", "OPERARIO", "MANTENIMIENTO"]):
        return "🧹"
    # PERSONAL FUNCIONARIO Y LABORAL GENÉRICO
    elif any(p in texto for p in ["PERSONAL FUNCIONARIO", "PERSONAL LABORAL", "VARIAS PLAZAS", "FUNCIONARIO Y LABORAL"]):
        return "🏛️"
    # DEFAULT
    else:
        return "📄"


def limpiar_titulo(titulo):
    """Extrae solo: 'Resolución de [fecha], de/del [organismo]'"""
    patron = r'^(Resolución[^,]+,\s+(?:de la|del|de)\s+[^,]+(?:\([^)]+\))?)'
    match = re.search(patron, titulo, re.IGNORECASE)

    if match:
        return match.group(1).strip()

    partes = titulo.split(',')
    if len(partes) >= 2:
        return f"{partes[0]}, {partes[1].strip()}"

    return titulo[:100]


def guardar_en_supabase(conv):
    """Guarda UNA convocatoria en Supabase. Retorna True si se guardó, False si ya existía."""
    cuerpo, categoria = extraer_cuerpo(conv['titulo'])
    data = {
        'fecha': conv['fecha'],
        'titulo': conv['titulo'],
        'enlace': conv['enlace'],
        'resumen': conv['resumen'],
        'cuerpo': cuerpo,
        'categoria': categoria,                       # ← el frontend filtra/agrupa por aquí
        'resumen_claude': conv.get('resumen_ia'),     # ← el frontend lee el puesto/plazas de aquí
    }
    # Comunidad autónoma (puede ser None → se infiere en el frontend)
    if conv.get('comunidad_autonoma'):
        data['comunidad_autonoma'] = conv['comunidad_autonoma']

    try:
        url = f"{SUPABASE_URL}/rest/v1/convocatorias"
        headers = {
            'apikey': SUPABASE_API_KEY,
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
        }

        json_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=json_data, headers=headers, method='POST')

        response = urllib.request.urlopen(req, timeout=10)
        response.read()
        response.close()

        print(f"✓ Guardada en Supabase: {conv['titulo'][:60]}...")
        return True

    except urllib.error.HTTPError as e:
        if e.code == 409:
            print(f"ℹ️  Ya existe: {conv['titulo'][:60]}...")
            return False
        # La columna comunidad_autonoma puede no existir aún → reintentar sin ella
        if e.code == 400 and 'comunidad_autonoma' in data:
            print("ℹ️  Columna comunidad_autonoma no existe aún; reintento sin ella.")
            data.pop('comunidad_autonoma', None)
            try:
                req2 = urllib.request.Request(
                    url, data=json.dumps(data).encode('utf-8'),
                    headers=headers, method='POST')
                r2 = urllib.request.urlopen(req2, timeout=10)
                r2.read(); r2.close()
                print(f"✓ Guardada (sin comunidad): {conv['titulo'][:60]}...")
                return True
            except urllib.error.HTTPError as e2:
                if e2.code == 409:
                    return False
                print(f"❌ Error guardando en Supabase (reintento): {e2}")
                return False
        print(f"❌ Error guardando en Supabase: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def enviar_a_telegram(conv):
    """Envía mensaje limpio y estético a Telegram"""

    try:
        fecha_obj = parsedate_to_datetime(conv['fecha'])
        meses = {
            1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
            5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
            9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
        }
        fecha_spanish = f"{fecha_obj.day} de {meses[fecha_obj.month]} de {fecha_obj.year}"
    except:
        fecha_spanish = conv['fecha']

    # Extraer datos
    detalles_ia = conv.get('resumen_ia', 'Convocatoria disponible')
    partes = detalles_ia.split(' - ')
    plazas = partes[0].strip() if len(partes) > 0 else "N/A"
    puesto = partes[1].strip() if len(partes) > 1 else "Convocatoria"
    ubicacion = partes[2].strip() if len(partes) > 2 else "España"

    # Icono según puesto
    icono = obtener_icono_puesto(detalles_ia)

    # Título limpio
    titulo_limpio = limpiar_titulo(conv['titulo'])

    # Mensaje final
    mensaje = (
        f"🎯 <b>NUEVA CONVOCATORIA</b>\n\n"
        f"📰 <b>{titulo_limpio}</b>\n\n"
        f"{icono} <b>{puesto}</b>\n\n"
        f"🔢 Plazas: {plazas}\n"
        f"📍 Ubicación: {ubicacion}\n"
        f"📅 Publicado: {fecha_spanish}\n\n"
        f"<a href=\"{conv['enlace']}\">📄 Ver en BOE</a>\n\n"
        f"#oposiciones #empleo #BOE"
    )

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': mensaje,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data).encode('utf-8'),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        response = urllib.request.urlopen(req, timeout=10)
        response.read()
        response.close()
        print(f"✅ Enviada: {titulo_limpio[:60]}...")
    except Exception as e:
        print(f"❌ Error Telegram: {e}")


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


def generar_html_convocatoria(conv, categoria):
    """Genera un archivo HTML por convocatoria"""

    slug = generar_slug(conv['titulo'], conv.get('ref_boe', ''))
    html_path = WEB_CONVOCATORIA_DIR / slug

    # Si ya existe, no regenerar
    if html_path.exists():
        print(f"⏭️  HTML ya existe: {slug}")
        return slug

    # Parsear fecha
    try:
        fecha_obj = parsedate_to_datetime(conv['fecha'])
        fecha_str = fecha_obj.strftime("%d %b %Y").replace(" 0", " ")
        fecha_schema = fecha_obj.strftime("%Y-%m-%d")
    except:
        fecha_str = conv['fecha']
        fecha_schema = datetime.now().strftime("%Y-%m-%d")

    valid_through = (datetime.fromisoformat(fecha_schema) + timedelta(days=30)).strftime("%Y-%m-%d")

    desc = conv.get('resumen_ia', 'Convocatoria disponible')
    meta_desc = f"Resumen: {desc[:120]}. Enlace al BOE oficial."
    canonical = f"https://oponoticias.com/convocatoria/{slug}"

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{conv['titulo']} — Convocatoria | OpoNoticias</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="{canonical}">
  <meta name="robots" content="index, follow">
  <meta name="theme-color" content="#5A5047">
  <script>document.documentElement.className += ' js';</script>

  <meta property="og:type" content="article">
  <meta property="og:site_name" content="OpoNoticias">
  <meta property="og:title" content="{conv['titulo'][:100]}">
  <meta property="og:description" content="{desc[:160]}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="https://oponoticias.com/assets/banner-telegram.svg">
  <meta property="og:locale" content="es_ES">
  <meta name="twitter:card" content="summary_large_image">

  <link rel="icon" type="image/svg+xml" href="../assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/style.css">

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "{conv['titulo']}",
    "description": "{desc}",
    "datePosted": "{fecha_schema}",
    "validThrough": "{valid_through}",
    "employmentType": "FULL_TIME",
    "hiringOrganization": {{"@type": "Organization", "name": "Administración Pública"}},
    "jobLocation": {{"@type": "Place", "address": {{"@type": "PostalAddress", "addressCountry": "ES"}}}},
    "industry": "Administración pública - {categoria}",
    "url": "{canonical}"
  }}
  </script>
</head>
<body>

  <header class="site-header">
    <div class="container">
      <nav class="nav" aria-label="Principal">
        <a href="../index.html" aria-label="OpoNoticias - Inicio"><img src="../assets/logo.svg" alt="OpoNoticias" class="nav-logo"></a>
        <div class="nav-links">
          <a href="../index.html#categorias">Categorías</a>
          <a href="../boe-hoy.html">El BOE de hoy</a>
          <a href="../blog.html">Blog</a>
          <a href="../index.html#como-funciona">Cómo funciona</a>
        </div>
        <div class="nav-cta">
          <a href="../index.html#categorias" class="btn btn-ghost">Explorar</a>
          <a href="https://t.me/OPONOTICIAS" class="btn btn-primary" rel="noopener" target="_blank">Telegram</a>
        </div>
      </nav>
    </div>
  </header>

  <main>
    <div class="container">
      <nav class="breadcrumb" aria-label="Migas de pan">
        <a href="../index.html">Inicio</a>
        <span class="sep">/</span>
        <a href="../index.html#categorias">{categoria}</a>
        <span class="sep">/</span>
        <span aria-current="page">{conv['titulo'][:80]}</span>
      </nav>

      <div class="article-layout">
        <article>
          <header class="article-header reveal">
            <span class="article-tag">{categoria}</span>
            <h1>{conv['titulo']}</h1>
            <div class="article-meta">
              <span>Publicado: <b>{fecha_str}</b></span>
              <span>Fuente: <b>BOE</b></span>
              <span>Referencia: <b>{conv.get('ref_boe', 'BOE')}</b></span>
            </div>
          </header>

          <div class="prose reveal">
            <p class="lead">{desc}</p>

            <h2>Requisitos principales</h2>
            <ul>
              <li>Tener la <strong>titulación</strong> exigida para el puesto.</li>
              <li>Poseer la <strong>nacionalidad española</strong> o de un país de la UE.</li>
              <li>No haber sido <strong>separado del servicio</strong> de ninguna administración pública.</li>
            </ul>

            <div class="info-box">
              <h3>Información de la convocatoria</h3>
              <table class="info-table">
                <tr><th>Categoría</th><td>{categoria}</td></tr>
                <tr><th>Publicación</th><td>{fecha_str}</td></tr>
                <tr><th>Referencia BOE</th><td>{conv.get('ref_boe', 'BOE')}</td></tr>
              </table>
            </div>

            <a href="{conv['enlace']}" class="boe-link" rel="noopener" target="_blank">
              <span class="l"><b>Leer el texto oficial en el BOE</b><span>boe.es · {conv.get('ref_boe', 'BOE')}</span></span>
              <span class="arrow">→</span>
            </a>

            <p style="margin-top:30px; color:var(--gray); font-size:0.9rem;">Este resumen tiene carácter informativo. La información válida y vinculante es siempre la publicada en el Boletín Oficial del Estado.</p>
          </div>
        </article>

        <aside class="sidebar">
          <div class="widget widget-tg reveal">
            <h4>Canal oficial</h4>
            <p>Recibe convocatorias cada mañana, resumidas y filtradas.</p>
            <a href="https://t.me/OPONOTICIAS" class="btn btn-accent" rel="noopener" target="_blank" style="width:100%; justify-content:center;">Unirse a Telegram →</a>
          </div>
        </aside>
      </div>
    </div>
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <img src="../assets/logo.svg" alt="OpoNoticias">
          <p>Las convocatorias de oposiciones del BOE, resumidas en lenguaje claro.</p>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© 2026 OpoNoticias · oponoticias.com</span>
      </div>
    </div>
  </footer>

  <script src="../assets/script.js" defer></script>
</body>
</html>"""

    try:
        WEB_CONVOCATORIA_DIR.mkdir(parents=True, exist_ok=True)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"✅ Generado HTML: {slug}")
        return slug
    except Exception as e:
        print(f"❌ Error generando HTML: {e}")
        return None


def regenerar_sitemap(slugs_nuevos):
    """Regenera el sitemap.xml incluyendo TODAS las páginas de convocatoria existentes."""
    try:
        hoy = datetime.now().strftime("%Y-%m-%d")
        urls = [
            ("https://oponoticias.com/", hoy, "daily", "1.0"),
            ("https://oponoticias.com/boe-hoy.html", hoy, "daily", "0.9"),
            ("https://oponoticias.com/blog.html", hoy, "weekly", "0.8"),
            ("https://oponoticias.com/categoria/educacion.html", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/sanidad.html", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/justicia.html", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/seguridad.html", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/administracion.html", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/hacienda.html", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/correos.html", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/tecnica.html", hoy, "daily", "0.8"),
        ]

        # Recoger todos los slugs históricos ya generados en el repo web
        slugs_existentes = set()
        if WEB_CONVOCATORIA_DIR.exists():
            for f in sorted(WEB_CONVOCATORIA_DIR.glob("*.html")):
                slugs_existentes.add(f.name)

        # Añadir también los del día (por si aún no están en disco)
        for slug in slugs_nuevos:
            slugs_existentes.add(slug)

        # Eliminar duplicados manteniendo orden determinista
        for slug in sorted(slugs_existentes):
            urls.append((
                f"https://oponoticias.com/convocatoria/{slug}",
                hoy,
                "weekly",
                "0.7"
            ))

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        ]

        for url, lastmod, changefreq, priority in urls:
            xml_lines.append(f"""  <url>
    <loc>{url}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>""")

        xml_lines.append("</urlset>")

        with open(WEB_SITEMAP_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(xml_lines))

        print(f"✅ Sitemap regenerado: {len(urls)} URLs")
        return True
    except Exception as e:
        print(f"❌ Error regenerando sitemap: {e}")
        return False


def commit_a_github(mensaje, archivos):
    """Hace commit y push a GitHub"""
    if not GITHUB_TOKEN:
        print("⚠️  No hay GITHUB_TOKEN. Saltando push a GitHub.")
        return False

    try:
        subprocess.run(
            ["git", "-C", WEB_REPO_PATH, "config", "user.name", "OpoNoticias Bot"],
            check=False
        )
        subprocess.run(
            ["git", "-C", WEB_REPO_PATH, "config", "user.email", "bot@oponoticias.com"],
            check=False
        )

        for archivo in archivos:
            subprocess.run(
                ["git", "-C", WEB_REPO_PATH, "add", archivo],
                check=True,
                capture_output=True
            )

        subprocess.run(
            ["git", "-C", WEB_REPO_PATH, "commit", "-m", mensaje],
            check=True,
            capture_output=True
        )

        url_repo = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
        subprocess.run(
            ["git", "-C", WEB_REPO_PATH, "push", url_repo, "main"],
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )

        print(f"✅ Commit y push a GitHub: {mensaje}")
        return True

    except subprocess.CalledProcessError as e:
        msg = str(e)
        if GITHUB_TOKEN:
            msg = msg.replace(GITHUB_TOKEN, "***")
        print(f"❌ Error en git: {msg}")
        return False
    except Exception as e:
        print(f"❌ Error en commit a GitHub: {e}")
        return False


if __name__ == "__main__":
    convocatorias = leer_boe_rss()

    if convocatorias:
        nuevas = 0
        slugs_generados = []

        for conv in convocatorias:
            cuerpo, categoria = extraer_cuerpo(conv['titulo'])

            print(f"\n🤖 Analizando: {conv['titulo'][:60]}...")
            conv['resumen_ia'] = generar_resumen_con_claude(conv['titulo'], conv['resumen'])
            conv['comunidad_autonoma'] = clasificar_comunidad(conv['titulo'], conv['resumen'])

            if guardar_en_supabase(conv):
                enviar_a_telegram(conv)

                # Generar HTML
                slug = generar_html_convocatoria(conv, categoria)
                if slug:
                    slugs_generados.append(slug)

                nuevas += 1
                time.sleep(2)

        # Regenerar sitemap y hacer push
        if slugs_generados:
            regenerar_sitemap(slugs_generados)

            archivos_commit = [
                f"convocatoria/{slug}" for slug in slugs_generados
            ] + ["sitemap.xml"]

            fecha_hoy = datetime.now().strftime("%d/%m/%Y")
            commit_a_github(f"Auto: {nuevas} nuevas convocatorias ({fecha_hoy})", archivos_commit)

        print(f"\n✅ Procesadas {len(convocatorias)} convocatorias. Nuevas: {nuevas}")
    else:
        print("\n❌ No se encontraron convocatorias")
