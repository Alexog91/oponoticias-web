#!/usr/bin/env python3
"""
tiktok_oauth_setup.py — Autorización OAuth inicial de TikTok.

Uso (una sola vez):
  TIKTOK_CLIENT_SECRET=... SUPABASE_URL=... SUPABASE_API_KEY=... python3 tiktok_oauth_setup.py

Flujo:
  1. Genera la URL de autorización → la abre el usuario en el navegador.
  2. TikTok redirige a https://oponoticias.com/callback?code=XXXX
     (la página puede dar 404 — eso es normal).
  3. El usuario pega el código aquí → se intercambia por access_token + refresh_token.
  4. Los tokens se guardan en Supabase Storage (social/tiktok/tokens.json).
     De ahí los lee publicar_tiktok.py en cada ejecución diaria.
"""

import os
import json
import time
import urllib.parse
import urllib.request

CLIENT_KEY    = os.environ.get("TIKTOK_CLIENT_KEY", "awrj1lcmltwx6qoe")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI  = "https://oponoticias.com/callback"
SCOPE         = "user.info.basic,video.upload"

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
STORAGE_BUCKET   = os.environ.get("SUPABASE_STORAGE_BUCKET", "social")
TOKENS_KEY       = "tiktok/tokens.json"


def auth_url():
    params = {
        "client_key":    CLIENT_KEY,
        "response_type": "code",
        "scope":         SCOPE,
        "redirect_uri":  REDIRECT_URI,
        "state":         "oponoticias_tiktok_auth",
    }
    return "https://www.tiktok.com/v2/auth/authorize?" + urllib.parse.urlencode(params)


def exchange_code(code):
    data = urllib.parse.urlencode({
        "client_key":    CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "grant_type":    "authorization_code",
        "redirect_uri":  REDIRECT_URI,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def save_tokens(tokens):
    """Guarda los tokens en Supabase Storage para que publicar_tiktok.py los lea."""
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        print("⚠️  SUPABASE_URL / SUPABASE_API_KEY no configurados — tokens:")
        print(json.dumps(tokens, indent=2))
        return False

    payload = json.dumps(tokens, ensure_ascii=False).encode("utf-8")
    url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{TOKENS_KEY}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "apikey": SUPABASE_API_KEY,
            "Content-Type": "application/json",
            "x-upsert": "true",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"✅ Tokens guardados en Supabase: {r.read().decode('utf-8')}")
        return True
    except Exception as e:
        print(f"⚠️  No se pudo guardar en Supabase ({e}). Tokens manuales:")
        print(json.dumps(tokens, indent=2))
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("TikTok OAuth Setup — OpoNoticias")
    print("=" * 60)

    if not CLIENT_SECRET:
        print("❌ Falta TIKTOK_CLIENT_SECRET.")
        print("   Usa: TIKTOK_CLIENT_SECRET=<valor> python3 tiktok_oauth_setup.py")
        raise SystemExit(1)

    # Modo no interactivo (GitHub Actions): el código llega por variable de entorno.
    code = os.environ.get("TIKTOK_AUTH_CODE", "").strip()
    if code:
        # TikTok URL-encodea el code en el redirect (p.ej. '...%2A...'); lo normalizamos.
        code = urllib.parse.unquote(code)
        print("Código recibido por TIKTOK_AUTH_CODE (modo no interactivo).")
    else:
        print()
        print("1. Abre esta URL en tu navegador (logueado como @oponoticias):")
        print()
        print(auth_url())
        print()
        print("2. Acepta los permisos.")
        print("3. TikTok te redirigirá a https://oponoticias.com/callback?code=XXXX")
        print("   La página puede dar 404 — es normal.")
        print("4. Copia el valor del parámetro 'code' de la URL.")
        print()
        code = input("Pega el code aquí: ").strip()

    if not code:
        print("❌ Sin código. Abortando.")
        raise SystemExit(1)

    print()
    print("Intercambiando código por tokens...")
    try:
        resp = exchange_code(code)
    except Exception as e:
        print(f"❌ Error al llamar al endpoint: {e}")
        raise SystemExit(1)

    if resp.get("error"):
        print(f"❌ TikTok devolvió error: {resp['error']} — {resp.get('error_description', '')}")
        print(f"   Respuesta completa: {resp}")
        raise SystemExit(1)

    tokens = {
        "access_token":       resp["access_token"],
        "refresh_token":      resp["refresh_token"],
        "open_id":            resp.get("open_id", ""),
        "expires_in":         resp.get("expires_in", 86400),
        "refresh_expires_in": resp.get("refresh_expires_in", 31536000),
        "obtained_at":        int(time.time()),
    }

    print()
    print("✅ Tokens obtenidos:")
    print(f"   access_token:  {tokens['access_token'][:24]}...")
    print(f"   refresh_token: {tokens['refresh_token'][:24]}...")
    print(f"   open_id:       {tokens['open_id']}")
    print()

    save_tokens(tokens)

    print()
    print("─" * 60)
    print("Añade estos GitHub Secrets (Settings → Secrets → Actions):")
    print(f"  TIKTOK_CLIENT_KEY    = {CLIENT_KEY}")
    print(f"  TIKTOK_CLIENT_SECRET = {CLIENT_SECRET}")
    print()
    print("SUPABASE_URL y SUPABASE_API_KEY ya los tienes — no hace falta")
    print("añadir secrets de access_token ni refresh_token: se guardan y")
    print("renuevan automáticamente en Supabase Storage.")
    print("─" * 60)
