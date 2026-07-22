"""tests/test_tiktok_code.py — limpiar el 'code' de TikTok pegado a mano.

Ejecuta:  python3 tests/test_tiktok_code.py

Por qué existe: tras autorizar, TikTok redirige a
    https://oponoticias.com/callback?code=XXXX&scopes=...&state=...
y hay que copiar el code de la barra de direcciones. Es facilísimo arrastrar
también el `&scopes=...&state=...` del final; entonces TikTok responde
`invalid_request - The request parameters are malformed` y el error no dice
nada de dónde está el fallo. Pasó de verdad el 22 jul 2026.

En vez de exigir puntería al copiar, el script acepta cualquiera de estas
formas: el code suelto, el code con la cola pegada, o la URL entera.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tiktok_oauth_setup as t  # noqa: E402

CODE = "abc123XYZ_-def"
COLA = "&scopes=video.publish%2Cuser.info.basic&state=oponoticias_tiktok_auth"

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


test("el code limpio se queda igual", lambda: t._limpiar_code(CODE) == CODE)

test("EL FALLO REAL: code con '&scopes=...&state=...' pegado detrás", lambda: (
    t._limpiar_code(CODE + COLA) == CODE
))

test("URL entera del redirect pegada tal cual", lambda: (
    t._limpiar_code("https://oponoticias.com/callback?code=" + CODE + COLA) == CODE
))

test("URL entera aunque dé 404 y se copie con espacios", lambda: (
    t._limpiar_code("  https://oponoticias.com/callback?code=" + CODE + COLA + "  ") == CODE
))

test("formato 'code=XXXX' sin URL", lambda: t._limpiar_code("code=" + CODE) == CODE)

test("decodifica %2A y %21, que TikTok mete en el code", lambda: (
    t._limpiar_code("Rn0aw%2Av%214837.e1") == "Rn0aw*v!4837.e1"
))

test("el caso literal que falló, con codificación y cola", lambda: (
    t._limpiar_code("Rn0aw%2Av%214837.e1" + COLA) == "Rn0aw*v!4837.e1"
))

test("un code que empieza por guion no se rompe", lambda: (
    t._limpiar_code("-ehwAVCYVu4kSl3sH" + COLA) == "-ehwAVCYVu4kSl3sH"
))

test("vacío devuelve vacío (no revienta)", lambda: t._limpiar_code("") == "")

test("None devuelve vacío", lambda: t._limpiar_code(None) == "")


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
