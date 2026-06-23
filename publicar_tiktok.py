#!/usr/bin/env python3
"""
publicar_tiktok.py — Publicación de vídeo en TikTok vía Content Posting API.

El vídeo se sube como borrador (scope video.upload). El usuario lo encuentra
en TikTok app → Perfil → Borradores → pulsa Publicar (5 segundos de trabajo).

Para publicación directa (sin intervención) hay que pasar la Content Posting
API audit en el portal de desarrolladores de TikTok (1-2 semanas).

Tokens almacenados en Supabase Storage: social/tiktok/tokens.json
Se obtienen inicialmente con tiktok_oauth_setup.py y se renuevan solos en
cada ejecución (access_token = 24h, refresh_token = 365d, ambos rotan).

Variables de entorno necesarias:
  SUPABASE_URL         — URL del proyecto Supabase
  SUPABASE_API_KEY     — clave anon (o service_role) de Supabase
  TIKTOK_CLIENT_KEY    — Client key de la app TikTok (awrj1lcmltwx6qoe)
  TIKTOK_CLIENT_SECRET — Client secret de la app TikTok
"""

import os
import json
import time
import urllib.parse
import urllib.request
import urllib.error

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
STORAGE_BUCKET   = os.environ.get("SUPABASE_STORAGE_BUCKET", "social")
CLIENT_KEY       = os.environ.get("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET    = os.environ.get("TIKTOK_CLIENT_SECRET", "")

TOKENS_KEY = "tiktok/tokens.json"
TIKTOK_API = "https://open.tiktokapis.com/v2"


# ── Supabase Storage ───────────────────────────────────────────────────────────

def _leer_tokens():
    """Lee tokens desde Supabase Storage (bucket público)."""
    if not SUPABASE_URL:
        return None
    url = f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{TOKENS_KEY}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️  TikTok: no se pudieron leer tokens de Supabase ({e})")
        return None


def _guardar_tokens(tokens):
    """Sobreescribe tokens en Supabase Storage con los valores frescos."""
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        return
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
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"⚠️  TikTok: no se pudieron guardar tokens actualizados ({e})")


# ── OAuth token refresh ────────────────────────────────────────────────────────

def _refrescar(refresh_token):
    """Intercambia un refresh_token por nuevo access_token + refresh_token."""
    data = urllib.parse.urlencode({
        "client_key":    CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{TIKTOK_API}/oauth/token/",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8"))
        if resp.get("error"):
            print(f"⚠️  TikTok refresh error: {resp}")
            return None
        return resp
    except Exception as e:
        print(f"⚠️  TikTok: error al refrescar token ({e})")
        return None


def _obtener_access_token():
    """
    Lee tokens de Supabase, refresca (el access_token dura 24h y el script corre
    una vez al día, así que siempre refrescamos para que el refresh_token rote
    correctamente y no caduque por falta de uso).

    Devuelve el access_token fresco o None.
    """
    tokens = _leer_tokens()
    if not tokens:
        return None

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("⚠️  TikTok: tokens.json sin refresh_token")
        return None

    resp = _refrescar(refresh_token)
    if not resp:
        return None

    nuevos = {
        "access_token":       resp["access_token"],
        "refresh_token":      resp["refresh_token"],
        "open_id":            resp.get("open_id", tokens.get("open_id", "")),
        "expires_in":         resp.get("expires_in", 86400),
        "refresh_expires_in": resp.get("refresh_expires_in", 31536000),
        "obtained_at":        int(time.time()),
    }
    _guardar_tokens(nuevos)
    print("🔄 TikTok: token refrescado y guardado en Supabase")
    return nuevos["access_token"]


# ── API pública ────────────────────────────────────────────────────────────────

def configurado():
    """True si hay credenciales y Supabase configurados."""
    return bool(CLIENT_KEY and CLIENT_SECRET and SUPABASE_URL and SUPABASE_API_KEY)


def _consultar_estado(publish_id, access_token):
    """Consulta el estado de un publish_id (status/fetch). Devuelve el dict data o {}."""
    payload = json.dumps({"publish_id": publish_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{TIKTOK_API}/post/publish/status/fetch/",
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json; charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8"))
        return resp.get("data", {}) or {}
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:300]
        print(f"⚠️  TikTok status falló: HTTP {e.code} · {cuerpo}")
        return {}
    except Exception as e:
        print(f"⚠️  Error TikTok status: {e}")
        return {}


def publicar_draft_tiktok(video_url, titulo="", verificar_estado=False):
    """
    Sube un vídeo a la bandeja de borradores de TikTok (Content Posting API).

    El usuario lo verá en TikTok app → Perfil → Borradores y podrá publicarlo
    en un par de toques. Best-effort: nunca bloquea el flujo principal.

    Si verificar_estado=True, tras subir consulta el endpoint status/fetch
    varias veces y muestra el estado real (PROCESSING / SEND_TO_USER_INBOX /
    FAILED + fail_reason). Útil para diagnóstico.

    Returns True si la API aceptó el vídeo (el procesamiento es asíncrono).
    """
    if not configurado():
        print("ℹ️  TikTok: no configurado (faltan TIKTOK_CLIENT_KEY/SECRET o Supabase)")
        return False

    access_token = _obtener_access_token()
    if not access_token:
        print("⚠️  TikTok: no se pudo obtener access_token — omitiendo publicación")
        return False

    # Descargamos el vídeo y lo subimos por FILE_UPLOAD (bytes directos). Así no
    # hace falta verificar el dominio en TikTok, cosa imposible con la URL pública
    # de Supabase (*.supabase.co no es nuestro). El vídeo diario pesa ~8-13 MB,
    # bien dentro del límite de un solo chunk (<64 MB).
    try:
        with urllib.request.urlopen(video_url, timeout=120) as r:
            video_bytes = r.read()
    except Exception as e:
        print(f"⚠️  TikTok: no se pudo descargar el vídeo ({e})")
        return False
    video_size = len(video_bytes)
    if video_size == 0:
        print("⚠️  TikTok: el vídeo descargado está vacío")
        return False

    # 1) init: reservamos la subida y obtenemos upload_url + publish_id
    payload = json.dumps({
        "source_info": {
            "source":            "FILE_UPLOAD",
            "video_size":        video_size,
            "chunk_size":        video_size,
            "total_chunk_count": 1,
        }
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{TIKTOK_API}/post/publish/inbox/video/init/",
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json; charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:400]
        print(f"⚠️  TikTok init falló: HTTP {e.code} · {cuerpo}")
        return False
    except Exception as e:
        print(f"⚠️  Error TikTok init (no bloquea): {e}")
        return False

    if resp.get("error", {}).get("code", "") != "ok":
        print(f"⚠️  TikTok init: respuesta inesperada {resp}")
        return False

    data = resp.get("data", {})
    upload_url = data.get("upload_url", "")
    publish_id = data.get("publish_id", "")
    if not upload_url:
        print(f"⚠️  TikTok: init sin upload_url {resp}")
        return False

    # 2) subimos los bytes del vídeo al upload_url (PUT, sin Authorization)
    put = urllib.request.Request(
        upload_url,
        data=video_bytes,
        headers={
            "Content-Type":  "video/mp4",
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        },
        method="PUT",
    )
    try:
        urllib.request.urlopen(put, timeout=180).read()
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:400]
        print(f"⚠️  TikTok upload falló: HTTP {e.code} · {cuerpo}")
        return False
    except Exception as e:
        print(f"⚠️  Error TikTok upload (no bloquea): {e}")
        return False

    print(f"🎵 TikTok (borrador): publish_id={publish_id} — "
          f"abre la app (Perfil → Borradores) para publicar")

    if verificar_estado:
        print("🔎 Consultando estado real del borrador (status/fetch)…")
        ultimo = {}
        for intento in range(6):
            time.sleep(5)
            ultimo = _consultar_estado(publish_id, access_token)
            estado = ultimo.get("status", "?")
            print(f"   intento {intento + 1}: status={estado} "
                  f"fail_reason={ultimo.get('fail_reason', '')}")
            if estado in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"):
                break
        estado = ultimo.get("status", "")
        if estado == "SEND_TO_USER_INBOX":
            print("✅ Entregado al inbox/borradores del usuario.")
        elif estado == "FAILED":
            print(f"❌ TikTok marcó la publicación como FAILED: {ultimo.get('fail_reason', '')}")
        else:
            print(f"ℹ️  Estado final: {estado or 'desconocido'} (data completa: {ultimo})")

    return True
