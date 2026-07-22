"""tests/test_tiktok_directo.py — publicación DIRECTA en TikTok.

Ejecuta:  python3 tests/test_tiktok_directo.py

Cubre las reglas que impone TikTok para el Direct Post y que, si se incumplen,
cuestan el acceso a la API:

  · Hay que consultar creator_info ANTES de publicar y usar SOLO uno de los
    `privacy_level_options` que devuelve. Mandar uno que el creador no tiene
    disponible es un rechazo (y saltarse sus ajustes, una violación de las UX
    guidelines).
  · Si el creador tiene desactivados comentarios / dúo / stitch, hay que
    respetarlo en cada publicación.
  · El título va limitado a 2200 caracteres UTF-16.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://ejemplo.invalid")
os.environ.setdefault("SUPABASE_API_KEY", "falsa")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import publicar_tiktok as tt  # noqa: E402

TODAS = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


# ── Elección del nivel de privacidad ────────────────────────────────────────
test("elige público cuando está disponible", lambda: (
    tt._elegir_privacidad(TODAS) == "PUBLIC_TO_EVERYONE"
))

test("si el creador NO puede publicar en público, no lo fuerza", lambda: (
    tt._elegir_privacidad(["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS"]) in
    ("SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS")
))

test("respeta una preferencia explícita si el creador la tiene", lambda: (
    tt._elegir_privacidad(TODAS, "SELF_ONLY") == "SELF_ONLY"
))

test("IGNORA una preferencia que el creador no tiene disponible", lambda: (
    tt._elegir_privacidad(["SELF_ONLY"], "PUBLIC_TO_EVERYONE") == "SELF_ONLY"
))

test("sin opciones devuelve None (no se puede publicar)", lambda: (
    tt._elegir_privacidad([]) is None
))


# ── post_info: respetar los ajustes del creador ─────────────────────────────
def post_info(titulo="hola", **creador):
    base = {"privacy_level_options": TODAS, "comment_disabled": False,
            "duet_disabled": False, "stitch_disabled": False}
    base.update(creador)
    return tt._construir_post_info(titulo, base)


test("caso normal: público y sin restricciones extra", lambda: (
    post_info()["privacy_level"] == "PUBLIC_TO_EVERYONE"
    and post_info()["disable_comment"] is False
))

test("si el creador tiene los comentarios desactivados, se respeta", lambda: (
    post_info(comment_disabled=True)["disable_comment"] is True
))

test("si el creador tiene el dúo desactivado, se respeta", lambda: (
    post_info(duet_disabled=True)["disable_duet"] is True
))

test("si el creador tiene el stitch desactivado, se respeta", lambda: (
    post_info(stitch_disabled=True)["disable_stitch"] is True
))

test("el título viaja tal cual", lambda: (
    post_info("Convocatorias del BOE")["title"] == "Convocatorias del BOE"
))

test("un título larguísimo se recorta al límite de TikTok (2200)", lambda: (
    len(post_info("x" * 3000)["title"]) == 2200
))

test("sin privacidad disponible, no construye post_info", lambda: (
    tt._construir_post_info("hola", {"privacy_level_options": []}) is None
))


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try:
            ok = fn()
        except Exception as e:                       # noqa: BLE001
            ok, nombre = False, f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}")
        fallos += not ok
    print("─" * 62)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
