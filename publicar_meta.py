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
import urllib.error

GRAPH = "https://graph.facebook.com/v21.0"

FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
FB_PAGE_ID    = os.environ.get("FB_PAGE_ID", "")
FB_IG_ID      = os.environ.get("FB_IG_ID", "")


def configurado():
    """True si hay token y página configurados (FB). IG además necesita FB_IG_ID."""
    return bool(FB_PAGE_TOKEN and FB_PAGE_ID)


_PAGE_TOKEN_CACHE = None


def _page_token():
    """Page Access Token de la página, derivado del token configurado.

    Para PUBLICAR en una página hay que usar el token DE LA PÁGINA, no un token
    de usuario / System User directamente; con éste Meta devuelve el confuso
    '(#200) publish_actions are not available'. Se obtiene una vez con
    GET /{page}?fields=access_token y se cachea. Si falla, usa el configurado.
    """
    global _PAGE_TOKEN_CACHE
    if _PAGE_TOKEN_CACHE:
        return _PAGE_TOKEN_CACHE
    try:
        r = _get(FB_PAGE_ID, {"fields": "access_token", "access_token": FB_PAGE_TOKEN})
        _PAGE_TOKEN_CACHE = r.get("access_token") or FB_PAGE_TOKEN
    except Exception as e:
        print(f"⚠️  No se pudo obtener el token de página, uso el configurado ({e})")
        _PAGE_TOKEN_CACHE = FB_PAGE_TOKEN
    return _PAGE_TOKEN_CACHE


def _leer_error(e):
    """Extrae el cuerpo JSON de un HTTPError de la Graph API.

    Meta devuelve el motivo real (token caducado, permiso, etc.) en el cuerpo
    de la respuesta 400/401, que urllib NO incluye en str(e). Sin esto solo
    veríamos 'HTTP Error 400: Bad Request' sin saber la causa.
    """
    try:
        cuerpo = e.read().decode("utf-8", "replace")
    except Exception:
        return str(e)
    try:
        err = json.loads(cuerpo).get("error", {})
        msg  = err.get("message", "")
        code = err.get("code", "")
        sub  = err.get("error_subcode", "")
        return f"HTTP {e.code} · code={code}{f'/{sub}' if sub else ''} · {msg}"
    except Exception:
        return f"HTTP {getattr(e, 'code', '?')} · {cuerpo[:300]}"


def _post(path, params, timeout=60):
    """POST a la Graph API. Devuelve dict de respuesta o lanza excepción.

    En error HTTP relanza con el mensaje real de Meta (no solo el código)."""
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(f"{GRAPH}/{path}", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(_leer_error(e)) from None


def _get(path, params, timeout=30):
    """GET a la Graph API. Devuelve dict de respuesta o lanza excepción."""
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{GRAPH}/{path}?{qs}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(_leer_error(e)) from None


# ── Facebook ────────────────────────────────────────────────────────────────
def publicar_foto_facebook(image_url, mensaje):
    """Publica una foto con texto en la página de Facebook.

    Equivale al post de imagen que hacía Make. La foto se sube por URL y el
    `mensaje` (con enlace y hashtags) queda como texto del post.

    Devuelve el ID del post (str, truthy) si se publica, o False si falla. El
    ID permite luego comentar el post (p.ej. para poner el enlace). Los callers
    que solo comprueban `if ok:` siguen funcionando igual.
    """
    if not configurado():
        return False
    try:
        r = _post(f"{FB_PAGE_ID}/photos", {
            "url": image_url,
            "caption": mensaje,
            "access_token": _page_token(),
        })
        pid = r.get("post_id") or r.get("id")
        if pid:
            print(f"📘 Facebook (API directa): post {pid}")
            return pid
        print(f"⚠️  Facebook: respuesta inesperada {r}")
        return False
    except Exception as e:
        print(f"⚠️  Error Facebook API (no bloquea): {e}")
        return False


def comentar_facebook(post_id, mensaje):
    """Añade un comentario a un post/foto de la página.

    Se usa para poner el ENLACE como primer comentario en lugar de en el cuerpo
    del post: Facebook penaliza el alcance orgánico de los posts que llevan un
    enlace externo en el texto, así que la imagen va nativa y el enlace debajo.
    Best-effort: devuelve True/False sin romper el flujo.
    """
    if not configurado() or not post_id:
        return False
    try:
        r = _post(f"{post_id}/comments", {
            "message": mensaje,
            "access_token": _page_token(),
        })
        if r.get("id"):
            print(f"💬 Facebook: comentario {r['id']}")
            return True
        print(f"⚠️  Facebook comentario: respuesta inesperada {r}")
        return False
    except Exception as e:
        print(f"⚠️  Error comentario Facebook (no bloquea): {e}")
        return False


def publicar_foto_facebook_enlace(image_url, mensaje, link_url):
    """Post de FOTO NATIVA + enlace como PRIMER COMENTARIO.

    Patrón de máximo alcance orgánico en Facebook: la página penaliza los posts
    con enlace en el cuerpo, así que se sube la imagen como contenido nativo y el
    enlace se añade como primer comentario nada más publicar. Devuelve True si la
    foto se publicó (el comentario es best-effort: si falla, el post sigue ahí).
    """
    pid = publicar_foto_facebook(image_url, mensaje)
    if not pid:
        return False
    if link_url:
        comentar_facebook(pid, f"👉 Aquí lo tienes: {link_url}")
    return True


def publicar_enlace_facebook(mensaje, link_url=None):
    """Post de texto + enlace en la página de Facebook (sin imagen adjunta).

    Facebook genera automáticamente el preview del enlace (og:image, título…).
    `link_url` puede omitirse si ya va incluido en el texto de `mensaje`.
    """
    if not configurado():
        return False
    try:
        params = {"message": mensaje, "access_token": _page_token()}
        if link_url:
            params["link"] = link_url
        r = _post(f"{FB_PAGE_ID}/feed", params)
        if r.get("id"):
            print(f"📘 Facebook (texto+enlace): post {r['id']}")
            return True
        print(f"⚠️  Facebook: respuesta inesperada {r}")
        return False
    except Exception as e:
        print(f"⚠️  Error Facebook feed API (no bloquea): {e}")
        return False


def publicar_video_facebook(video_url, descripcion):
    """Publica un vídeo (reel/feed) en la página de Facebook por URL."""
    if not configurado():
        return False
    try:
        r = _post(f"{FB_PAGE_ID}/videos", {
            "file_url": video_url,
            "description": descripcion,
            "access_token": _page_token(),
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


def publicar_foto_instagram(image_url, caption):
    """Publica una foto individual en Instagram vía Graph API."""
    if not configurado() or not FB_IG_ID:
        return False
    try:
        cont = _post(f"{FB_IG_ID}/media", {
            "image_url": image_url,
            "caption": caption,
            "access_token": FB_PAGE_TOKEN,
        })
        if not cont.get("id"):
            print(f"⚠️  Instagram foto: no se creó contenedor {cont}")
            return False
        pub = _post(f"{FB_IG_ID}/media_publish", {
            "creation_id": cont["id"],
            "access_token": FB_PAGE_TOKEN,
        })
        if pub.get("id"):
            print(f"📷 Instagram foto (API directa): {pub['id']}")
            return True
        print(f"⚠️  Instagram foto: publicación inesperada {pub}")
        return False
    except Exception as e:
        print(f"⚠️  Error Instagram foto API (no bloquea): {e}")
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


def publicar_historia_instagram(video_url):
    """Publica el vídeo como HISTORIA de Instagram (contenedor STORIES + publish).

    Mismo flujo de dos pasos que el Reel, pero con `media_type=STORIES`. Las
    historias NO llevan pie de foto: Instagram lo ignora, así que ni se manda.
    Dura 24 h y se muestra arriba del todo, que es justo lo que le da alcance
    extra a la publicación del día.
    """
    if not configurado() or not FB_IG_ID:
        return False
    try:
        cont = _post(f"{FB_IG_ID}/media", {
            "media_type": "STORIES",
            "video_url": video_url,
            "access_token": FB_PAGE_TOKEN,
        })
        if not cont.get("id"):
            print(f"⚠️  Instagram Historia: no se creó contenedor {cont}")
            return False
        if not _esperar_contenedor(cont["id"]):
            return False
        pub = _post(f"{FB_IG_ID}/media_publish", {
            "creation_id": cont["id"],
            "access_token": FB_PAGE_TOKEN,
        })
        if pub.get("id"):
            print(f"📸 Instagram Historia (API directa): {pub['id']}")
            return True
        print(f"⚠️  Instagram Historia: publicación inesperada {pub}")
        return False
    except Exception as e:
        print(f"⚠️  Error Instagram Historia API (no bloquea): {e}")
        return False


# ── Diagnóstico ────────────────────────────────────────────────────────────────
def diagnosticar():
    """Comprueba el estado del token y los IDs sin exponer el secreto.

    Llama a la Graph API con el token actual y reporta:
      - validez del token (debug_token: tipo, app, caducidad, scopes)
      - acceso a la página (GET /{FB_PAGE_ID})
      - acceso a la cuenta de Instagram (GET /{FB_IG_ID})
    Pensado para ejecutarse en CI: `python3 -c "import publicar_meta; publicar_meta.diagnosticar()"`.
    """
    print("=" * 62)
    print("🔎  Diagnóstico Meta Graph API")
    print(f"    Versión API: {GRAPH}")
    print(f"    FB_PAGE_TOKEN: {'definido (' + str(len(FB_PAGE_TOKEN)) + ' chars)' if FB_PAGE_TOKEN else 'VACÍO'}")
    print(f"    FB_PAGE_ID:    {FB_PAGE_ID or 'VACÍO'}")
    print(f"    FB_IG_ID:      {FB_IG_ID or 'VACÍO'}")
    print("=" * 62)
    if not FB_PAGE_TOKEN:
        print("❌ Sin FB_PAGE_TOKEN: nada que comprobar.")
        return

    # 1) ¿El token es válido? debug_token devuelve metadatos del propio token.
    try:
        r = _get("debug_token", {"input_token": FB_PAGE_TOKEN,
                                 "access_token": FB_PAGE_TOKEN})
        d = r.get("data", {})
        validez = d.get("is_valid")
        exp = d.get("expires_at", 0)
        exp_txt = ("nunca caduca" if exp == 0
                   else time.strftime('%Y-%m-%d %H:%M', time.gmtime(exp)))
        print(f"1) Token válido: {validez}")
        print(f"   Tipo: {d.get('type')} · App ID: {d.get('app_id')}")
        print(f"   Caduca: {exp_txt}")
        print(f"   Permisos: {', '.join(d.get('scopes', [])) or '—'}")
        if d.get("error"):
            print(f"   ⚠️  error en token: {d['error']}")
    except Exception as e:
        print(f"1) ❌ debug_token falló: {e}")

    # 2) ¿Da acceso a la página?
    try:
        r = _get(FB_PAGE_ID, {"fields": "id,name", "access_token": FB_PAGE_TOKEN})
        print(f"2) Página OK: {r.get('name')} ({r.get('id')})")
    except Exception as e:
        print(f"2) ❌ Acceso a la página falló: {e}")

    # 3) ¿Da acceso a la cuenta de Instagram?
    if FB_IG_ID:
        try:
            r = _get(FB_IG_ID, {"fields": "id,username", "access_token": FB_PAGE_TOKEN})
            print(f"3) Instagram OK: @{r.get('username')} ({r.get('id')})")
        except Exception as e:
            print(f"3) ❌ Acceso a Instagram falló: {e}")
    print("=" * 62)


if __name__ == "__main__":
    diagnosticar()
