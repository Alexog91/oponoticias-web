#!/usr/bin/env python3
"""
generar_blog_temas.py — Artículos temáticos (metodología y preparación) del blog.

A diferencia de generar_blog.py (que escribe guías largas por categoría a partir
de convocatorias reales), este módulo genera artículos BREVES y evergreen sobre
cómo opositar: técnicas de estudio, gestión de la ansiedad, planificación, etc.

Son los "satélites" del modelo pilar-satélite de SEO: enlazan hacia las guías de
categoría (los pilares) y entre las propias secciones de la web.

Formato de redacción:
  - 350–450 palabras.
  - Párrafos homogéneos de 5–7 líneas; una expresión de alto impacto en negrita
    por párrafo.
  - 2 enlaces internos al pilar + 1 a una sección real + 1 externo de autoridad.
  - Cierre con una sola pregunta frecuente (rich snippet).
  - Portada propia 1200×630 (og:image) generada con la marca.

Cada artículo se guarda como BORRADOR (publicado=False) con fecha programada.
Los publica el job de lunes/jueves (publicar_programados.py), igual que los demás.

Categoría interna: "preparacion" (pista de contenido propia, no de convocatorias).
Slug estable por tema (sin sufijo de mes) → un único artículo evergreen por tema.

Variables de entorno: SUPABASE_URL, SUPABASE_API_KEY, ANTHROPIC_API_KEY.
Para la portada: librsvg2-bin o Chrome + Pillow (best-effort; si falta, sin imagen).
"""

import os
import re
import sys
import json
import time
import random
import urllib.parse
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generar_blog as gb

try:
    import generar_imagen_instagram as gii
except Exception as _e:           # Pillow/render no disponible: seguimos sin portada
    gii = None
    print(f"ℹ️  Imagen no disponible ({_e}); los artículos saldrán sin portada.")

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
BASE_URL         = "https://oponoticias.com"
BLOG_DIR         = "blog"

CATEGORIA_TEMAS = "preparacion"   # mapea a "Preparación" en gb.NOMBRE_CATEGORIA
MAX_POR_EJECUCION = 3

# ── Banco de temas (metodología y preparación) ──────────────────────────────────
# slug: estable, sin mes → un único artículo evergreen por tema.
# pilar: categoría a la que enlaza como guía de referencia (/categoria/<pilar>.html).
TEMAS = [
    {"slug": "como-elegir-la-oposicion-adecuada-a-tu-perfil",
     "tema": "Cómo elegir la oposición adecuada según tu perfil, formación y objetivos",
     "keyword": "elegir oposición", "pilar": "administracion"},
    {"slug": "academia-presencial-online-o-autopreparacion",
     "tema": "Academia presencial, academia online o autopreparación: ventajas e inconvenientes de cada opción",
     "keyword": "academia de oposiciones", "pilar": "administracion"},
    {"slug": "plan-de-estudio-realista-para-oposiciones",
     "tema": "Cómo crear un plan de estudio realista para una oposición y cumplirlo",
     "keyword": "plan de estudio oposiciones", "pilar": "administracion"},
    {"slug": "tecnicas-de-memorizacion-para-temarios-extensos",
     "tema": "Técnicas de memorización para temarios extensos: palacios de la memoria y reglas mnemotécnicas",
     "keyword": "técnicas de memorización", "pilar": "administracion"},
    {"slug": "repaso-espaciado-aplicado-a-oposiciones",
     "tema": "El repaso espaciado (repetición espaciada) aplicado a la preparación de oposiciones",
     "keyword": "repaso espaciado", "pilar": "administracion"},
    {"slug": "estrategias-para-aprobar-examenes-tipo-test",
     "tema": "Cómo afrontar los exámenes tipo test: estrategias para acertar más y penalizar menos",
     "keyword": "examen tipo test oposiciones", "pilar": "administracion"},
    {"slug": "gestion-del-tiempo-en-el-examen-de-oposicion",
     "tema": "Gestión del tiempo durante el examen: cómo no quedarte sin contestar",
     "keyword": "gestión del tiempo examen", "pilar": "administracion"},
    {"slug": "como-hacer-esquemas-y-resumenes-de-un-temario",
     "tema": "Cómo elaborar esquemas y resúmenes eficaces de un temario de oposición",
     "keyword": "esquemas y resúmenes temario", "pilar": "administracion"},
    {"slug": "errores-comunes-de-los-opositores-primerizos",
     "tema": "Los errores más comunes de los opositores primerizos y cómo evitarlos",
     "keyword": "errores opositores primerizos", "pilar": "administracion"},
    {"slug": "como-mantener-la-motivacion-opositando",
     "tema": "Cómo mantener la motivación durante años de preparación de una oposición",
     "keyword": "motivación opositor", "pilar": "administracion"},
    {"slug": "gestion-de-la-ansiedad-y-los-nervios-en-el-examen",
     "tema": "Gestión de la ansiedad y los nervios antes y durante el examen de oposición",
     "keyword": "ansiedad examen oposición", "pilar": "administracion"},
    {"slug": "cuantas-horas-estudiar-para-una-oposicion",
     "tema": "Rutinas de estudio: cuántas horas estudiar al día para una oposición y cómo distribuirlas",
     "keyword": "cuántas horas estudiar oposición", "pilar": "administracion"},
    {"slug": "como-afrontar-el-supuesto-practico",
     "tema": "Cómo afrontar el supuesto práctico y los casos prácticos en una oposición",
     "keyword": "supuesto práctico oposición", "pilar": "justicia"},
    {"slug": "preparar-la-prueba-fisica-de-oposiciones",
     "tema": "Cómo preparar la prueba física de oposiciones (Guardia Civil, Policía, Bomberos): planes de entrenamiento",
     "keyword": "prueba física oposiciones", "pilar": "seguridad"},
    {"slug": "como-opositar-mientras-trabajas",
     "tema": "Cómo estudiar una oposición mientras trabajas o tienes responsabilidades familiares",
     "keyword": "opositar trabajando", "pilar": "administracion"},
    {"slug": "apps-y-herramientas-utiles-para-opositores",
     "tema": "Herramientas y apps útiles para opositores: Anki, simuladores de test y gestores de estudio",
     "keyword": "apps para opositores", "pilar": "tecnica"},
    {"slug": "como-afrontar-un-suspenso-en-una-oposicion",
     "tema": "Cómo afrontar un suspenso en una oposición y volver a empezar sin rendirte",
     "keyword": "suspenso oposición", "pilar": "administracion"},
    {"slug": "descanso-sueno-y-ejercicio-en-el-rendimiento",
     "tema": "La importancia del descanso, el sueño y el ejercicio en el rendimiento del opositor",
     "keyword": "descanso y rendimiento opositor", "pilar": "administracion"},
    {"slug": "preparar-la-entrevista-personal-y-el-psicotecnico",
     "tema": "Cómo preparar la entrevista personal y las pruebas psicotécnicas de una oposición",
     "keyword": "entrevista personal y psicotécnico", "pilar": "seguridad"},
    {"slug": "como-seguir-las-convocatorias-que-te-interesan",
     "tema": "Calendario de convocatorias: cómo seguir las oposiciones que te interesan sin perderte ninguna",
     "keyword": "calendario de convocatorias", "pilar": "administracion"},
    {"slug": "como-entender-la-nota-de-corte-y-la-baremacion",
     "tema": "Cómo calcular tu nota de corte y entender el sistema de baremación de méritos",
     "keyword": "nota de corte y baremación", "pilar": "administracion"},
    {"slug": "tecnicas-para-mejorar-la-concentracion-estudiando",
     "tema": "Técnicas para mejorar la concentración y evitar distracciones durante el estudio",
     "keyword": "mejorar la concentración estudiando", "pilar": "administracion"},
    {"slug": "como-organizar-tu-material-de-estudio",
     "tema": "Cómo organizar tu material de estudio físico y digital para una oposición",
     "keyword": "organizar material de estudio", "pilar": "tecnica"},
    {"slug": "merece-la-pena-pagar-un-preparador",
     "tema": "El papel del preparador o tutor de oposiciones: ¿merece la pena pagarlo?",
     "keyword": "preparador de oposiciones", "pilar": "administracion"},
    {"slug": "que-aprender-de-quienes-aprobaron-la-oposicion",
     "tema": "Rutinas y hábitos de quienes aprobaron su oposición: qué podemos aprender de ellos",
     "keyword": "cómo aprobar una oposición", "pilar": "administracion"},
    # ── Temas conceptuales de alta búsqueda (inspirados en la lista) ─────────────
    {"slug": "que-grupo-de-clasificacion-me-conviene-a1-a2-c1-c2",
     "tema": "Grupos de clasificación A1, A2, B, C1 y C2: requisitos, funciones y retribuciones",
     "keyword": "grupos de clasificación funcionario", "pilar": "administracion"},
    {"slug": "oposicion-concurso-oposicion-y-concurso-diferencias",
     "tema": "Oposición, concurso-oposición y concurso: diferencias entre los sistemas selectivos",
     "keyword": "oposición concurso-oposición concurso", "pilar": "administracion"},
    {"slug": "turno-libre-y-promocion-interna-como-funcionan",
     "tema": "Turno libre y promoción interna: cómo funciona cada cupo de acceso al empleo público",
     "keyword": "turno libre y promoción interna", "pilar": "administracion"},
    {"slug": "como-leer-las-bases-de-una-convocatoria",
     "tema": "Cómo leer las bases de una convocatoria de oposición sin pasar por alto nada importante",
     "keyword": "bases de la convocatoria", "pilar": "administracion"},
    {"slug": "oposiciones-sin-titulacion-universitaria-c1-c2",
     "tema": "Oposiciones sin titulación universitaria: qué puedes opositar en los grupos C1 y C2",
     "keyword": "oposiciones sin carrera", "pilar": "administracion"},
    {"slug": "el-cupo-de-reserva-de-discapacidad-en-el-empleo-publico",
     "tema": "El cupo de reserva para personas con discapacidad en el acceso al empleo público",
     "keyword": "cupo de discapacidad oposiciones", "pilar": "administracion"},
]

SECCIONES_WEB = [
    ("últimas convocatorias", "/index.html#ultimas"),
    ("todas las categorías", "/index.html#categorias"),
    ("el blog del opositor", "/blog.html"),
]


# ── Selección y deduplicación ────────────────────────────────────────────────

def _ya_existe(slug):
    """True si ya hay un artículo (borrador o publicado) con ese slug."""
    params = urllib.parse.urlencode({"select": "id", "slug": f"eq.{slug}", "limit": 1})
    return bool(gb.supabase_get("articulos_blog", params))


def temas_pendientes():
    """Devuelve los temas que aún no tienen artículo, en orden de la lista."""
    return [t for t in TEMAS if not _ya_existe(t["slug"])]


def _proxima_fecha(usadas):
    """Siguiente fecha disponible, 1 artículo por día, saltando domingos."""
    d = datetime.now(timezone.utc).date() + timedelta(days=1)
    while True:
        if d.isoweekday() != 7 and usadas.count(d) < 1:
            return d
        d += timedelta(days=1)


# ── Generación con Claude ────────────────────────────────────────────────────

def _parsear_json(respuesta):
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


def generar_articulo_tema(tema):
    año = datetime.now().year
    nombre_pilar = gb.NOMBRE_CATEGORIA.get(tema["pilar"], "Administración")
    url_pilar = f"/categoria/{tema['pilar']}.html"
    seccion_label, seccion_url = random.choice(SECCIONES_WEB)
    fuente = random.choice(gb.FUENTES_REFERENCIA)

    prompt = f"""Eres un redactor experto en oposiciones y empleo público en España, con conocimiento técnico real del acceso a la función pública (cuerpos y escalas, grupos de clasificación, sistemas selectivos y bases de convocatoria). Escribes con autoridad profesional pero de forma cercana, como alguien que conoce de primera mano lo que vive un opositor. Escribe para el blog de OpoNoticias un artículo BREVE y muy bien posicionado en buscadores sobre:

"{tema['tema']}"

PALABRA CLAVE principal: "{tema['keyword']}". Debe aparecer en el título, en la primera frase del artículo y en al menos un subtítulo H2.

CÓMO ESCRIBIR (lo más importante):
- Extensión: ENTRE 350 Y 450 palabras de contenido real. Es un LÍMITE ESTRICTO: no superes las 450 palabras bajo ningún concepto. Cuenta las palabras antes de devolver el JSON y recorta si te pasas.
- El cuerpo debe tener ENTRE 4 Y 6 PÁRRAFOS en total (sin contar la sección de preguntas frecuentes). Cada párrafo debe ser DENSO, de 5 a 7 líneas: no escribas párrafos sueltos de 2-3 líneas ni trocees una idea en varios párrafos cortos.
- En CADA UNO de esos párrafos marca en **negrita** una (y solo una) frase o expresión de alto impacto: la idea más accionable o memorable del párrafo. Si escribes 5 párrafos, habrá exactamente 5 fragmentos en **negrita**. No marques palabras sueltas sin fuerza ni dejes ningún párrafo sin su negrita.
- Registro profesional y técnico del ámbito de las oposiciones, pero divulgativo y humano: escribes para futuros funcionarios. Usa con precisión la terminología (cuerpos y escalas, grupos A1, A2, B, C1 y C2; oposición, concurso-oposición y concurso; turno libre y promoción interna; bases, temario, fase de oposición y fase de concurso). No uses un término por otro.
- Empieza con un gancho concreto: un dato, una cifra, una situación real del opositor. NUNCA empieces con "En el mundo actual", "Es importante destacar", "Las oposiciones son una de las mejores opciones".
- Varía la longitud de las frases. PROHIBIDO usar muletillas de IA: "En resumen", "En definitiva", "Cabe destacar", "Es fundamental", "el mundo de las oposiciones", "embarcarte en", "abre las puertas a", "no es tarea fácil", ni listas de tres adjetivos.
- No inventes cifras, fechas, plazas ni denominaciones oficiales que no conozcas con certeza; si no tienes el dato exacto, exprésalo en términos generales.

ENLACES (obligatorios, integrados de forma natural dentro de frases, en formato markdown):
- DOS enlaces a la guía de referencia del área, con textos ancla distintos: [oposiciones de {nombre_pilar}]({url_pilar}) y una segunda mención con otro texto ancla hacia {url_pilar}.
- UN enlace a esta sección real de la web: [{seccion_label}]({seccion_url}).
- UN enlace externo de autoridad: [{fuente['nombre']}]({fuente['url']}).

ESTRUCTURA Y SEO:
- Usa 1 o 2 subtítulos H2 (##) que contengan la palabra clave o variantes que la gente busca de verdad.
- Termina con "## Preguntas frecuentes" seguido de UNA sola pregunta (### con la pregunta) y su respuesta en 2-3 frases. Ayuda a aparecer en los fragmentos destacados de Google.
- Cierra con una frase breve y honesta invitando a seguir las novedades en el canal de Telegram [OpoNoticias](https://t.me/OPONOTICIAS), sin sonar a anuncio.

DEVUELVE SOLO ESTE JSON (sin ```, sin texto antes ni después):
{{
  "titulo": "Título de máximo 60 caracteres, con la palabra clave al principio, sin clickbait",
  "resumen": "Meta descripción de 150-160 caracteres, atractiva y con la palabra clave",
  "contenido": "Artículo completo en markdown ({año})"
}}"""

    return _parsear_json(gb.claude(prompt, max_tokens=2500))


# ── Guardado ─────────────────────────────────────────────────────────────────

def _generar_portada(art, slug):
    """Genera la portada 1200×630 y la sube a Supabase. Devuelve URL o cadena vacía."""
    if not gii:
        return ""
    nombre_remoto = f"blog/covers/{slug}.jpg"
    url = gii.generar_y_subir_cover(
        {"categoria": "Guía de preparación", "titulo": art["titulo"]},
        nombre_remoto,
    )
    return url or ""


def _upsert_borrador(data):
    """Inserta o sobrescribe (on_conflict=slug) un borrador. Devuelve True si OK."""
    import urllib.request, urllib.error, json as _json
    url = f"{SUPABASE_URL}/rest/v1/articulos_blog?on_conflict=slug"
    req = urllib.request.Request(
        url, data=_json.dumps(data).encode(),
        headers={**gb.HEADERS_SB, "Prefer": "return=minimal,resolution=merge-duplicates"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15)
        return True
    except urllib.error.HTTPError as e:
        print(f"  ❌  Upsert Supabase: {e.code} — {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"  ❌  Upsert Supabase: {e}")
        return False


def guardar_borrador(art, tema, fecha_pub, imagen, overwrite=False):
    art["slug"] = tema["slug"]
    art["categoria"] = CATEGORIA_TEMAS
    art["fecha_pub"] = fecha_pub.isoformat() + "T08:00:00+00:00"
    art["imagen"] = imagen   # se "bakea" en el HTML; no se guarda en la tabla

    data = {
        "titulo":    art["titulo"],
        "slug":      tema["slug"],
        "resumen":   art.get("resumen", ""),
        "contenido": art["contenido"],
        "categoria": CATEGORIA_TEMAS,
        "tipo":      "ia",
        "publicado": False,
        "fecha_pub": art["fecha_pub"],
    }
    if overwrite:
        if not _upsert_borrador(data):
            return False
    else:
        status = gb.supabase_post("articulos_blog", data)
        if status == 409:
            print(f"  ⚠️  Slug duplicado '{tema['slug']}', saltando…")
            return False
        if status not in (200, 201):
            print(f"  ❌  Error Supabase (status {status})")
            return False

    os.makedirs(BLOG_DIR, exist_ok=True)
    ruta = os.path.join(BLOG_DIR, f"{tema['slug']}.html")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(gb.plantilla_articulo(art))
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print(f"📝  Blog · artículos temáticos — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 62)

    if not (SUPABASE_URL and SUPABASE_API_KEY and os.environ.get("ANTHROPIC_API_KEY")):
        print("❌ Faltan SUPABASE_URL, SUPABASE_API_KEY o ANTHROPIC_API_KEY")
        return

    # Modo regeneración: REGENERAR_N=k rehace los k primeros temas de la lista
    # (sobrescribiendo) en vez de saltar los ya existentes. Útil para refrescar
    # una tanda con el prompt actualizado.
    regen_n = os.environ.get("REGENERAR_N", "").strip()
    overwrite = regen_n.isdigit() and int(regen_n) > 0
    if overwrite:
        seleccion = TEMAS[:int(regen_n)]
        print(f"♻️  Regeneración forzada de {len(seleccion)} tema(s) (sobrescribe)\n")
    else:
        seleccion = temas_pendientes()
        if not seleccion:
            print("✅ No quedan temas pendientes: todos publicados o programados.")
            return
        print(f"📚 {len(seleccion)} tema(s) pendientes · genero hasta {MAX_POR_EJECUCION}\n")
        seleccion = seleccion[:MAX_POR_EJECUCION]

    fechas_usadas = []
    plan = []

    for tema in seleccion:
        print(f"📂 {tema['tema'][:60]}…")
        art = generar_articulo_tema(tema)
        if not art or not art.get("titulo") or not art.get("contenido"):
            print("  ❌ Generación fallida, saltando…")
            continue

        imagen = _generar_portada(art, tema["slug"])
        print(f"  🖼️  Portada: {'ok' if imagen else 'sin imagen'}")

        fecha_pub = _proxima_fecha(fechas_usadas)
        fechas_usadas.append(fecha_pub)

        print(f"  📝 {art['titulo'][:55]}")
        print(f"  📅 Programado: {fecha_pub.strftime('%A %d/%m/%Y')}")

        if guardar_borrador(art, tema, fecha_pub, imagen, overwrite=overwrite):
            plan.append({"fecha": fecha_pub, "titulo": art["titulo"], "slug": tema["slug"]})
            print("  ✅ Borrador guardado\n")
        time.sleep(4)

    print("=" * 62)
    for item in plan:
        print(f"  🗓️  {item['fecha'].strftime('%a %d/%m')} · {item['titulo'][:50]}")
        print(f"      → {BASE_URL}/blog/{item['slug']}.html")
    print(f"\n✅ {len(plan)} borrador(es) temático(s) generado(s).")
    print("   Se publican solos el lunes/jueves (publicar_programados.py).")
    print("=" * 62)


if __name__ == "__main__":
    main()
