"""tests/test_blog_indice_seo.py — el índice del blog (/blog) tiene og:image,
Twitter Card y JSON-LD válido.

Ejecuta:  python3 tests/test_blog_indice_seo.py

Auditoría SEO (17 sep 2026): /blog no tenía imagen social ni datos
estructurados → preview vacía al compartir y sin schema. Estos tests fijan que
`plantilla_indice` los incluya y que el JSON-LD sea parseable (títulos con
comillas no deben romperlo). Ver [[oponoticias-seo-web]].
"""
import re
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generar_blog as gb  # noqa: E402

ARTICULOS = [
    {"slug": "guia-educacion", "titulo": 'Guía "especial" de oposiciones de Educación',
     "resumen": "Todo lo que necesitas.", "categoria": "educacion",
     "fecha_pub": "2026-09-01T00:00:00Z"},
    {"slug": "sanidad-2026", "titulo": "Oposiciones de Sanidad 2026",
     "resumen": "Plazas y plazos.", "categoria": "sanidad",
     "fecha_pub": "2026-08-15T00:00:00Z"},
]

HTML = gb.plantilla_indice(ARTICULOS)


def _ld_json_blocks(html_str):
    """Devuelve los objetos JSON de cada <script type=application/ld+json>."""
    bloques = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        html_str, re.DOTALL)
    return [json.loads(b) for b in bloques]


casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731

test("og:image apunta al banner social",
     lambda: 'property="og:image"' in HTML and "telegram-banner.png" in HTML)
test("tiene Twitter Card (summary_large_image)",
     lambda: 'name="twitter:card"' in HTML and "summary_large_image" in HTML)
test("tiene al menos un bloque JSON-LD",
     lambda: 'application/ld+json' in HTML)
test("el JSON-LD es parseable (comillas del título no lo rompen)",
     lambda: len(_ld_json_blocks(HTML)) >= 1)
test("el JSON-LD declara @type Blog",
     lambda: any(b.get("@type") == "Blog" for b in _ld_json_blocks(HTML)))
# Regresiones: no romper lo que ya estaba
test("regresión: sigue el canonical a /blog",
     lambda: 'rel="canonical" href="https://oponoticias.com/blog"' in HTML)
test("regresión: sigue index, follow",
     lambda: 'name="robots" content="index, follow"' in HTML)


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
