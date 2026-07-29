"""tests/test_aviso_borrador.py — el pie del vídeo, listo para copiar en TikTok.

Ejecuta:  python3 tests/test_aviso_borrador.py

Por qué existe: TikTok denegó el Direct Post (24 jul 2026), así que el vídeo
diario se queda en Borradores y hay que publicarlo a mano desde la app. El
endpoint de borradores **no admite título ni hashtags** — solo acepta
`source_info` con el vídeo, sin `post_info` (verificado en la documentación
oficial). O sea: no hay forma de dejar el texto ya escrito en el borrador.

Lo que sí se puede: mandarlo por Telegram al admin en un bloque <code>, que en
Telegram se copia **con un solo toque**. Así el trabajo diario pasa de escribir
título + 6 hashtags a: tocar para copiar, abrir TikTok, pegar.

Clave: el mensaje va con parse_mode=HTML, así que cualquier <, > o & del pie
rompería el envío entero si no se escapa.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://ejemplo.invalid")
os.environ.setdefault("SUPABASE_API_KEY", "falsa")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import publicar_tiktok as tt  # noqa: E402

PIE = ("🎯 Convocatorias del BOE · 24 julio\n\n"
       "👉 Toda la información y el enlace al BOE en oponoticias.com\n\n"
       "#oposiciones #empleopublico #BOE #oposicion2026 #funcionario #opositar")

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


# Quita el <code>…</code> para ver el texto tal cual quedaría al copiarlo.
def _copiado(pie):
    m = tt._mensaje_borrador(pie)
    return m.replace("<code>", "").replace("</code>", "")


test("🔴 el mensaje es SOLO el pie, tal cual — nada que borrar al pegar", lambda: (
    # Al quitar las etiquetas de formato, lo que queda es EXACTAMENTE el pie.
    _copiado(PIE) == PIE
))

test("el pie va dentro de un <code> (Telegram lo copia de un toque)", lambda: (
    tt._mensaje_borrador(PIE).startswith("<code>")
    and tt._mensaje_borrador(PIE).endswith("</code>")
))

test("NADA de avisos: ni 'borrador', ni 'Perfil', ni 'vídeo del día'", lambda: (
    "borrador" not in tt._mensaje_borrador(PIE).lower()
    and "perfil" not in tt._mensaje_borrador(PIE).lower()
    and "vídeo del día" not in tt._mensaje_borrador(PIE).lower()
    and "toca el texto" not in tt._mensaje_borrador(PIE).lower()
))

test("el texto del pie llega íntegro, con sus hashtags", lambda: (
    "#oposiciones" in tt._mensaje_borrador(PIE)
    and "#opositar" in tt._mensaje_borrador(PIE)
    and "oponoticias.com" in tt._mensaje_borrador(PIE)
))

# El envío usa parse_mode=HTML: sin escapar, un '<' rompe el mensaje entero.
test("🔴 escapa < > & para que HTML no rompa el envío", lambda: (
    (lambda m: "&lt;" in m and "&gt;" in m and "&amp;" in m)(
        tt._mensaje_borrador("Plazas <100> & más"))
))

test("no deja etiquetas HTML crudas venidas del pie", lambda: (
    "<b>" not in _copiado("texto con <b>negrita</b> inyectada")
    and "&lt;b&gt;" in tt._mensaje_borrador("texto con <b>negrita</b> inyectada")
))

test("un pie vacío no revienta", lambda: isinstance(tt._mensaje_borrador(""), str))

test("None no revienta", lambda: isinstance(tt._mensaje_borrador(None), str))

test("los emojis sobreviven", lambda: "🎯" in tt._mensaje_borrador(PIE))


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try:
            ok = fn()
        except Exception as e:                       # noqa: BLE001
            ok, nombre = False, f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}")
        fallos += not ok
    print("─" * 66)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
