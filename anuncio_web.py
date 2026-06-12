"""
Envía un mensaje de anuncio de la web a Telegram.
Uso: TELEGRAM_TOKEN=xxx TELEGRAM_CHAT_ID=xxx python3 anuncio_web.py
"""
import os
import urllib.request
import urllib.parse

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

mensaje = (
    "🚀 <b>¡Ya tenemos web!</b>\n\n"
    "A partir de ahora puedes consultar <b>todas las convocatorias de oposiciones</b> "
    "en nuestra página web, con filtros por categoría, comunidad autónoma y fecha.\n\n"
    "🔍 Busca tu oposición, guarda las que te interesan y consúltalas cuando quieras.\n\n"
    "👉 <b><a href=\"https://oponoticias.com\">oponoticias.com</a></b>\n\n"
    "Seguimos publicando aquí cada convocatoria del BOE en tiempo real 📡"
)

url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
data = {
    'chat_id':   TELEGRAM_CHAT_ID,
    'text':      mensaje,
    'parse_mode': 'HTML',
    'disable_web_page_preview': False,
}
req = urllib.request.Request(
    url,
    data=urllib.parse.urlencode(data).encode('utf-8'),
    headers={'Content-Type': 'application/x-www-form-urlencoded'}
)
resp = urllib.request.urlopen(req, timeout=10)
print("✅ Anuncio enviado:", resp.read().decode())
