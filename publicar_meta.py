#!/usr/bin/env python3
"""
publicar_meta.py — Publicación DIRECTA en Facebook e Instagram vía Graph API.

Sustituye a los webhooks de Make.com (que tenían límite de operaciones y coste).
Usa un Page Access Token permanente (no caduca) generado desde una app propia en
modo desarrollo, con permisos pages_manage_posts, pages_read_engagement,
instagram_basic e instagram_content_publish. Publicar en la PROPIA página/IG no
requiere App Review de Meta.

Variables de entorno necesarias (GitHub Secrets):
  FB_PAGE_TOKEN  — Page Access Token permanente (expires_at = 0)
  FB_PAGE_ID     — ID de la página de Facebook
  FB_IG_ID       — ID de la cuenta de Instagram Business vinculada

Todo es best-effort: cualquier fallo se reporta y devuelve False sin romper el
flujo principal (BOE/Telegram).
"""

import os
import json
import time
import urllib.parse
import urllib.request

GRAPH = "https://graph.facebook.com/v21.0"

FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
FB_PAGE_ID    = os.environ.get("FB_PAGE_ID", "")
FB_IG_ID      = os.environ.get("FB_IG_ID", "")


def configurado():
    """True si hay token y página configurados (FB). IG además necesita FB_IG_ID."""
    return bool(FB_PAGE_TOKEN and FB_PAGE_ID)


def _post(path, params, timeout=60):
    """POST a la Graph API. Devuelve dict de respuesta o lanza excepción."""
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(f"{GRAPH}/{path}", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path, params, timeout=30):
    """GET a la Graph API. Devuelve dict de respuesta o lanza excepción."""
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{GRAPH}/{path}?{qs}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ── Facebook ────────────────────────────────────────────────────────────────
def publicar_foto_facebook(image_url, mensaje):
    """Publica una foto con texto en la página de Facebook.

    Equivale al post de imagen que hacía Make. La foto se sube por URL y el
    `mensaje` (con enlace y hashtags) queda como texto del post.
    """
    if not configurado():
        return False
    try:
        r = _post(f"{FB_PAGE_ID}/photos", {
            "url": image_url,
            "caption": mensaje,
            "access_token": FB_PAGE_TOKEN,
        })
        if r.get("id") or r.get("post_id"):
            print(f"📘 Facebook (API directa): post {r.get('post_id') or r.get('id')}")
            return True
        print(f"⚠️  Facebook: respuesta inesperada {r}")
        return False
    except Exception as e:
        print(f"⚠️  Error Facebook API (no bloquea): {e}")
        return False


def publicar_video_facebook(video_url, descripcion):
    """Publica un vídeo (reel/feed) en la página de Facebook por URL."""
    if not configurado():
        return False
    try:
        r = _post(f"{FB_PAGE_ID}/videos", {
            "file_url": video_url,
            "description": descripcion,
            "access_token": FB_PAGE_TOKEN,
        }, timeout=120)
        if r.get("id"):
            print(f"📘 Facebook vídeo (API directa): {r['id']}")
            return True
        print(f"⚠️  Facebook vídeo: respuesta inesperada {r}")
        return False
    except Exception as e:
        print(f"⚠️  Error Facebook vídeo API (no bloquea): {e}")
        return False


# ── Instagram ─────────────────────────────────────────────────────────────────
def _esperar_contenedor(creation_id, intentos=20, espera=6):
    """Sondea el estado de un contenedor de IG hasta que esté FINISHED.

    Los vídeos/reels necesitan procesarse antes de publicarse. Devuelve True si
    llega a FINISHED, False si expira o hay ERROR.
    """
    for _ in range(intentos):
        try:
            r = _get(creation_id, {"fields": "status_code,status",
                                   "access_token": FB_PAGE_TOKEN})
            code = r.get("status_code")
            if code == "FINISHED":
                return True
            if code == "ERROR":
                print(f"⚠️  Instagram: contenedor en ERROR {r.get('status')}")
                return False
        except Exception as e:
            print(f"⚠️  Instagram: sondeo contenedor falló ({e})")
        time.sleep(espera)
    print("⚠️  Instagram: contenedor no terminó a tiempo")
    return False


def publicar_carrusel_instagram(image_urls, caption):
    """Publica un carrusel (2-10 imágenes) en Instagram vía Graph API.

    Flujo: crea un contenedor por imagen (is_carousel_item), luego un contenedor
    CAROUSEL con los hijos, y finalmente lo publica.
    """
    if not configurado() or not FB_IG_ID:
        return False
    if len(image_urls) < 2:
        print("⚠️  Instagram: un carrusel necesita ≥2 imágenes.")
        return False
    try:
        hijos = []
        for url in image_urls:
            r = _post(f"{FB_IG_ID}/media", {
                "image_url": url,
                "is_carousel_item": "true",
                "access_token": FB_PAGE_TOKEN,
            })
            if not r.get("id"):
                print(f"⚠️  Instagram: no se creó contenedor para {url}: {r}")
                return False
            hijos.append(r["id"])

        cont = _post(f"{FB_IG_ID}/media", {
            "media_type": "CAROUSEL",
            "children": ",".join(hijos),
            "caption": caption,
            "access_token": FB_PAGE_TOKEN,
        })
        if not cont.get("id"):
            print(f"⚠️  Instagram: no se creó contenedor CAROUSEL: {cont}")
            return False

        pub = _post(f"{FB_IG_ID}/media_publish", {
            "creation_id": cont["id"],
            "access_token": FB_PAGE_TOKEN,
        })
        if pub.get("id"):
            print(f"📷 Instagram carrusel (API directa): {pub['id']}")
            return True
        print(f"⚠️  Instagram: publicación inesperada {pub}")
        return False
    except Exception as e:
        print(f"⚠️  Error Instagram carrusel API (no bloquea): {e}")
        return False


def publicar_reel_instagram(video_url, caption):
    """Publica un Reel en Instagram vía Graph API (contenedor REELS + publish)."""
    if not configurado() or not FB_IG_ID:
        return False
    try:
        cont = _post(f"{FB_IG_ID}/media", {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": FB_PAGE_TOKEN,
        })
        if not cont.get("id"):
            print(f"⚠️  Instagram Reel: no se creó contenedor {cont}")
            return False
        if not _esperar_contenedor(cont["id"]):
            return False
        pub = _post(f"{FB_IG_ID}/media_publish", {
            "creation_id": cont["id"],
            "access_token": FB_PAGE_TOKEN,
        })
        if pub.get("id"):
            print(f"📷 Instagram Reel (API directa): {pub['id']}")
            return True
        print(f"⚠️  Instagram Reel: publicación inesperada {pub}")
        return False
    except Exception as e:
        print(f"⚠️  Error Instagram Reel API (no bloquea): {e}")
        return False
