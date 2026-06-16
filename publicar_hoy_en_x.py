#!/usr/bin/env python3
"""Publica en X las convocatorias de hoy ya guardadas en Supabase.

Uso (con Facebook deshabilitado en Make):
    python3 publicar_hoy_en_x.py

No llama a la API de Claude: usa resumen_ia ya guardado en Supabase.
"""
import os, json, re, unicodedata, urllib.request, urllib.parse, time, pathlib

SUPABASE_URL     = os.environ["SUPABASE_URL"]
SUPABASE_API_KEY = os.environ["SUPABASE_API_KEY"]
MAKE_WEBHOOK_URL = os.environ["MAKE_WEBHOOK_URL"]
IMAGEN_TWEET     = "https://oponoticias.com/social/tweet-card.png"
WEB_DIR          = pathlib.Path(__file__).parent / "convocatoria"

CCAA_TAGS = {
    "Andalucía":"#Andalucia","Aragón":"#Aragon","Asturias":"#Asturias",
    "Canarias":"#Canarias","Cantabria":"#Cantabria",
    "Castilla-La Mancha":"#CastillaLaMancha","Castilla y León":"#CastillaYLeon",
    "Cataluña":"#Cataluna","Ceuta":"#Ceuta","Extremadura":"#Extremadura",
    "Galicia":"#Galicia","Islas Baleares":"#IslasBaleares","La Rioja":"#LaRioja",
    "Madrid":"#Madrid","Melilla":"#Melilla","Murcia":"#Murcia",
    "Navarra":"#Navarra","País Vasco":"#PaisVasco",
    "Comunitat Valenciana":"#ComunidadValenciana",
}


def generar_slug(titulo, ref_boe=""):
    slug = titulo.lower()
    slug = unicodedata.normalize('NFKD', slug)
    slug = ''.join(c for c in slug if not unicodedata.combining(c))
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    slug = re.sub(r'-+', '-', slug)[:60]
    if ref_boe and ref_boe != "BOE":
        sufijo = re.sub(r'[^a-z0-9]+', '-', ref_boe.lower()).strip('-')
        return f"{slug}-{sufijo}.html"
    return f"{slug}.html"


def url_convocatoria(conv):
    slug = generar_slug(conv['titulo'], conv.get('ref_boe', ''))
    if (WEB_DIR / slug).exists():
        return f"https://oponoticias.com/convocatoria/{slug}"
    return "https://oponoticias.com"


def limpiar_titulo(titulo):
    titulo = re.sub(r'(?i)^resolución\s+(de\s+)?', '', titulo)
    titulo = re.sub(r'(?i)^orden\s+(de\s+)?', '', titulo)
    return titulo.strip()


def generar_tweet(conv):
    partes    = [p.strip() for p in (conv.get('resumen_ia') or conv.get('resumen_claude') or '').split(' - ')]
    plazas    = partes[0] if partes else ""
    puesto    = partes[1] if len(partes) > 1 else ""
    comunidad = conv.get('comunidad_autonoma') or ""
    titulo    = limpiar_titulo(conv['titulo'])
    url       = url_convocatoria(conv)
    tag_ccaa  = CCAA_TAGS.get(comunidad, "")
    hashtags  = f"#oposiciones #BOE {tag_ccaa}".strip()

    lineas = [f"📋 {titulo[:50]}{'…' if len(titulo) > 50 else ''}"]
    if puesto:
        lineas.append(f"🔢 {plazas} · {puesto[:40]}")
    if comunidad:
        lineas.append(f"📍 {comunidad}")
    lineas.append(f"\n🔗 {url}")
    lineas.append(
        "\n📘 https://www.facebook.com/profile.php?id=61590965302457"
        "  ·  📸 https://www.instagram.com/oponoticiason/"
        "  ·  ✈️ https://t.me/OPONOTICIAS"
    )
    lineas.append(f"\n{hashtags}")
    return "\n".join(lineas)


def obtener_convocatorias_hoy():
    """Devuelve las convocatorias de hoy con telegram_enviado=true."""
    qs = urllib.parse.urlencode({
        'telegram_enviado': 'eq.true',
        'order': 'id.desc',
        'limit': '100',
        'select': 'titulo,enlace,resumen_claude,comunidad_autonoma,fecha',
    })
    url = f"{SUPABASE_URL.rstrip('/')}/convocatorias?{qs}"
    headers = {
        'apikey': SUPABASE_API_KEY,
        'Authorization': f'Bearer {SUPABASE_API_KEY}',
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        rows = json.loads(r.read())
    print(f"📦 {len(rows)} convocatorias recientes con telegram_enviado=true")
    return rows


def enviar_tweet(conv, n, total):
    tweet = generar_tweet(conv)
    payload = json.dumps({
        "tweet": tweet,
        "imagen_tweet": IMAGEN_TWEET,
        "skip_facebook": True,
    }).encode('utf-8')
    req = urllib.request.Request(
        MAKE_WEBHOOK_URL, data=payload,
        headers={'Content-Type': 'application/json'}, method='POST'
    )
    urllib.request.urlopen(req, timeout=10).read()
    titulo_corto = conv['titulo'][:50]
    print(f"  [{n}/{total}] 🐦 {titulo_corto}…")


def main():
    convs = obtener_convocatorias_hoy()
    if not convs:
        print("No hay convocatorias.")
        return

    print(f"\n¿Publicar {len(convs)} tweets en X? (Asegúrate de tener Facebook deshabilitado en Make)")
    resp = input("Escribe el número de convocatorias a publicar (o Enter para todas): ").strip()
    if resp.isdigit():
        convs = convs[:int(resp)]

    print(f"\n🚀 Publicando {len(convs)} tweets…\n")
    ok, fail = 0, 0
    for i, conv in enumerate(convs, 1):
        try:
            enviar_tweet(conv, i, len(convs))
            ok += 1
            time.sleep(1.5)   # respetar rate limit de Buffer
        except Exception as e:
            print(f"  [{i}/{len(convs)}] ❌ Error: {e}")
            fail += 1

    print(f"\n✅ Publicados: {ok}  ❌ Errores: {fail}")


if __name__ == "__main__":
    main()
