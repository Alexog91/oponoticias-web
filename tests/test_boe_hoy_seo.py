"""tests/test_boe_hoy_seo.py — la página estática /boe-hoy tiene og:image,
Twitter Card, JSON-LD válido y og:url limpia (sin .html).

Ejecuta:  python3 tests/test_boe_hoy_seo.py

Auditoría SEO (17 sep 2026): boe-hoy.html (que Facebook comparte a diario) no
tenía imagen social ni datos estructurados, y su og:url llevaba ".html" (no
coincidía con el canonical limpio). Es un archivo ESTÁTICO, así que el test
lee el archivo y fija esas propiedades. Ver [[oponoticias-seo-web]].
"""
import re
import sys
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HTML = (RAIZ / "boe-hoy.html").read_text(encoding="utf-8")


def _ld_json_blocks(html_str):
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
test("tiene JSON-LD parseable",
     lambda: len(_ld_json_blocks(HTML)) >= 1)
test("og:url limpia, sin .html",
     lambda: 'property="og:url" content="https://oponoticias.com/boe-hoy"' in HTML)
# Regresiones
test("regresión: canonical intacto",
     lambda: 'rel="canonical" href="https://oponoticias.com/boe-hoy"' in HTML)
test("regresión: title intacto",
     lambda: "El BOE de hoy" in HTML)


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
