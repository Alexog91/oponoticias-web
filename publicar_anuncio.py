#!/usr/bin/env python3
"""publicar_anuncio.py — Publica un anuncio PUNTUAL en las redes (Telegram,
Facebook, Instagram, X). Se ejecuta a mano desde el workflow anuncio.yml, con las
mismas credenciales/funciones que la automatización diaria. Best-effort e
independiente por canal: si uno falla, los demás siguen.

Env: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, FB_PAGE_TOKEN, FB_PAGE_ID, FB_IG_ID,
     MAKE_WEBHOOK_URL.
Opcionales: CANALES (coma-separado: telegram,facebook,instagram,x; por defecto
     todos), DRY_RUN=1 (no publica; solo comprueba credenciales e imprime).
"""

import os
import sys
import json
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publicar_meta

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "")

LINK   = "https://oponoticias.com/preferencias"
BANNER = "https://oponoticias.com/social/telegram-banner.png"
TWEET_CARD = "https://oponoticias.com/social/tweet-card.png"

CANALES = {c.strip().lower() for c in
           os.environ.get("CANALES", "telegram,facebook,instagram,x").split(",") if c.strip()}
DRY = os.environ.get("DRY_RUN", "") not in ("", "0", "false", "False")

# ── Textos por red ──────────────────────────────────────────────────────────
TG_HTML = ("📢 <b>Novedad:</b> tu correo diario de OpoNoticias, ahora a tu medida.\n\n"
           "Elige tu <b>comunidad</b> y/o tu <b>categoría</b> (Administración, Sanidad, "
           "Educación…), de forma independiente, y recibe solo lo que te interesa.\n\n"
           f"👉 Ajusta tus preferencias: {LINK}")

FB_MSG = ("📢 Novedad: tu correo diario de oposiciones, ahora a tu medida. Elige tu "
          "comunidad y/o tu categoría (Administración, Sanidad, Educación…) y recibe "
          "solo las convocatorias que te interesan.")

IG_CAP = ("📢 Tu correo diario de oposiciones, ahora a tu medida ✨\n\n"
          "Elige tu comunidad y/o tu categoría (Administración, Sanidad, Educación…) y "
          "recibe cada mañana solo lo que te interesa.\n\n"
          "🔗 Ajústalo en oponoticias.com/preferencias\n\n"
          "#oposiciones #empleopublico #oposiciones2026 #administrativo #BOE #opositar")

X_TWEET = ("📢 Novedad: tu correo diario de @OpoNoticiasON ahora se filtra por comunidad "
           "y/o categoría (Administración, Sanidad, Educación…). Elige solo lo que te "
           f"interesa 👉 {LINK}")


# ── Un publicador por canal (devuelve un texto de estado; lanza en caso de error) ──
def post_telegram():
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return "sin credenciales"
    if DRY:
        return "DRY (credenciales OK)"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID, "text": TG_HTML,
        "parse_mode": "HTML", "disable_web_page_preview": "false",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    urllib.request.urlopen(req, timeout=15).read()
    return "OK"


def post_facebook():
    if not publicar_meta.configurado():
        return "sin credenciales"
    if DRY:
        return "DRY (credenciales OK)"
    return "OK" if publicar_meta.publicar_enlace_facebook(FB_MSG, LINK) else "fallo"


def post_instagram():
    if not publicar_meta.configurado():
        return "sin credenciales"
    if DRY:
        return "DRY (credenciales OK)"
    return "OK" if publicar_meta.publicar_foto_instagram(BANNER, IG_CAP) else "fallo"


def post_x():
    if not MAKE_WEBHOOK_URL:
        return "sin webhook (MAKE_WEBHOOK_URL)"
    if DRY:
        return "DRY (webhook OK)"
    payload = json.dumps({
        "tweet": X_TWEET, "imagen_tweet": TWEET_CARD, "skip_facebook": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        MAKE_WEBHOOK_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=15).read()
    return "OK (enviado a Make→Buffer)"


def main():
    print("📢 Publicando anuncio en redes…" + (" [DRY_RUN — no publica]" if DRY else ""))
    acciones = [("telegram", post_telegram), ("facebook", post_facebook),
                ("instagram", post_instagram), ("x", post_x)]
    for nombre, fn in acciones:
        if nombre not in CANALES:
            print(f"  ⏭️  {nombre}: omitido (no está en CANALES)")
            continue
        try:
            print(f"  ✅ {nombre}: {fn()}")
        except Exception as e:                       # noqa: BLE001
            print(f"  ❌ {nombre}: {e}")


if __name__ == "__main__":
    main()
