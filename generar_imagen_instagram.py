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


def _render_rsvg(svg_texto, salida_png, tmp):
    """Renderiza con rsvg-convert (librsvg). Determinista, sin navegador.
    Devuelve True si generó el PNG."""
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        return False
    svg_tmp = tmp / "in.svg"
    svg_tmp.write_text(svg_texto, encoding="utf-8")
    res = subprocess.run(
        [rsvg, "-w", "1080", "-h", "1350", "-o", str(salida_png), str(svg_tmp)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60,
    )
    if res.returncode != 0:
        err = (res.stderr or b"").decode("utf-8", "replace")[-600:]
        raise RuntimeError(f"rsvg-convert falló: {err}")
    return salida_png.exists() and salida_png.stat().st_size > 0


def _render_chrome(svg_texto, salida_png, tmp):
    """Renderiza con Chrome headless (fallback para Mac local)."""
    chrome = _chrome_bin()
    if not chrome:
        raise RuntimeError("No se encontró rsvg-convert ni Chrome. "
                           "Instala librsvg2-bin o define CHROME_BIN.")
    # Chrome headless captura HTML de forma más fiable que un .svg suelto.
    html_tmp = tmp / "in.html"
    html_tmp.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;}"
        "svg{display:block;width:1080px;height:1350px;}</style></head>"
        f"<body>{svg_texto}</body></html>",
        encoding="utf-8",
    )
    user_dir = tmp / "chrome"
    out_png = tmp / "screenshot.png"  # ruta relativa + cwd=tmp para no perderla
    err_log = tmp / "chrome.err"
    with open(err_log, "wb") as ferr:
        proc = subprocess.Popen([
            chrome, "--headless", "--disable-gpu", "--no-sandbox",
            "--no-first-run", "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--disable-background-networking",  # corta GCM que cuelga el proceso
            "--disable-component-update",
            "--disable-extensions", "--disable-sync", "--mute-audio",
            "--virtual-time-budget=5000",       # renderiza y sale solo
            "--force-device-scale-factor=1",
            "--screenshot=screenshot.png",
            "--window-size=1080,1350",
            "--default-background-color=00000000",
            "--hide-scrollbars",
            f"--user-data-dir={user_dir}",
            f"file://{html_tmp}",
        ], cwd=str(tmp), stdout=subprocess.DEVNULL, stderr=ferr)

        for _ in range(40):
            if out_png.exists() and out_png.stat().st_size > 0:
                break
            if proc.poll() is not None:
                break
            time.sleep(0.5)
        time.sleep(0.3)
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

    if out_png.exists() and out_png.stat().st_size > 0:
        shutil.copy2(str(out_png), str(salida_png))
        return True
    try:
        err = err_log.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        err = ""
    err = err[-600:] if err else "(sin stderr)"
    raise RuntimeError(f"Chrome no generó {salida_png}. stderr: {err}")


def render_png(svg_texto, salida_png):
    """Renderiza un SVG (texto) a PNG 1080×1350.

    Prefiere rsvg-convert (librsvg) por ser determinista y rápido; si no está
    disponible (p.ej. Mac local sin librsvg), cae a Chrome headless."""
    salida_png = Path(salida_png)
    if salida_png.exists():
        salida_png.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if not _render_rsvg(svg_texto, salida_png, tmp):
            _render_chrome(svg_texto, salida_png, tmp)

    if not (salida_png.exists() and salida_png.stat().st_size > 0):
        raise RuntimeError(f"No se pudo generar {salida_png}")
    return salida_png


def _a_jpeg(png_path, jpg_path):
    """Convierte el PNG a JPEG (Instagram solo acepta JPEG en el carrusel).
    Aplana cualquier transparencia sobre el fondo de marca por seguridad."""
    from PIL import Image
    img = Image.open(png_path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, (43, 38, 34))  # #2B2622, fondo de marca
        fondo.paste(img, mask=img.split()[-1])
        img = fondo
    else:
        img = img.convert("RGB")
    img.save(jpg_path, "JPEG", quality=88, optimize=True)
    return jpg_path


def subir_a_storage(archivo, nombre_remoto):
    """Sube el archivo al bucket público de Supabase y devuelve la URL pública."""
    if not (SUPABASE_URL and SUPABASE_API_KEY):
        raise RuntimeError("Faltan SUPABASE_URL / SUPABASE_API_KEY")

    ctype = "image/jpeg" if str(nombre_remoto).lower().endswith((".jpg", ".jpeg")) else "image/png"
    datos = Path(archivo).read_bytes()
    destino = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{nombre_remoto}"
    req = urllib.request.Request(
        destino, data=datos, method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "apikey": SUPABASE_API_KEY,
            "Content-Type": ctype,
            "x-upsert": "true",
        },
    )
    urllib.request.urlopen(req, timeout=30).read()
    return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{nombre_remoto}"


def generar_y_subir(datos, nombre_remoto):
    """Rellena → renderiza PNG → convierte a JPEG → sube. URL pública o None."""
    try:
        svg = rellenar_template(datos)
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "out.png"
            render_png(svg, png)
            jpg = Path(tmp) / "out.jpg"
            _a_jpeg(png, jpg)
            return subir_a_storage(jpg, nombre_remoto)
    except Exception as e:
        print(f"⚠️  Imagen Instagram falló ({nombre_remoto}): {e}")
        return None


# ── Blog card ─────────────────────────────────────────────────────────────────

BLOG_TEMPLATE_PATH = BASE_DIR / "social" / "blog-template.svg"


def _bloque_titulo_blog(titulo):
    """Título del artículo: hasta 4 líneas, base anclada en y=840."""
    titulo = (titulo or "Artículo").strip()
    ancho_util = 920
    lineas = []
    size = 36
    for size in (70, 62, 52, 42, 36):
        char_w = size * 0.55
        max_chars = max(6, int(ancho_util / char_w))
        lineas = _wrap_palabras(titulo, max_chars)
        if len(lineas) <= 4:
            break
    if len(lineas) > 4:
        lineas = lineas[:4]
        cap = max(6, int(ancho_util / (36 * 0.55)))
        if len(lineas[3]) > cap:
            lineas[3] = lineas[3][:cap - 1].rstrip() + "…"

    line_height = round(size * 1.18)
    n = len(lineas)
    # Centro el bloque en la zona [350, 860] (entre la pill y el separador)
    total_block = (n - 1) * line_height + size
    y_primera = 350 + (510 - total_block) // 2 + size
    # Garantizo que no desborda la zona
    y_primera = max(350 + size, min(y_primera, 860 - (n - 1) * line_height))

    tspans = []
    for i, ln in enumerate(lineas):
        dy = 0 if i == 0 else line_height
        tspans.append(f'<tspan x="80" dy="{dy}">{_esc(ln)}</tspan>')
    return size, y_primera, "".join(tspans)


def _bloque_resumen_blog(resumen):
    """Meta-descripción del artículo: hasta 3 líneas a 27 px."""
    resumen = (resumen or "").strip()
    size, max_lineas = 27, 3
    char_w = size * 0.52
    max_chars = max(10, int(920 / char_w))
    lineas = _wrap_palabras(resumen, max_chars)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        lineas[-1] = lineas[-1].rstrip("., ") + "…"
    line_height = round(size * 1.45)
    tspans = []
    for i, ln in enumerate(lineas):
        dy = 0 if i == 0 else line_height
        tspans.append(f'<tspan x="80" dy="{dy}">{_esc(ln)}</tspan>')
    return "".join(tspans)


def rellenar_blog_template(datos):
    """datos: {categoria, titulo, resumen} → SVG relleno (str)."""
    svg = BLOG_TEMPLATE_PATH.read_text(encoding="utf-8")
    categoria = _esc((datos.get("categoria") or "Blog").strip().upper())
    t_size, t_y, t_tspans = _bloque_titulo_blog(datos.get("titulo", ""))
    r_tspans = _bloque_resumen_blog(datos.get("resumen", ""))
    for k, v in {
        "{{CATEGORIA}}":      categoria,
        "{{TITULO_SIZE}}":    str(t_size),
        "{{TITULO_Y}}":       str(t_y),
        "{{TITULO_TSPANS}}":  t_tspans,
        "{{RESUMEN_TSPANS}}": r_tspans,
    }.items():
        svg = svg.replace(k, v)
    return svg


def generar_y_subir_blog(datos, nombre_remoto):
    """Genera la tarjeta de artículo de blog y la sube a Supabase. Devuelve URL o None."""
    try:
        svg = rellenar_blog_template(datos)
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "out.png"
            render_png(svg, png)
            jpg = Path(tmp) / "out.jpg"
            _a_jpeg(png, jpg)
            return subir_a_storage(jpg, nombre_remoto)
    except Exception as e:
        print(f"⚠️  Imagen blog falló ({nombre_remoto}): {e}")
        return None


if __name__ == "__main__":
    # Prueba local: genera 2 JPEGs de ejemplo en social/ (sin subir).
    ejemplos = [
        {"fecha": "13 jun 2026", "organismo": "Ayuntamiento de Madrid",
         "puesto": "Administrativo de gestión", "plazas": "25", "lugar": "Madrid"},
        {"fecha": "13 jun 2026", "organismo": "Servicio Andaluz de Salud",
         "puesto": "Enfermero/a especialista en salud mental", "plazas": "120",
         "lugar": "Andalucía"},
    ]
    for i, d in enumerate(ejemplos, 1):
        svg = rellenar_template(d)
        png = BASE_DIR / "social" / f"instagram-ejemplo-{i}.png"
        render_png(svg, png)
        out = BASE_DIR / "social" / f"instagram-ejemplo-{i}.jpg"
        _a_jpeg(png, out)
        png.unlink(missing_ok=True)
        print(f"✅ {out}")
