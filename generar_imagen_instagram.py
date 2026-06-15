#!/usr/bin/env python3
"""Genera imágenes de convocatoria para el carrusel diario de Instagram.

Rellena social/instagram-template.svg con los datos de cada convocatoria,
ajusta el tamaño del texto según su longitud, renderiza a PNG con Chrome
headless y sube el resultado a Supabase Storage (bucket público), devolviendo
la URL pública que Make.com → Instagram puede leer.

Diseñado para usarse desde leer_boe.py, pero ejecutable en solitario para
pruebas locales:  python3 generar_imagen_instagram.py
"""

import os
import re
import html
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "social" / "instagram-template.svg"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")  # service_role (escritura)
STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "social")

MESES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
               'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

# Rutas posibles de Chrome (Mac local / CI Linux). Se puede forzar con CHROME_BIN.
_CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
]


def _chrome_bin():
    for c in _CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    found = shutil.which("google-chrome") or shutil.which("chromium-browser") or shutil.which("chromium")
    return found


def _esc(texto):
    return html.escape((texto or "").strip(), quote=True)


def _wrap_palabras(texto, max_chars):
    """Reparte el texto en líneas sin cortar palabras."""
    palabras = texto.split()
    lineas, actual = [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if len(prueba) <= max_chars or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def _bloque_puesto(puesto):
    """Devuelve (font_size, y_primera_linea, tspans_svg) para el título-puesto.

    Escala el tamaño para que quepa en 1-2 líneas dentro del ancho útil (~920px)
    y ancla el bloque por abajo, justo encima del filete separador (y≈640)."""
    puesto = (puesto or "Convocatoria").strip()
    ancho_util = 920
    for size in (78, 70, 62, 54, 48):
        char_w = size * 0.60
        max_chars = max(6, int(ancho_util / char_w))
        lineas = _wrap_palabras(puesto, max_chars)
        if len(lineas) <= 2:
            break
    else:
        lineas = lineas[:2]
        if len(lineas) == 2 and len(lineas[1]) > max_chars:
            lineas[1] = lineas[1][:max_chars - 1].rstrip() + "…"

    line_height = round(size * 1.16)
    n = len(lineas)
    base_inferior = 636                      # baseline de la última línea
    y_primera = base_inferior - (n - 1) * line_height

    tspans = []
    for i, ln in enumerate(lineas):
        dy = 0 if i == 0 else line_height
        tspans.append(f'<tspan x="80" dy="{dy}">{_esc(ln)}</tspan>')
    return size, y_primera, "".join(tspans)


def _fit_una_linea(texto, max_chars, tamanos):
    """Escala una sola línea: prueba tamaños de mayor a menor; trunca si hace falta."""
    texto = (texto or "").strip()
    for size in tamanos:
        # max_chars escala inversamente con el tamaño relativo al primero
        cap = int(max_chars * tamanos[0] / size)
        if len(texto) <= cap:
            return size, texto
    size = tamanos[-1]
    cap = int(max_chars * tamanos[0] / size)
    if len(texto) > cap:
        texto = texto[:cap - 1].rstrip() + "…"
    return size, texto


def rellenar_template(datos):
    """datos: {fecha, organismo, puesto, plazas, lugar} → SVG relleno (str)."""
    svg = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Organismo (una línea, ~52 chars a tamaño 30)
    _, organismo = _fit_una_linea(datos.get("organismo", ""), 52, [30])

    # Puesto (1-2 líneas, escalable)
    p_size, p_y, p_tspans = _bloque_puesto(datos.get("puesto", ""))

    # Plazas (número corto o palabra)
    plazas = (str(datos.get("plazas", "")).strip() or "—")
    if len(plazas) <= 3:
        pl_size = 76
    elif len(plazas) <= 6:
        pl_size = 44
    else:
        pl_size = 30
        plazas = plazas[:9]

    # Lugar / CCAA (una línea dentro de la caja, ~606px)
    l_size, lugar = _fit_una_linea(datos.get("lugar", "España"), 16, [46, 38, 30])

    reemplazos = {
        "{{FECHA}}": _esc(datos.get("fecha", "")),
        "{{ORGANISMO}}": _esc(organismo),
        "{{PUESTO_SIZE}}": str(p_size),
        "{{PUESTO_Y}}": str(p_y),
        "{{PUESTO_TSPANS}}": p_tspans,
        "{{PLAZAS}}": _esc(plazas),
        "{{PLAZAS_SIZE}}": str(pl_size),
        "{{LUGAR}}": _esc(lugar),
        "{{LUGAR_SIZE}}": str(l_size),
    }
    for k, v in reemplazos.items():
        svg = svg.replace(k, v)
    return svg


def render_png(svg_texto, salida_png):
    """Renderiza un SVG (texto) a PNG 1080×1350 con Chrome headless."""
    chrome = _chrome_bin()
    if not chrome:
        raise RuntimeError("No se encontró Chrome/Chromium. Define CHROME_BIN.")

    salida_png = Path(salida_png)
    if salida_png.exists():
        salida_png.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        svg_tmp = Path(tmp) / "in.svg"
        svg_tmp.write_text(svg_texto, encoding="utf-8")
        user_dir = Path(tmp) / "chrome"
        proc = subprocess.Popen([
            chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--no-first-run", "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--force-device-scale-factor=1",
            f"--screenshot={salida_png}",
            "--window-size=1080,1350",
            "--default-background-color=00000000",
            "--hide-scrollbars",
            f"--user-data-dir={user_dir}",
            f"file://{svg_tmp}",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # No dependemos de que Chrome salga solo (con el navegador abierto a
        # veces se cuelga tras capturar): esperamos al PNG y matamos el proceso.
        listo = False
        for _ in range(40):
            if salida_png.exists() and salida_png.stat().st_size > 0:
                listo = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.5)
        time.sleep(0.3)  # margen para que termine de escribir
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

    if not (salida_png.exists() and salida_png.stat().st_size > 0):
        raise RuntimeError(f"Chrome no generó {salida_png}")
    return salida_png


def subir_a_storage(png_path, nombre_remoto):
    """Sube el PNG al bucket público de Supabase y devuelve la URL pública."""
    if not (SUPABASE_URL and SUPABASE_API_KEY):
        raise RuntimeError("Faltan SUPABASE_URL / SUPABASE_API_KEY")

    datos = Path(png_path).read_bytes()
    destino = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{nombre_remoto}"
    req = urllib.request.Request(
        destino, data=datos, method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "apikey": SUPABASE_API_KEY,
            "Content-Type": "image/png",
            "x-upsert": "true",
        },
    )
    urllib.request.urlopen(req, timeout=30).read()
    return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{nombre_remoto}"


def generar_y_subir(datos, nombre_remoto):
    """Rellena → renderiza → sube. Devuelve la URL pública (o None si falla)."""
    try:
        svg = rellenar_template(datos)
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "out.png"
            render_png(svg, png)
            return subir_a_storage(png, nombre_remoto)
    except Exception as e:
        print(f"⚠️  Imagen Instagram falló ({nombre_remoto}): {e}")
        return None


if __name__ == "__main__":
    # Prueba local: genera 2 PNGs de ejemplo en social/ (sin subir).
    ejemplos = [
        {"fecha": "13 jun 2026", "organismo": "Ayuntamiento de Madrid",
         "puesto": "Administrativo de gestión", "plazas": "25", "lugar": "Madrid"},
        {"fecha": "13 jun 2026", "organismo": "Servicio Andaluz de Salud",
         "puesto": "Enfermero/a especialista en salud mental", "plazas": "120",
         "lugar": "Andalucía"},
    ]
    for i, d in enumerate(ejemplos, 1):
        svg = rellenar_template(d)
        out = BASE_DIR / "social" / f"instagram-ejemplo-{i}.png"
        render_png(svg, out)
        print(f"✅ {out}")
