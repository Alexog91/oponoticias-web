"""tests/test_filtro_noticias.py — que no se cuele publicidad en las noticias.

Ejecuta:  python3 tests/test_filtro_noticias.py

Por qué existe: los feeds (sobre todo academias como Preparadores) publican a
veces contenido promocional que, como habla de oposiciones, pasa el filtro de
relevancia. El 30 jul 2026 se coló un artículo de la empresa SOCIALVA
("prepara oposiciones"). El filtro de relevancia dice "sí trata de
oposiciones" — cierto — pero no distingue noticia de anuncio.

`es_publicidad()` bloquea por nombre de marca/empresa. Conservador a propósito:
mejor dejar pasar algún anuncio dudoso que censurar una noticia real.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import actualizar_noticias as an  # noqa: E402

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731


# ── Publicidad que DEBE bloquearse ──────────────────────────────────────────
test("🔴 el anuncio de SOCIALVA que se coló", lambda: an.es_publicidad(
    "SOCIALVA prepara oposiciones para el empleo público con su método online",
    "La academia SOCIALVA ofrece cursos para preparar tu oposición.") is True)

test("SOCIALVA en la descripción, no en el título", lambda: an.es_publicidad(
    "Cómo aprobar tu oposición este año",
    "Con SOCIALVA lo tienes más fácil, apúntate ya.") is True)

test("SOCIALVA en minúsculas / con espacios raros", lambda: an.es_publicidad(
    "Prepara con  socialva  tus exámenes", "") is True)

# ── Noticias reales que NO deben bloquearse ─────────────────────────────────
test("noticia real de convocatoria pasa", lambda: an.es_publicidad(
    "El BOE publica 2.704 plazas de Policía Nacional",
    "La oferta de empleo público incluye plazas de acceso libre.") is False)

test("noticia que menciona 'preparación' pero es informativa", lambda: an.es_publicidad(
    "Consejos para la preparación de las oposiciones de Correos",
    "Claves para organizar el estudio de cara al examen.") is False)

test("noticia sobre una academia como HECHO noticioso no se bloquea por 'academia'", lambda: an.es_publicidad(
    "La Academia General Militar abre su proceso de admisión",
    "Convocatoria para el ingreso en la Academia General Militar.") is False)

test("título vacío no revienta", lambda: an.es_publicidad("", "") is False)
test("None no revienta", lambda: an.es_publicidad(None, None) is False)


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try:
            ok = fn()
        except Exception as e:                       # noqa: BLE001
            ok, nombre = False, f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}")
        fallos += not ok
    print("─" * 64)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
