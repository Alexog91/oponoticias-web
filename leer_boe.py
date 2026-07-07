import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import json
import os
from web_utils import limpiar_hrefs
import time
import re
import subprocess
import html as html_lib
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
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "")  # webhook Make.com → Facebook
INSTAGRAM_WEBHOOK_URL = os.environ.get("INSTAGRAM_WEBHOOK_URL", "")  # webhook Make.com → Instagram (carrusel)
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")  # chat privado del admin (resumen diario)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "Alexog91/oponoticias-web"
WEB_REPO_PATH = os.environ.get("WEB_REPO_PATH", "./oponoticias-web")

# Rutas al proyecto web
WEB_CONVOCATORIA_DIR = Path(WEB_REPO_PATH) / "convocatoria"
WEB_SITEMAP_PATH = Path(WEB_REPO_PATH) / "sitemap.xml"


def leer_boe_rss():
    print("🔄 Leyendo RSS del BOE...")

    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    max_reintentos = 5
    esperas = [5, 10, 20, 30]  # segundos de espera entre reintentos

    for intento in range(max_reintentos):
        try:
            req = urllib.request.Request(RSS_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
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
            if intento < max_reintentos - 1:
                espera = esperas[intento]
                print(f"⚠️  Intento {intento + 1}/{max_reintentos} falló: {e}")
                print(f"   Reintentando en {espera} segundos...")
                time.sleep(espera)
            else:
                print(f"❌ Error al leer el RSS tras {max_reintentos} intentos: {e}")
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
        # Authorization: Bearer es OBLIGATORIO para que PostgREST autentique
        # como service_role y el INSERT pueda saltarse las políticas RLS de la
        # tabla. Sin esta cabecera el rol es 'anon' y el RLS (solo lectura)
        # rechaza el alta con 401/42501 ("violates row-level security policy").
        headers = {
            'apikey': SUPABASE_API_KEY,
            'Authorization': f'Bearer {SUPABASE_API_KEY}',
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


def telegram_ya_enviado(enlace):
    """Comprueba en Supabase si la convocatoria ya se envió a Telegram.
    Devuelve True si la fila existe y telegram_enviado=true."""
    try:
        qs = urllib.parse.urlencode({
            'enlace': f'eq.{enlace}',
            'select': 'telegram_enviado',
        })
        url = f"{SUPABASE_URL}/rest/v1/convocatorias?{qs}"
        headers = {
            'apikey': SUPABASE_API_KEY,
            'Authorization': f'Bearer {SUPABASE_API_KEY}',
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            rows = json.loads(r.read())
        return bool(rows and rows[0].get('telegram_enviado'))
    except Exception as e:
        print(f"⚠️  No se pudo comprobar flag Telegram: {e}")
        return False


def marcar_telegram_enviado(enlace):
    """Marca la convocatoria como ya enviada a Telegram (flag en Supabase)."""
    try:
        qs = urllib.parse.urlencode({'enlace': f'eq.{enlace}'})
        url = f"{SUPABASE_URL}/rest/v1/convocatorias?{qs}"
        headers = {
            'apikey': SUPABASE_API_KEY,
            'Authorization': f'Bearer {SUPABASE_API_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal',
        }
        data = json.dumps({'telegram_enviado': True}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='PATCH')
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        return True
    except Exception as e:
        print(f"⚠️  No se pudo marcar flag Telegram: {e}")
        return False


def enviar_a_telegram(conv):
    """Envía mensaje limpio y estético a Telegram. Devuelve True si se envió."""

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

    # Escapar todo el texto derivado de datos para HTML válido en Telegram
    titulo_limpio = html_lib.escape(limpiar_titulo(conv['titulo']))
    plazas        = html_lib.escape(plazas)
    puesto        = html_lib.escape(puesto)
    ubicacion     = html_lib.escape(ubicacion)
    fecha_spanish = html_lib.escape(fecha_spanish)
    enlace_esc    = html_lib.escape(conv['enlace'], quote=True)

    mensaje = (
        f"🎯 <b>NUEVA CONVOCATORIA</b>\n\n"
        f"📰 <b>{titulo_limpio}</b>\n\n"
        f"{icono} <b>{puesto}</b>\n\n"
        f"🔢 Plazas: {plazas}\n"
        f"📍 Ubicación: {ubicacion}\n"
        f"📅 Publicado: {fecha_spanish}\n\n"
        f"<a href=\"{enlace_esc}\">📄 Ver en BOE</a>\n\n"
        f"——————————————\n"
        f"📲 <b><a href=\"https://oponoticias.com\">OpoNoticias.com</a></b> — busca y filtra todas las convocatorias\n"
        f"📘 <a href=\"https://www.facebook.com/profile.php?id=61590965302457\">Facebook</a>  ·  📸 <a href=\"https://www.instagram.com/oponoticiason/\">Instagram</a>  ·  💬 <a href=\"https://whatsapp.com/channel/0029Vb8BReo89ind8LpWxp26\">WhatsApp</a>\n\n"
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
        print(f"✅ Enviada a Telegram: {titulo_limpio[:60]}...")
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"❌ Error Telegram: HTTP {e.code} — {body[:300]}")
        return False
    except Exception as e:
        print(f"❌ Error Telegram: {e}")
        return False


def enviar_resumen_privado(convocatorias_enviadas):
    """Envía un resumen diario al chat privado del admin, listo para copiar al Canal de WhatsApp."""
    if not TELEGRAM_ADMIN_CHAT_ID or not convocatorias_enviadas:
        return
    top5 = sorted(convocatorias_enviadas, key=_plazas_num, reverse=True)[:5]
    lineas = []
    for conv in top5:
        partes = [p.strip() for p in (conv.get('resumen_ia') or '').split(' - ')]
        plazas = partes[0] if partes else "?"
        puesto  = partes[1] if len(partes) > 1 else limpiar_titulo(conv['titulo'])[:45]
        # Escapar para parse_mode=HTML: un '&', '<' o '>' en el puesto rompía el
        # envío con HTTP 400 (el envío al canal sí escapaba; este no).
        plazas = html_lib.escape(plazas)
        puesto = html_lib.escape(puesto[:50])
        lineas.append(f"• {plazas} — {puesto}")
    n = len(convocatorias_enviadas)
    fecha_str = datetime.now().strftime("%d/%m/%Y")
    mensaje = (
        f"📋 <b>BOE del {fecha_str} — {n} convocatorias nuevas</b>\n\n"
        f"🏆 <b>Top por plazas:</b>\n"
        + "\n".join(lineas) + "\n\n"
        "🔎 <b>Consulta todas las convocatorias en detalle:</b>\n"
        "📌 https://oponoticias.com\n"
        "✈️ https://t.me/OPONOTICIAS\n"
        "📘 https://www.facebook.com/profile.php?id=61590965302457\n"
        "📸 https://www.instagram.com/oponoticiason/\n"
        "💬 https://whatsapp.com/channel/0029Vb8BReo89ind8LpWxp26\n\n"
        "<i>☝️ Copia esto en el Canal de WhatsApp</i>"
    )
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_ADMIN_CHAT_ID,
            'text': mensaje,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data).encode('utf-8'),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        urllib.request.urlopen(req, timeout=10).read()
        print("✅ Resumen diario enviado al admin por privado")
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:300]
        print(f"⚠️  Resumen privado falló: HTTP {e.code} · {cuerpo}")
        if e.code == 400 and "chat not found" in cuerpo:
            print("    → TELEGRAM_ADMIN_CHAT_ID incorrecto o el admin no ha abierto "
                  "@OPONOTICIAS_BOT (debe pulsar Start y usar su chat_id personal).")
    except Exception as e:
        print(f"⚠️  Resumen privado: {e}")


def publicar_tweet_resumen(convocatorias_enviadas):
    """Publica un tweet-resumen del día en X (Buffer vía Make), reutilizando el
    mismo top de plazas que el resumen de WhatsApp.

    skip_facebook=true → el filtro del escenario de Make bloquea Facebook y solo
    publica en X. Best-effort: nunca bloquea el flujo principal.
    """
    if not MAKE_WEBHOOK_URL or not convocatorias_enviadas:
        return False
    top = sorted(convocatorias_enviadas, key=_plazas_num, reverse=True)[:3]
    lineas = []
    for conv in top:
        partes = [p.strip() for p in (conv.get('resumen_ia') or '').split(' - ')]
        plazas = partes[0] if partes and partes[0] else ""
        puesto = partes[1] if len(partes) > 1 else limpiar_titulo(conv['titulo'])
        lineas.append(f"• {plazas} {puesto[:32]}".strip())
    n = len(convocatorias_enviadas)
    fecha_str = datetime.now().strftime("%d/%m")
    tweet = (
        f"📋 BOE {fecha_str} · {n} convocatorias nuevas\n\n"
        "🏆 Top plazas:\n" + "\n".join(lineas) + "\n\n"
        "🔎 Todas en oponoticias.com\n"
        "#oposiciones #empleopublico"
    )
    if len(tweet) > 280:
        tweet = tweet[:279] + "…"
    try:
        payload = json.dumps({
            "tweet": tweet,
            "imagen_tweet": "https://oponoticias.com/social/tweet-card.png",
            "skip_facebook": True,
        }).encode('utf-8')
        req = urllib.request.Request(
            MAKE_WEBHOOK_URL, data=payload,
            headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.urlopen(req, timeout=10).read()
        print("🐦 Tweet-resumen del día enviado a X")
        return True
    except Exception as e:
        print(f"⚠️  Tweet-resumen X falló (no bloquea): {e}")
        return False


def enlace_web_convocatoria(conv):
    """URL de la página en oponoticias.com si ya existe el HTML, si no la home."""
    slug = generar_slug(conv['titulo'], conv.get('ref_boe', ''))
    if (WEB_CONVOCATORIA_DIR / slug).exists():
        return f"https://oponoticias.com/convocatoria/{slug.replace('.html', '')}"
    return "https://oponoticias.com"


def enviar_a_facebook(conv, incluir_tweet=True):
    """[OBSOLETO desde 22 jun 2026 — ya NO se llama]

    Publicaba 1 post por convocatoria (~32/día) → Meta bloqueó la cuenta de
    desarrollador por spam. Sustituido por `publicar_facebook_agrupado()`
    (máx. 6 posts/día) + `enviar_tweet_x()` (X). Se conserva como referencia.

    Publica en Facebook directamente vía Graph API (texto plano, sin HTML).

    Vía preferente: API directa de Meta (gratis, sin límite de operaciones).
    Fallback: webhook de Make.com si la API directa no está configurada.
    X (Buffer) sigue saliendo por Make si MAKE_WEBHOOK_URL está configurado.

    Best-effort: si falla no bloquea ni revierte el envío de Telegram.
    """
    import publicar_meta
    if not (publicar_meta.configurado() or MAKE_WEBHOOK_URL):
        return False
    try:
        partes = [p.strip() for p in (conv.get('resumen_ia') or '').split(' - ')]
        plazas = (partes[0] if partes and partes[0] else "").capitalize()
        puesto = partes[1].capitalize() if len(partes) > 1 else "Convocatoria"
        categoria = conv.get('categoria', '') or ''
        comunidad = conv.get('comunidad_autonoma', '') or ''
        titulo = limpiar_titulo(conv['titulo'])

        # Formato conciso: cabe visible sin "Ver más" (~4 líneas)
        lineas = [f"🎯 {titulo[:70]}{'…' if len(titulo) > 70 else ''}"]
        if plazas or puesto:
            lineas.append(f"🔢 {plazas} · {puesto[:45]}" if plazas and puesto else f"🔢 {plazas or puesto}")
        if comunidad:
            lineas.append(f"📍 {comunidad}")
        lineas += [
            f"🔗 {enlace_web_convocatoria(conv)}",
            "#oposiciones #BOE #empleopublico",
        ]
        # Tweet para X (Buffer vía Make): mismo webhook, campo separado
        partes_x  = [p.strip() for p in (conv.get('resumen_ia') or '').split(' - ')]
        plazas_x  = partes_x[0] if partes_x else ""
        puesto_x  = partes_x[1] if len(partes_x) > 1 else ""
        ccaa_tags = {
            "Andalucía":"#Andalucia","Aragón":"#Aragon","Asturias":"#Asturias",
            "Canarias":"#Canarias","Cantabria":"#Cantabria",
            "Castilla-La Mancha":"#CastillaLaMancha","Castilla y León":"#CastillaYLeon",
            "Cataluña":"#Cataluna","Ceuta":"#Ceuta","Extremadura":"#Extremadura",
            "Galicia":"#Galicia","Islas Baleares":"#IslasBaleares","La Rioja":"#LaRioja",
            "Madrid":"#Madrid","Melilla":"#Melilla","Murcia":"#Murcia",
            "Navarra":"#Navarra","País Vasco":"#PaisVasco",
            "Comunitat Valenciana":"#ComunidadValenciana",
        }
        tag_ccaa  = ccaa_tags.get(comunidad, "")
        hashtags  = f"#oposiciones #BOE {tag_ccaa}".strip()
        t_lineas  = [f"📋 {titulo[:50]}{'…' if len(titulo)>50 else ''}"]
        if puesto_x:
            t_lineas.append(f"🔢 {plazas_x} · {puesto_x[:40]}")
        if comunidad:
            t_lineas.append(f"📍 {comunidad}")
        t_lineas.append(f"\n🔗 {enlace_web_convocatoria(conv)}")
        t_lineas.append(
            "\n📘 https://www.facebook.com/profile.php?id=61590965302457"
            "  ·  📸 https://www.instagram.com/oponoticiason/"
            "  ·  ✈️ https://t.me/OPONOTICIAS"
        )
        t_lineas.append(f"\n{hashtags}")
        tweet_texto = "\n".join(t_lineas)

        # Imagen propia de la convocatoria (misma plantilla que Instagram):
        # muestra organismo, puesto, plazas y lugar → cada post es único y
        # atractivo en el feed móvil, donde el texto se corta con "Ver más".
        # Best-effort: si la generación/subida falla, usa la tarjeta genérica.
        imagen_fb = "https://oponoticias.com/social/fb-card.png"
        try:
            import generar_imagen_instagram as gii
            import hashlib
            uid = hashlib.md5((conv.get('enlace', '') + titulo).encode('utf-8')).hexdigest()[:12]
            nombre_img = f"fb/{datetime.now().strftime('%Y-%m-%d')}-{uid}.jpg"
            url_img = gii.generar_y_subir(_datos_imagen(conv), nombre_img)
            if url_img:
                imagen_fb = url_img
        except Exception as e:
            print(f"⚠️  Imagen Facebook propia falló, uso genérica ({e})")

        mensaje = "\n".join(lineas)

        # ── Vía preferente: Graph API directa (gratis, sin límite de Make) ──────
        if publicar_meta.configurado():
            ok = publicar_meta.publicar_foto_facebook(imagen_fb, mensaje)
            # X/Twitter (Buffer vía Make) SOLO para las destacadas del día.
            # skip_facebook=true → el filtro del escenario bloquea Facebook y solo
            # publica en X, así NO se duplica el post de FB que ya hizo la API directa.
            if incluir_tweet and MAKE_WEBHOOK_URL:
                try:
                    payload = json.dumps({
                        "tweet": tweet_texto,
                        "imagen_tweet": "https://oponoticias.com/social/tweet-card.png",
                        "skip_facebook": True,
                    }).encode('utf-8')
                    req = urllib.request.Request(
                        MAKE_WEBHOOK_URL, data=payload,
                        headers={'Content-Type': 'application/json'}, method='POST')
                    urllib.request.urlopen(req, timeout=10).read()
                except Exception as e:
                    print(f"⚠️  Tweet X vía Make falló (no bloquea): {e}")
            return ok

        # ── Fallback: webhook de Make.com (comportamiento anterior) ────────────
        datos_post = {
            "mensaje": mensaje,
            "enlace": enlace_web_convocatoria(conv),
            "imagen_facebook": imagen_fb,
        }
        # X (Buffer) solo para las convocatorias destacadas del día: evita saturar
        # el plan gratuito de Buffer y que X corte el token por spam. Las que no
        # llevan tweet hacen fallar a Buffer y el handler "Resume" las pasa a Facebook.
        if incluir_tweet:
            datos_post["tweet"] = tweet_texto
            datos_post["imagen_tweet"] = "https://oponoticias.com/social/tweet-card.png"
        payload = json.dumps(datos_post).encode('utf-8')
        req = urllib.request.Request(
            MAKE_WEBHOOK_URL, data=payload,
            headers={'Content-Type': 'application/json'}, method='POST'
        )
        urllib.request.urlopen(req, timeout=10).read()
        print(f"📘 Enviada a Facebook: {titulo[:50]}…")
        return True
    except Exception as e:
        print(f"⚠️  Error Facebook (no bloquea): {e}")
        return False



_MESES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                'jul', 'ago', 'sep', 'oct', 'nov', 'dic']


def _extraer_organismo(titulo):
    """Organismo corto a partir del título largo del BOE."""
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
    return titulo[:60]


def _datos_imagen(conv):
    """Construye el dict de datos para la plantilla de Instagram."""
    partes = [p.strip() for p in (conv.get('resumen_ia') or '').split(' - ')]
    plazas = partes[0] if partes and partes[0] else "—"
    puesto = partes[1] if len(partes) > 1 and partes[1] else "Convocatoria"
    lugar = conv.get('comunidad_autonoma') or (partes[2] if len(partes) > 2 else "España")
    hoy = datetime.now()
    return {
        "fecha": f"{hoy.day} {_MESES_CORTO[hoy.month - 1]} {hoy.year}",
        "organismo": _extraer_organismo(conv['titulo']),
        "puesto": puesto,
        "plazas": plazas,
        "lugar": lugar or "España",
    }


def _plazas_num(conv):
    """Número de plazas como entero (0 si no es numérico) para ordenar."""
    partes = (conv.get('resumen_ia') or '').split(' - ')
    if not partes:
        return 0
    m = re.search(r'\d+', partes[0])
    return int(m.group()) if m else 0


# Hashtags por CCAA para los tweets de X (Buffer vía Make).
_CCAA_TAGS = {
    "Andalucía": "#Andalucia", "Aragón": "#Aragon", "Asturias": "#Asturias",
    "Canarias": "#Canarias", "Cantabria": "#Cantabria",
    "Castilla-La Mancha": "#CastillaLaMancha", "Castilla y León": "#CastillaYLeon",
    "Cataluña": "#Cataluna", "Ceuta": "#Ceuta", "Extremadura": "#Extremadura",
    "Galicia": "#Galicia", "Islas Baleares": "#IslasBaleares", "La Rioja": "#LaRioja",
    "Madrid": "#Madrid", "Melilla": "#Melilla", "Murcia": "#Murcia",
    "Navarra": "#Navarra", "País Vasco": "#PaisVasco",
    "Comunitat Valenciana": "#ComunidadValenciana",
}


def enviar_tweet_x(conv):
    """Envía SOLO el tweet (X vía Buffer/Make) de una convocatoria destacada.

    `skip_facebook=True` para que el escenario de Make no duplique en Facebook
    (FB ahora va por `publicar_facebook_agrupado`, no por aquí). Best-effort.
    """
    if not MAKE_WEBHOOK_URL:
        return False
    try:
        partes = [p.strip() for p in (conv.get('resumen_ia') or '').split(' - ')]
        plazas = partes[0] if partes else ""
        puesto = partes[1] if len(partes) > 1 else ""
        comunidad = conv.get('comunidad_autonoma', '') or ''
        titulo = limpiar_titulo(conv['titulo'])
        hashtags = f"#oposiciones #BOE {_CCAA_TAGS.get(comunidad, '')}".strip()
        t = [f"📋 {titulo[:50]}{'…' if len(titulo) > 50 else ''}"]
        if puesto:
            t.append(f"🔢 {plazas} · {puesto[:40]}")
        if comunidad:
            t.append(f"📍 {comunidad}")
        t.append(f"\n🔗 {enlace_web_convocatoria(conv)}")
        t.append("\n📘 https://www.facebook.com/profile.php?id=61590965302457"
                 "  ·  📸 https://www.instagram.com/oponoticiason/"
                 "  ·  ✈️ https://t.me/OPONOTICIAS")
        t.append(f"\n{hashtags}")
        payload = json.dumps({
            "tweet": "\n".join(t),
            "imagen_tweet": "https://oponoticias.com/social/tweet-card.png",
            "skip_facebook": True,
        }).encode('utf-8')
        req = urllib.request.Request(
            MAKE_WEBHOOK_URL, data=payload,
            headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.urlopen(req, timeout=10).read()
        print(f"🐦 Tweet X (Buffer/Make): {titulo[:40]}…")
        return True
    except Exception as e:
        print(f"⚠️  Tweet X falló (no bloquea): {e}")
        return False


def _linea_fb_conv(conv):
    """Una entrada del listado de un post agrupado de Facebook."""
    partes = [p.strip() for p in (conv.get('resumen_ia') or '').split(' - ')]
    plazas = partes[0] if partes and partes[0] else ""
    puesto = partes[1] if len(partes) > 1 else ""
    comunidad = conv.get('comunidad_autonoma', '') or ''
    titulo = limpiar_titulo(conv['titulo'])
    det = " · ".join([x for x in [plazas, puesto[:40], comunidad] if x])
    linea = f"🎯 {titulo[:80]}{'…' if len(titulo) > 80 else ''}"
    if det:
        linea += f"\n   {det}"
    linea += f"\n   🔗 {enlace_web_convocatoria(conv)}"
    return linea


def publicar_facebook_agrupado(convocatorias, max_posts=6):
    """Publica las convocatorias del día en COMO MUCHO `max_posts` posts de FB.

    Antes se publicaba 1 post por convocatoria (~32/día) → Meta lo interpretó
    como spam/automatización y BLOQUEÓ la cuenta de desarrollador (incidente
    22 jun 2026). Ahora se reparten en grupos: cada post agrupa varias
    convocatorias (su listado con enlaces) + la tarjeta de la de más plazas del
    grupo. Telegram/web/email siguen recibiéndolas todas. Best-effort.
    """
    import publicar_meta
    if not convocatorias:
        return
    if not publicar_meta.configurado():
        print("📘 Facebook: API directa no configurada, se omite el agrupado.")
        return

    import math
    import hashlib
    try:
        import generar_imagen_instagram as gii
    except Exception:
        gii = None

    convs = sorted(convocatorias, key=_plazas_num, reverse=True)
    grupos_n = min(max_posts, len(convs))
    tam = math.ceil(len(convs) / grupos_n)
    grupos = [convs[i:i + tam] for i in range(0, len(convs), tam)]
    total = len(grupos)

    hoy = datetime.now()
    fecha_txt = f"{hoy.day} {_MESES_CORTO[hoy.month - 1]}"
    publicados = 0

    for idx, grupo in enumerate(grupos, 1):
        # Tarjeta de la convocatoria con más plazas del grupo (best-effort)
        imagen = None
        if gii:
            try:
                lider = grupo[0]
                uid = hashlib.md5((lider.get('enlace', '') + lider['titulo'])
                                  .encode('utf-8')).hexdigest()[:10]
                imagen = gii.generar_y_subir(
                    _datos_imagen(lider), f"fb/{hoy:%Y-%m-%d}-g{idx}-{uid}.jpg")
            except Exception as e:
                print(f"⚠️  Tarjeta FB grupo {idx} falló ({e})")

        encabezado = (f"📋 Convocatorias del BOE · {fecha_txt}"
                      + (f" ({idx}/{total})" if total > 1 else ""))
        cuerpo = "\n\n".join(_linea_fb_conv(c) for c in grupo)
        mensaje = f"{encabezado}\n\n{cuerpo}\n\n#oposiciones #BOE #empleopublico #opositar"

        ok = False
        if imagen:
            ok = publicar_meta.publicar_foto_facebook(imagen, mensaje)
        if not ok:
            ok = publicar_meta.publicar_enlace_facebook(mensaje)
        if ok:
            publicados += 1
        time.sleep(3)

    print(f"📘 Facebook: {publicados}/{total} posts agrupados "
          f"({len(convs)} convocatorias del día).")


def publicar_facebook_boletin(convocatorias):
    """Publica UN post-boletín diario en Facebook con enlace a la web (boe-hoy).

    Sustituye a `publicar_facebook_agrupado` (6 posts de imagen): un único post de
    ENLACE con el total del día + algunas convocatorias, que lleva tráfico a
    oponoticias.com/boe-hoy (Facebook genera el preview clicable a partir del
    og:image de la página). Como no adjunta tarjeta de imagen, el bug del "1 plaza"
    desaparece. Best-effort: nunca bloquea el flujo principal.
    """
    import publicar_meta
    if not convocatorias:
        return False
    if not publicar_meta.configurado():
        print("📘 Facebook: API directa no configurada, se omite el boletín.")
        return False

    _MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                    "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    hoy = datetime.now()
    fecha = f"{hoy.day} de {_MESES_LARGO[hoy.month - 1]}"
    n = len(convocatorias)

    # Hasta 3 ejemplos, deduplicados por (puesto, lugar), de más a menos plazas.
    vistas, ejemplos = set(), []
    for conv in sorted(convocatorias, key=_plazas_num, reverse=True):
        partes = [p.strip() for p in (conv.get('resumen_ia') or '').split(' - ')]
        puesto = partes[1] if len(partes) > 1 and partes[1] else "Convocatoria"
        lugar = conv.get('comunidad_autonoma') or "España"
        clave = (puesto.lower(), lugar.lower())
        if clave in vistas:
            continue
        vistas.add(clave)
        num = _plazas_num(conv)
        es_nac = (lugar or "").strip().lower() in ("nacional/estatal", "nacional", "estatal")
        sitio = "Estatal" if es_nac else lugar
        if num > 1:
            num_fmt = f"{num:,}".replace(",", ".")
            ejemplos.append(f"🎯 {puesto} · {sitio} · {num_fmt} plazas")
        else:
            ejemplos.append(f"🎯 {puesto} · {sitio}")
        if len(ejemplos) == 3:
            break

    lineas = [
        f"📋 El BOE de hoy · {fecha}",
        f"{n} convocatoria{'s' if n != 1 else ''} nueva{'s' if n != 1 else ''} de empleo público.",
    ]
    if ejemplos:
        lineas += ["", "Algunas de hoy:", *ejemplos]
    lineas += [
        "",
        "👉 Todas, con enlace al BOE y filtro por tu comunidad:",
        "🔗 oponoticias.com/boe-hoy",
        "",
        "📩 Y recíbelas en tu email + Calendario del Opositor 2026 gratis.",
        "",
        "#oposiciones #BOE #empleopublico #opositar",
    ]
    mensaje = "\n".join(lineas)

    ok = publicar_meta.publicar_enlace_facebook(mensaje, link_url="https://oponoticias.com/boe-hoy")
    print(f"📘 Facebook: boletín diario {'publicado' if ok else 'falló'} ({n} convocatorias).")
    return ok


def publicar_carrusel_instagram(convocatorias, max_slides=3):
    """Genera un carrusel diario (2-3 imágenes) y lo envía a Make.com → Instagram.

    Best-effort: nunca bloquea ni revierte el flujo principal. Selecciona las
    convocatorias con más plazas del día, genera un PNG por cada una, lo sube a
    Supabase Storage y empuja las URLs + caption al webhook de Instagram.
    """
    import publicar_meta
    api_directa = publicar_meta.configurado() and bool(publicar_meta.FB_IG_ID)
    if not (api_directa or INSTAGRAM_WEBHOOK_URL):
        return False
    if not convocatorias:
        print("📷 Instagram: sin convocatorias nuevas, no se publica carrusel.")
        return False
    try:
        import generar_imagen_instagram as gii
    except Exception as e:
        print(f"⚠️  Instagram: no se pudo importar el generador ({e})")
        return False

    # Seleccionar las de más plazas (desc), conservando orden estable
    # Deduplicar por (puesto, plazas, lugar) para evitar imágenes idénticas
    vistas = set()
    seleccion = []
    for conv in sorted(convocatorias, key=_plazas_num, reverse=True):
        datos = _datos_imagen(conv)
        clave = (datos['puesto'], datos['plazas'], datos['lugar'])
        if clave not in vistas:
            vistas.add(clave)
            seleccion.append(conv)
            if len(seleccion) == max_slides:
                break

    fecha_slug = datetime.now().strftime("%Y-%m-%d")

    imagenes, lineas_caption = [], []
    for i, conv in enumerate(seleccion, 1):
        datos = _datos_imagen(conv)
        nombre = f"ig/{fecha_slug}-{i}.jpg"
        url = gii.generar_y_subir(datos, nombre)
        if not url:
            continue
        imagenes.append(url)
        lineas_caption.append(f"📍 {datos['puesto']} · {datos['plazas']} plazas · {datos['lugar']}")

    # Un carrusel necesita ≥2 imágenes. La API directa acepta 2-10 (sin slots
    # fijos); el fallback de Make necesita exactamente `max_slides`.
    if len(imagenes) < 2:
        print(f"⚠️  Instagram: solo {len(imagenes)} imagen(es), se omite el carrusel.")
        return False
    if not api_directa and len(imagenes) < max_slides:
        print(f"⚠️  Instagram: solo {len(imagenes)}/{max_slides} imágenes, "
              f"se omite el carrusel (Make espera {max_slides}).")
        return False

    caption = "\n".join([
        f"🎯 Convocatorias del BOE · {datetime.now().day} {_MESES_CORTO[datetime.now().month - 1]}",
        "",
        *lineas_caption,
        "",
        "👉 Toda la información y el enlace al BOE en oponoticias.com (link en bio)",
        "",
        "#oposiciones #empleopublico #BOE #oposicion2026 #funcionario",
    ])

    # ── Vía preferente: Graph API directa ──────────────────────────────────────
    if api_directa:
        return publicar_meta.publicar_carrusel_instagram(imagenes, caption)

    # ── Fallback: webhook de Make.com ──────────────────────────────────────────
    try:
        payload = json.dumps({"imagenes": imagenes, "caption": caption}).encode('utf-8')
        req = urllib.request.Request(
            INSTAGRAM_WEBHOOK_URL, data=payload,
            headers={'Content-Type': 'application/json'}, method='POST'
        )
        urllib.request.urlopen(req, timeout=15).read()
        print(f"📷 Carrusel Instagram enviado: {len(imagenes)} imágenes")
        return True
    except Exception as e:
        print(f"⚠️  Error Instagram webhook (no bloquea): {e}")
        return False


# generar_slug: idéntica a la de generar_ccaa.py/generar_categorias.py, ahora
# compartida en boe_utils.py (antes estaba triplicada).
from boe_utils import generar_slug


# Contexto útil por categoría (2-3 frases reales). Sirve para des-thin-ear las
# fichas: añade texto genuinamente informativo que varía según el área.
CONTEXTO_CATEGORIA = {
    "Administración": "Las oposiciones del área de Administración son la vía de acceso más común a la función pública en España. Engloban cuerpos como Auxiliar Administrativo, Administrativo o Gestión, presentes en ayuntamientos, diputaciones, comunidades autónomas y la Administración General del Estado. Suelen resolverse por concurso-oposición u oposición libre, con temarios que combinan derecho administrativo, organización del Estado y, a menudo, una prueba de ofimática.",
    "Educación": "Las oposiciones de Educación dan acceso a los cuerpos docentes (Maestros, Profesores de Secundaria, Formación Profesional, EOI, etc.). El proceso combina una fase de oposición —con pruebas de conocimientos y la defensa de una programación didáctica— y una fase de concurso en la que se valoran méritos como la experiencia previa y la formación.",
    "Sanidad": "Las oposiciones de Sanidad cubren plazas del sistema público de salud: personal facultativo, de enfermería, técnico y de gestión sanitaria. Las convocan habitualmente los servicios de salud autonómicos mediante concurso-oposición, y tienen gran demanda por la estabilidad y las condiciones del empleo público sanitario.",
    "Justicia": "Las oposiciones de Justicia permiten acceder a los cuerpos al servicio de la Administración de Justicia: Tramitación Procesal, Auxilio Judicial y Gestión Procesal, además de carreras como Letrados o Fiscales. Los temarios giran en torno al derecho procesal y la organización judicial, y el acceso suele ser de ámbito estatal.",
    "Seguridad": "Las oposiciones de Seguridad incluyen cuerpos como Policía Nacional, Guardia Civil y policías autonómicas y locales. Además de las pruebas teóricas, incorporan pruebas físicas, psicotécnicas y reconocimiento médico, por lo que requieren una preparación específica más allá del temario.",
    "Hacienda": "Las oposiciones del área de Hacienda dan acceso a cuerpos vinculados a la gestión tributaria, la inspección y la administración económica del Estado. Son procesos con temarios técnicos de derecho financiero, tributario y contabilidad pública.",
    "Correos": "Las convocatorias de Correos seleccionan personal para reparto, atención al cliente y clasificación. A diferencia de las oposiciones clásicas, el acceso suele basarse en una prueba tipo test y la valoración de méritos, sin un temario tan extenso, lo que las hace muy accesibles.",
    "Técnica": "Las oposiciones de perfil técnico cubren plazas especializadas (ingeniería, arquitectura, informática, medio ambiente, etc.) en distintas administraciones. Combinan un temario común sobre la Administración con un temario específico de la especialidad y, con frecuencia, supuestos prácticos.",
}

_CCAA_SLUGS = {
    "andalucia", "aragon", "asturias", "baleares", "canarias", "cantabria",
    "castilla-la-mancha", "castilla-leon", "cataluna", "ceuta", "comunidad-valenciana",
    "extremadura", "galicia", "la-rioja", "madrid", "melilla", "murcia", "nacional",
    "navarra", "pais-vasco",
}


def _norm_slug(texto):
    """Minúsculas, sin acentos, separadores a guion."""
    s = unicodedata.normalize('NFKD', (texto or '').lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return re.sub(r'-+', '-', s)


def _slug_categoria(categoria):
    """Mapa categoría visible -> archivo en categoria/. Fallback administracion."""
    s = _norm_slug(categoria)
    validas = {"administracion", "correos", "educacion", "hacienda",
               "justicia", "sanidad", "seguridad", "tecnica"}
    return s if s in validas else "administracion"


def _slug_ccaa(comunidad):
    """Mapa comunidad -> archivo en ccaa/. Fallback nacional."""
    s = _norm_slug(comunidad)
    alias = {
        "valencia": "comunidad-valenciana", "c-valenciana": "comunidad-valenciana",
        "comunidad-valenciana": "comunidad-valenciana", "valenciana": "comunidad-valenciana",
        "islas-baleares": "baleares", "illes-balears": "baleares",
        "islas-canarias": "canarias", "euskadi": "pais-vasco", "pais-vasco": "pais-vasco",
        "rioja": "la-rioja", "castilla-y-leon": "castilla-leon",
        "principado-de-asturias": "asturias", "region-de-murcia": "murcia",
        "comunidad-de-madrid": "madrid", "nacional-estatal": "nacional",
        "estatal": "nacional", "espana": "nacional", "": "nacional",
    }
    s = alias.get(s, s)
    return s if s in _CCAA_SLUGS else "nacional"


def _titulo_seo(puesto, ambito, plazas, anio):
    """Título SEO con la keyword por delante: 'Oposiciones {puesto} en {lugar} {año}'.
    Recibe strings ya escapados para HTML. Devuelve "" cuando el puesto es genérico
    (en ese caso se conserva el título oficial del BOE, que ya es único)."""
    puesto = (puesto or "").strip()
    if puesto.lower() in ("", "-", "—", "convocatoria", "convocatorias", "varias"):
        return ""
    es_nacional = _norm_slug(ambito) in ("nacional", "nacional-estatal", "estatal", "")
    lugar = "" if es_nacional else f" en {ambito}"
    cuerpo = puesto if puesto.lower().startswith("oposicion") else f"Oposiciones {puesto}"
    titulo = f"{cuerpo}{lugar} {anio}"
    pl = _norm_slug(plazas)
    if pl and pl not in ("varias", "", "-") and any(c.isdigit() for c in plazas):
        unidad = "plaza" if re.sub(r"[^\d]", "", plazas) == "1" else "plazas"
        titulo += f" · {plazas} {unidad}"
    return titulo


# Trámites administrativos que NO son convocatorias buscables (no merecen índice).
_RE_TRAMITE = re.compile(
    r'(?i)correcci[oó]n|\bcorrig|errata|modificaci[oó]n|lista de admit|'
    r'relaci[oó]n .*aprob|aprueba la relaci[oó]n|admitidas? y exclu|admitidos? y exclu|'
    r'sedes de examen|adjudicaci|nombramiento|jubilaci|baja ')


def _ficha_indexable(plazas, titulo_oficial):
    """Decide si la ficha entra en el índice de Google (anti index bloat).
    Poda agresiva (decidida 30 jun 2026): fuera las de 1 sola plaza (demanda
    ~nula; es la firma del fallback del extractor) y los trámites
    administrativos (correcciones, modificaciones, adjudicaciones,
    nombramientos...). Se siguen indexando los procesos con varias plazas.
    Las podadas quedan noindex,follow: vivas para usuarios y pasan autoridad
    a los hubs, pero fuera del índice y del sitemap."""
    if re.sub(r'[^\d]', '', plazas or '') == "1":
        return False
    if _RE_TRAMITE.search(titulo_oficial or ''):
        return False
    return True


# Iconos (18px) para la barra de compartir.
_SVG_WA = ('<svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true">'
           '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>')
_SVG_TG = ('<svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true">'
           '<path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg>')
_SVG_X = ('<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true">'
          '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>')

_ICO_STYLE = ("display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;"
              "border-radius:9px;background:var(--surface);border:1px solid var(--line);color:var(--ink);text-decoration:none;")


def _barra_compartir(url, titular):
    """Barra de compartir (WhatsApp/Telegram/X/copiar) para las fichas. En este
    nicho las convocatorias se reenvían a los grupos de estudio -> bucle viral.
    Autocontenida: enlaces externos + botón copiar con clipboard API y fallback
    execCommand (script inline, sin tocar assets/script.js)."""
    msg = html_lib.unescape(f"{titular} — convocatoria de oposiciones 👇")
    txt = urllib.parse.quote(msg)
    u = urllib.parse.quote(url)
    return f'''
      <div class="compartir-bar reveal" style="display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:20px 0 4px;">
        <span style="font-family:var(--sans);font-size:0.9rem;font-weight:600;color:var(--gray);margin-right:2px;">Compartir:</span>
        <a href="https://wa.me/?text={txt}%20{u}" target="_blank" rel="noopener" aria-label="Compartir por WhatsApp" title="WhatsApp" style="{_ICO_STYLE}">{_SVG_WA}</a>
        <a href="https://t.me/share/url?url={u}&amp;text={txt}" target="_blank" rel="noopener" aria-label="Compartir por Telegram" title="Telegram" style="{_ICO_STYLE}">{_SVG_TG}</a>
        <a href="https://twitter.com/intent/tweet?text={txt}&amp;url={u}" target="_blank" rel="noopener" aria-label="Compartir en X" title="X" style="{_ICO_STYLE}">{_SVG_X}</a>
        <button type="button" class="js-copiar" data-url="{url}" style="display:inline-flex;align-items:center;gap:6px;height:36px;padding:0 14px;border-radius:9px;background:var(--surface);border:1px solid var(--line);color:var(--ink);font-family:var(--sans);font-size:0.85rem;font-weight:600;cursor:pointer;">🔗 Copiar enlace</button>
      </div>
      <script>(function(){{var b=document.currentScript.previousElementSibling.querySelector('.js-copiar');if(!b)return;b.addEventListener('click',function(){{var u=b.getAttribute('data-url');function ok(){{var o=b.innerHTML;b.innerHTML='✓ Copiado';setTimeout(function(){{b.innerHTML=o;}},1800);}}function fb(){{try{{var t=document.createElement('textarea');t.value=u;t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.focus();t.select();document.execCommand('copy');document.body.removeChild(t);ok();}}catch(e){{}}}}if(navigator.clipboard&&navigator.clipboard.writeText){{navigator.clipboard.writeText(u).then(ok).catch(fb);}}else{{fb();}}}});}})();</script>'''


def _bloque_enriquecido(conv, categoria, puesto_t, organismo_t, ambito_t,
                        plazas_t, fecha_str):
    """Devuelve (html_bloque, faq_schema_json). Contenido único y útil por ficha,
    sin coste de API: varía con categoría, puesto, organismo, ámbito, plazas y fecha.
    Las entradas *_t llegan ya escapadas para HTML; para el schema se des-escapan."""
    ref_boe = conv.get('ref_boe', 'BOE')
    es_nacional = _norm_slug(ambito_t) in ("nacional", "nacional-estatal", "estatal", "")
    ambito_frase = "de ámbito estatal" if es_nacional else f"en {ambito_t}"
    contexto = CONTEXTO_CATEGORIA.get(categoria, CONTEXTO_CATEGORIA["Administración"])
    cat_slug = _slug_categoria(categoria)
    ccaa_slug = _slug_ccaa(ambito_t)

    if _norm_slug(plazas_t) in ("varias", "", "-"):
        plazas_faq = "La convocatoria oferta varias plazas; el número exacto y su distribución figuran en las bases publicadas en el BOE."
    else:
        plazas_faq = f"La convocatoria oferta {plazas_t} plazas. Consulta el detalle y su distribución en el texto oficial del BOE."

    intro = (f"El organismo <strong>{organismo_t}</strong> ha publicado en el "
             f"Boletín Oficial del Estado, con fecha {fecha_str}, una convocatoria "
             f"relacionada con plazas de <strong>{puesto_t}</strong> {ambito_frase}. "
             f"En esta página resumimos los datos principales y te explicamos cómo "
             f"seguir el proceso paso a paso.")

    # FAQ visible
    faqs = [
        ("¿Cuántas plazas se convocan?", plazas_faq),
        ("¿Quién convoca esta oposición?",
         f"El proceso selectivo lo convoca {organismo_t}, {ambito_frase}, dentro del área de {categoria}."),
        ("¿Hasta cuándo puedo presentar la solicitud?",
         f"El plazo habitual de presentación es de 20 días hábiles desde el día siguiente a la publicación en el BOE ({fecha_str}). El plazo definitivo es siempre el que indiquen las bases oficiales de la convocatoria."),
        ("¿Dónde consulto las bases oficiales?",
         f"En el texto publicado en el BOE con referencia {ref_boe}, accesible desde el enlace «Leer el texto oficial en el BOE» de esta página."),
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
            {"@type": "Question", "name": html_lib.unescape(q),
             "acceptedAnswer": {"@type": "Answer", "text": html_lib.unescape(a)}}
            for q, a in faqs
        ],
    }
    faq_schema_json = json.dumps(faq_schema, ensure_ascii=False, indent=2)

    ambito_link = "" if ccaa_slug == "nacional" and es_nacional else (
        f'<a href="../ccaa/{ccaa_slug}.html" style="background:var(--surface); border:1px solid var(--line); border-radius:999px; padding:8px 16px; text-decoration:none;">Oposiciones en {ambito_t} →</a>')

    bloque = f"""
            <section class="ficha-extra" style="margin-top:32px;">
              <p style="line-height:1.65;">{intro}</p>

              <h2 style="font-size:1.2rem; margin:28px 0 10px;">Sobre las oposiciones de {categoria}</h2>
              <p style="line-height:1.65; color:var(--ink);">{contexto}</p>

              <h2 style="font-size:1.2rem; margin:28px 0 10px;">Cómo presentarte a esta convocatoria</h2>
              <ol style="line-height:1.7; padding-left:1.2em;">
                <li>Lee el texto oficial en el BOE (enlace arriba) para conocer los requisitos, la titulación exigida y el baremo de méritos.</li>
                <li>Comprueba el plazo de solicitudes. Suele ser de 20 días hábiles desde el día siguiente a la publicación en el BOE; en este caso, a partir del {fecha_str}. Confírmalo siempre en las bases.</li>
                <li>Reúne la documentación (titulación, DNI y justificante de la tasa) y presenta la instancia por la sede electrónica del organismo o el registro que indiquen las bases.</li>
                <li>Prepara el temario y acredita tus méritos. Si tienes experiencia o formación previa, asegúrate de justificarlos para sumar en la fase de concurso.</li>
              </ol>

              <h2 style="font-size:1.2rem; margin:28px 0 10px;">Preguntas frecuentes</h2>
              <div class="faq-list">{faq_items}</div>

              <div class="ficha-links" style="margin-top:28px; display:flex; flex-wrap:wrap; gap:10px; font-size:0.92rem; font-weight:600;">
                <a href="../categoria/{cat_slug}.html" style="background:var(--surface); border:1px solid var(--line); border-radius:999px; padding:8px 16px; text-decoration:none;">Más convocatorias de {categoria} →</a>
                {ambito_link}
                <a href="../index.html#ultimas" style="background:var(--surface); border:1px solid var(--line); border-radius:999px; padding:8px 16px; text-decoration:none;">Ver todas las convocatorias →</a>
              </div>
            </section>
"""
    return bloque, faq_schema_json


def generar_html_convocatoria(conv, categoria, forzar=False, relacionadas_html="", slug_forzado=""):
    """Genera un archivo HTML por convocatoria"""

    slug = slug_forzado or generar_slug(conv['titulo'], conv.get('ref_boe', ''))
    html_path = WEB_CONVOCATORIA_DIR / slug

    # Si ya existe, no regenerar (salvo regeneración forzada del rediseño)
    if html_path.exists() and not forzar:
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
    desc_json = json.dumps(desc)[1:-1]          # escapa \n, " y \ sin las comillas externas
    titulo_json = json.dumps(conv['titulo'])[1:-1]
    meta_desc = f"Resumen: {desc[:120]}. Enlace al BOE oficial."
    canonical = f"https://oponoticias.com/convocatoria/{slug.replace('.html', '')}"

    # Datos para el titular corto y las tarjetas (ficha escaneable)
    _p = [x.strip() for x in (conv.get('resumen_ia') or '').split(' - ')]
    plazas_t = re.sub(r'(?i)\s*plazas?', '', _p[0]).strip().capitalize() if _p and _p[0] else "—"
    puesto_t = _p[1].capitalize() if len(_p) > 1 and _p[1] else "Convocatoria"
    organismo_t = html_lib.escape(_extraer_organismo(conv['titulo']) or "Administración Pública")
    ambito_t = html_lib.escape(conv.get('comunidad_autonoma') or "Nacional")
    plazas_t = html_lib.escape(plazas_t)
    puesto_t = html_lib.escape(puesto_t)
    titular_corto = f"{puesto_t} — {organismo_t}"

    # Bloque de contenido enriquecido (texto útil y único por ficha) + schema FAQ
    bloque_extra, faq_schema_json = _bloque_enriquecido(
        conv, categoria, puesto_t, organismo_t, ambito_t, plazas_t, fecha_str)

    # Título SEO (keyword al frente) + enlaces internos a los hubs
    _seo = _titulo_seo(puesto_t, ambito_t, plazas_t, fecha_schema[:4])
    title_tag = f"{_seo} | OpoNoticias" if _seo else f"{conv['titulo']} — Convocatoria | OpoNoticias"
    og_title = _seo or conv['titulo'][:100]
    cat_slug = _slug_categoria(categoria)
    ccaa_slug = _slug_ccaa(ambito_t)
    robots = "index, follow" if _ficha_indexable(plazas_t, conv['titulo']) else "noindex, follow"
    barra_compartir = _barra_compartir(canonical, titular_corto)

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_tag}</title>
  <meta name="description" content="{meta_desc}">
  <link rel="canonical" href="{canonical}">
  <meta name="robots" content="{robots}">
  <meta name="theme-color" content="#5A5047">
  <script>document.documentElement.className += ' js';</script>

  <meta property="og:type" content="article">
  <meta property="og:site_name" content="OpoNoticias">
  <meta property="og:title" content="{og_title}">
  <meta property="og:description" content="{desc[:160]}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="https://oponoticias.com/social/telegram-banner.png">
  <meta property="og:locale" content="es_ES">
  <meta name="twitter:card" content="summary_large_image">

  <link rel="icon" type="image/svg+xml" href="../assets/icon-512.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../assets/style.css?v=6">

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "{titulo_json}",
    "description": "{desc_json}",
    "datePosted": "{fecha_schema}",
    "validThrough": "{valid_through}",
    "employmentType": "FULL_TIME",
    "hiringOrganization": {{"@type": "Organization", "name": "Administración Pública"}},
    "jobLocation": {{"@type": "Place", "address": {{"@type": "PostalAddress", "addressCountry": "ES"}}}},
    "industry": "Administración pública - {categoria}",
    "url": "{canonical}"
  }}
  </script>
  <script type="application/ld+json">
  {faq_schema_json}
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
          <a href="../boe-hoy.html">El BOE de hoy</a>
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
            <a href="https://www.instagram.com/oponoticiason/" rel="noopener" target="_blank" aria-label="Instagram" title="Instagram"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg></a>
            <a href="https://whatsapp.com/channel/0029Vb8BReo89ind8LpWxp26" rel="noopener" target="_blank" aria-label="WhatsApp" title="WhatsApp"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg></a>
            <a href="mailto:info@oponoticias.com" aria-label="Email" title="info@oponoticias.com"><svg viewBox="0 0 24 24" width="20" height="20" fill="#2B2622" aria-hidden="true"><path d="M2 4h20c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H2c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm10 7L2.5 6h19L12 11zm0 2.2L2 7.3V18h20V7.3l-10 5.9z"/></svg></a>
          </div>
        </div>
      </nav>
    </div>
  </header>

  <main>
    <div class="container">
      <nav class="breadcrumb" aria-label="Migas de pan">
        <a href="../index.html">Inicio</a>
        <span class="sep">/</span>
        <a href="../categoria/{cat_slug}.html">{categoria}</a>
        <span class="sep">/</span>
        <span aria-current="page">{titular_corto}</span>
      </nav>

      <div class="article-layout">
        <article>
          <header class="article-header reveal">
            <span class="article-tag">{categoria}</span>
            <h1>{titular_corto}</h1>
            <p style="color:var(--gray); font-size:0.95rem; margin:8px 0 0; line-height:1.45;">{conv['titulo']}</p>
            <div class="article-meta">
              <span>Publicado: <b>{fecha_str}</b></span>
              <span>Fuente: <b>BOE</b></span>
              <span>Referencia: <b>{conv.get('ref_boe', 'BOE')}</b></span>
            </div>
          </header>
{barra_compartir}
          <div class="prose reveal">
            <div style="display:grid; gap:10px; margin:6px 0 26px;">
              <div style="background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px 16px;">
                <div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--gray); margin-bottom:4px;">Puesto</div>
                <div style="font-size:1.05rem; font-weight:600; color:var(--ink);">{puesto_t}</div>
              </div>
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                <div style="background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px 16px;">
                  <div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--gray); margin-bottom:4px;">Plazas</div>
                  <div style="font-size:1.05rem; font-weight:600; color:var(--ink);">{plazas_t}</div>
                </div>
                <div style="background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px 16px;">
                  <div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--gray); margin-bottom:4px;">Ámbito</div>
                  <div style="font-size:1.05rem; font-weight:600; color:var(--ink);"><a href="../ccaa/{ccaa_slug}.html" style="color:inherit; text-decoration:none; border-bottom:1px solid var(--line);">{ambito_t}</a></div>
                </div>
              </div>
              <div style="background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px 16px;">
                <div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; color:var(--gray); margin-bottom:4px;">Organismo</div>
                <div style="font-size:1.05rem; font-weight:600; color:var(--ink);">{organismo_t}</div>
              </div>
            </div>

            <a href="{conv['enlace']}" class="boe-link" rel="noopener" target="_blank">
              <span class="l"><b>Leer el texto oficial en el BOE</b><span>boe.es · {conv.get('ref_boe', 'BOE')}</span></span>
              <span class="arrow">→</span>
            </a>

            <p style="margin-top:24px; color:var(--gray); font-size:0.9rem;">Este resumen tiene carácter informativo. La información válida y vinculante es siempre la publicada en el Boletín Oficial del Estado.</p>
{bloque_extra}
{relacionadas_html}
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
          <img src="../assets/logo-white.svg" alt="OpoNoticias">
          <p>Las convocatorias de oposiciones del BOE, resumidas en lenguaje claro y organizadas por categoría.</p>
          <div class="footer-social">
            <a href="https://t.me/OPONOTICIAS" rel="noopener" target="_blank" aria-label="Telegram" title="Telegram"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z"/></svg></a>
            <a href="https://www.facebook.com/profile.php?id=61590965302457" rel="noopener" target="_blank" aria-label="Facebook" title="Facebook"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.1 24 18.1 24 12.07z"/></svg></a>
            <a href="https://x.com/OpoNoticiasON" rel="noopener" target="_blank" aria-label="X" title="X"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
            <a href="https://www.instagram.com/oponoticiason/" rel="noopener" target="_blank" aria-label="Instagram" title="Instagram"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg></a>
            <a href="https://whatsapp.com/channel/0029Vb8BReo89ind8LpWxp26" rel="noopener" target="_blank" aria-label="WhatsApp" title="WhatsApp"><svg viewBox="0 0 24 24" width="24" height="24" fill="#ffffff" aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg></a>
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
        <span>© 2026 OpoNoticias · oponoticias.com</span>
        <span>Fuente oficial: api.boe.es · Actualización diaria cada mañana</span>
      </div>
    </div>
  </footer>

  <script src="../assets/script.js?v=7" defer></script>
</body>
</html>"""

    try:
        WEB_CONVOCATORIA_DIR.mkdir(parents=True, exist_ok=True)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(limpiar_hrefs(html_content))
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
            ("https://oponoticias.com/boe-hoy", hoy, "daily", "0.9"),
            ("https://oponoticias.com/convocatorias", hoy, "daily", "0.9"),
            ("https://oponoticias.com/blog", hoy, "weekly", "0.8"),
            ("https://oponoticias.com/recursos", hoy, "weekly", "0.7"),
            ("https://oponoticias.com/calculadora-nota", hoy, "monthly", "0.7"),
            ("https://oponoticias.com/sobre-nosotros", hoy, "monthly", "0.5"),
            ("https://oponoticias.com/contacto", hoy, "monthly", "0.5"),
            ("https://oponoticias.com/categoria/educacion", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/sanidad", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/justicia", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/seguridad", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/administracion", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/hacienda", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/correos", hoy, "daily", "0.8"),
            ("https://oponoticias.com/categoria/tecnica", hoy, "daily", "0.8"),
        ]

        # Fichas de convocatoria: solo las indexables (index bloat, 30 jun 2026).
        # La etiqueta robots de cada ficha es la fuente de verdad: las marcadas
        # noindex (1 plaza / trámites, ver _ficha_indexable) se excluyen del
        # sitemap para concentrar el rastreo en las que valen. Las CCAA las añade
        # generar_ccaa.actualizar_sitemap tras este paso.
        if WEB_CONVOCATORIA_DIR.exists():
            for f in sorted(WEB_CONVOCATORIA_DIR.glob("*.html")):
                try:
                    cabecera = f.read_text(encoding="utf-8")[:2500]
                except Exception:
                    continue
                if 'content="noindex' in cabecera:
                    continue
                lastmod = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
                urls.append((f"https://oponoticias.com/convocatoria/{f.stem}",
                             lastmod, "monthly", "0.6"))

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
        env_git = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

        # rebase antes de empujar: si `main` avanzó desde el checkout (otro
        # workflow o un push manual mientras corría este), un push directo sin
        # esto falla con "non-fast-forward" y el HTML generado hoy se pierde en
        # silencio (el runner se destruye al terminar el job). Con 1 reintento
        # tras el rebase basta para el volumen de commits reales de este repo.
        for intento in range(2):
            try:
                subprocess.run(
                    ["git", "-C", WEB_REPO_PATH, "push", url_repo, "HEAD:main"],
                    check=True, capture_output=True, env=env_git,
                )
                break
            except subprocess.CalledProcessError:
                if intento == 1:
                    raise
                print("  ⚠️  Push rechazado (main avanzó) — rebase y reintento…")
                subprocess.run(
                    ["git", "-C", WEB_REPO_PATH, "pull", "--rebase", url_repo, "main"],
                    check=True, capture_output=True, env=env_git,
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

    if not convocatorias:
        print("\n❌ No se encontraron convocatorias")
        raise SystemExit(0)

    nuevas = 0
    slugs_generados = []

    # ── 1) Procesar: resumen IA + comunidad + guardar en Supabase + HTML ──────
    for conv in convocatorias:
        cuerpo, categoria = extraer_cuerpo(conv['titulo'])

        print(f"\n🤖 Analizando: {conv['titulo'][:60]}...")
        conv['categoria'] = categoria               # se usa luego en Facebook
        conv['resumen_ia'] = generar_resumen_con_claude(conv['titulo'], conv['resumen'])
        conv['comunidad_autonoma'] = clasificar_comunidad(conv['titulo'], conv['resumen'])

        es_nueva = guardar_en_supabase(conv)        # inserta con telegram_enviado=false (default)
        slug = generar_html_convocatoria(conv, categoria)
        if es_nueva:
            nuevas += 1
            if slug:
                slugs_generados.append(slug)

    # ── 2) Redes sociales (Telegram, Facebook, Instagram, X, vídeo) ───────────
    # SKIP_SOCIAL=1 → guarda en Supabase y genera HTML/web pero NO publica en
    # redes. Sirve para reprocesar un día cuyas convocatorias YA se anunciaron
    # (p. ej. tras un fallo de Supabase que impidió guardarlas) sin duplicar los
    # posts. Además marca las del día como ya enviadas, para que una ejecución
    # normal posterior tampoco las reenvíe.
    enviadas_tg = 0
    if os.environ.get('SKIP_SOCIAL'):
        print("\n⏭️  SKIP_SOCIAL activo: NO se publica en redes (solo Supabase + web).")
        for conv in convocatorias:
            marcar_telegram_enviado(conv['enlace'])
    else:
        # ── Telegram: enviar SOLO las que aún no se hayan enviado (retry-safe) ──
        # Desacoplado del guardado: si un envío falla, el flag queda en false y se
        # reintenta en la siguiente ejecución sin duplicar las ya publicadas.
        print("\n📤 Telegram + Facebook — enviando convocatorias pendientes…")
        # X (Buffer): ya NO se postean tweets individuales por convocatoria
        # (28 jun 2026). X recibe SOLO el tweet-resumen diario (más abajo), igual
        # que el resumen de WhatsApp → menos volumen, sin saturar Buffer ni que X
        # corte el token por spam. Telegram, web y Facebook siguen recibiendo todas.
        enviadas_hoy = []
        for conv in convocatorias:
            if telegram_ya_enviado(conv['enlace']):
                print(f"⏭️  Ya estaba en Telegram: {conv['titulo'][:50]}...")
                continue
            if enviar_a_telegram(conv):
                marcar_telegram_enviado(conv['enlace'])
                enviadas_hoy.append(conv)
                enviadas_tg += 1
                time.sleep(2)

        # ── Resúmenes diarios (una vez al día) ────────────────────────────────────
        # Facebook agrupado, carrusel IG, resumen admin/WhatsApp, tweet-resumen y
        # vídeo son publicaciones ÚNICAS del día. Solo se generan cuando hay
        # convocatorias realmente nuevas (nuevas > 0); así, si el workflow se
        # vuelve a ejecutar el mismo día (re-trigger manual), NO se duplican
        # posts ni vídeos. El envío granular a Telegram (arriba) sí es retry-safe
        # por convocatoria (flag telegram_enviado), independiente de este bloque.
        if nuevas > 0:
            # ── 2a bis) Facebook: UN boletín diario con enlace a la web (28 jun 2026) ──
            # Sustituye los 6 posts agrupados de imagen por un único post de enlace a
            # oponoticias.com/boe-hoy → lleva tráfico a la web (el fuerte de FB) y
            # evita el bug del "1 plaza". `publicar_facebook_agrupado` se conserva
            # (sin invocar) por si hay que volver atrás.
            publicar_facebook_boletin(enviadas_hoy)

            # ── 2b) Instagram: el carrusel diario se ELIMINA (28 jun 2026) ────────────
            # Duplicaba el Reel diario (mismo contenido, top por plazas) y arrastraba
            # el problema del "1 plaza". La pieza diaria de IG es ahora solo el Reel
            # (ver paso 2d). La función publicar_carrusel_instagram() se conserva por si
            # se reconvierte en el futuro, pero ya no se invoca.

            # ── 2c) Resumen privado al admin (para copiar al Canal de WhatsApp) ───────
            enviar_resumen_privado(enviadas_hoy)

            # ── 2c bis) Tweet-resumen del día en X (mismo top que el de WhatsApp) ──────
            publicar_tweet_resumen(enviadas_hoy)

            # ── 2d) Vídeo diario para TikTok / IG Reels / FB Reels (best-effort) ──────
            try:
                import generar_video_diario as gvd
                gvd.enviar_video_redes(enviadas_hoy)
            except Exception as e:
                print(f"⚠️  Vídeo diario: {e}")
        else:
            print("ℹ️  Sin convocatorias nuevas: se omiten resúmenes diarios "
                  "(Facebook/Instagram/X/vídeo) para no duplicar.")

    # ── 3) Sitemap + push a GitHub si hay HTML nuevos ─────────────────────────
    if slugs_generados:
        regenerar_sitemap(slugs_generados)

        archivos_commit = [
            f"convocatoria/{slug}" for slug in slugs_generados
        ] + ["sitemap.xml"]

        fecha_hoy = datetime.now().strftime("%d/%m/%Y")
        commit_a_github(f"Auto: {nuevas} nuevas convocatorias ({fecha_hoy})", archivos_commit)

    print(f"\n✅ Procesadas {len(convocatorias)} convocatorias. "
          f"Nuevas: {nuevas} · Enviadas a Telegram: {enviadas_tg}")
