#!/usr/bin/env python3
"""
crear_promo_kit.py — Gráficos promocionales del Kit del Opositor.

Uso puntual (NO va en ningún workflow): se ejecuta a mano, revisas los PNG y
los publicas tú. Se maqueta en HTML con la marca (Merriweather + Inter, paleta
de assets/style.css) y se captura al tamaño exacto de cada red.

Requiere Playwright (`pip install playwright && playwright install chromium`).
NO se usa el Chrome del sistema con `--headless --screenshot`: desde Chrome 132
el headless antiguo desapareció y esa combinación se queda colgada. Playwright
además permite esperar a `document.fonts.ready`, así que las tipografías de
Google Fonts nunca salen a medio cargar (con Chrome había que adivinar con un
--virtual-time-budget).

  python3 crear_promo_kit.py            # todo
  python3 crear_promo_kit.py ig-1 x     # solo algunas piezas

Salida: social/kit/*.png
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
SALIDA = REPO / "social" / "kit"

# Paleta de assets/style.css
CSS_BASE = """
@import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700;900&family=Inter:wght@400;500;600;700;800;900&display=swap');
:root{
  --primary:#5A5047; --secondary:#C4A574; --accent:#7A8B6E;
  --ink:#2B2622; --gray:#8B8B7A; --bg:#F8F6F2; --line:#E7E0D5;
  --serif:'Merriweather',Georgia,serif; --sans:'Inter',-apple-system,sans-serif;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);font-family:var(--sans);color:var(--ink);
     -webkit-font-smoothing:antialiased;overflow:hidden}
.card{width:100vw;height:100vh;display:flex;flex-direction:column;position:relative;overflow:hidden}
.grain:after{content:'';position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(circle at 80% 10%, rgba(196,165,116,.16), transparent 55%);}
.eyebrow{font-weight:800;letter-spacing:.16em;text-transform:uppercase;color:var(--secondary)}
h1,h2{font-family:var(--serif);font-weight:900;line-height:1.1;letter-spacing:-.02em}
.hl{color:var(--secondary)}
.brand{display:flex;align-items:center;gap:.6em}
.brand-mark{background:linear-gradient(135deg,#5A5047,#C4A574);color:#fff;
  font-family:var(--serif);font-weight:900;display:grid;place-items:center;border-radius:22%}
.brand-name{font-family:var(--serif);font-weight:900;color:var(--ink)}
.brand-name em{font-style:normal;font-weight:400}
.url{font-weight:700;color:var(--primary)}
ul{list-style:none;display:flex;flex-direction:column}
li{display:flex;align-items:flex-start;gap:.55em;color:var(--primary);font-weight:500}
li b{color:var(--ink);font-weight:700}
.tick{color:var(--accent);font-weight:900;flex:none}
.sheet{background:#fff;width:100%;border:1px solid var(--line);border-radius:14px;
  box-shadow:0 22px 50px rgba(43,38,34,.13);overflow:hidden}
.sheet-bar{background:#F3EFE8;border-bottom:1px solid var(--line);display:flex;gap:.4em;align-items:center}
.dot{border-radius:50%;background:#D8CFC0}
.row{display:grid;border-bottom:1px solid #F0EBE2}
.row:last-child{border-bottom:0}
.cell{padding:.55em .7em;font-size:.5em;color:var(--primary);border-right:1px solid #F0EBE2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cell:last-child{border-right:0}
.head .cell{background:#EFE9E0;font-weight:800;color:var(--ink);letter-spacing:.03em}
.fill{background:#FBF4E6}          /* celda que rellena el usuario */
.calc{background:#fff;color:var(--gray)}
.hot{background:#FBEAE6;color:#B4453A;font-weight:800}
.ok{color:var(--accent);font-weight:800}
"""


def brand(size_px, dark=False):
    # Sobre fondo oscuro el sello degradado (#5A5047→#C4A574) se funde con el
    # fondo y desaparece: se sustituye por ocre plano con texto oscuro.
    c = "#fff" if dark else "var(--ink)"
    mark = ("background:var(--secondary);color:var(--ink)" if dark else "")
    return f"""
    <div class="brand" style="font-size:{size_px}px">
      <div class="brand-mark" style="width:1.55em;height:1.55em;font-size:.62em;{mark}">ON</div>
      <div class="brand-name" style="color:{c}">Opo<em>Noticias</em></div>
    </div>"""


def hoja_retroplanning(scale=1.0):
    filas = [
        ("1", "8 sep", "14 sep", "1ª vuelta", "Temas 1-3"),
        ("2", "15 sep", "21 sep", "1ª vuelta", "Temas 4-6"),
        ("3", "22 sep", "28 sep", "1ª vuelta", "Temas 7-9"),
        ("…", "", "", "", ""),
        ("18", "5 ene", "11 ene", "Repaso final", "Todo el temario"),
        ("19", "12 ene", "18 ene", "Simulacros", "3 tests completos"),
    ]
    rows = "".join(
        f'<div class="row" style="grid-template-columns:.62fr .85fr .85fr 1.15fr 1.7fr">'
        + "".join(f'<div class="cell calc">{v}</div>' for v in f)
        + "</div>"
        for f in filas
    )
    return f"""
    <div class="sheet" style="font-size:{34*scale}px">
      <div class="sheet-bar" style="padding:.42em .6em">
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span style="font-size:.42em;font-weight:700;color:var(--gray);margin-left:.5em">1. Retroplanning</span>
      </div>
      <div class="row head" style="grid-template-columns:1.2fr 1fr">
        <div class="cell">Fecha del examen</div><div class="cell fill" style="color:#8a6d2f;font-weight:800">18/01/2027</div>
      </div>
      <div class="row" style="grid-template-columns:1.2fr 1fr">
        <div class="cell">Días que faltan</div><div class="cell calc" style="font-weight:800;color:var(--accent)">194</div>
      </div>
      <div class="row head" style="grid-template-columns:.62fr .85fr .85fr 1.15fr 1.7fr">
        <div class="cell">Sem</div><div class="cell">Desde</div><div class="cell">Hasta</div>
        <div class="cell">Fase</div><div class="cell">Qué estudiar</div>
      </div>
      {rows}
    </div>"""


def hoja_repasos(scale=1.0):
    filas = [
        ("3", "Acto administrativo", "hoy", "✓ hecho"),
        ("7", "Recursos", "hoy", "✓ hecho"),
        ("12", "Ley 39/2015 · Tít. IV", "hoy", "✓ hecho"),
    ]
    rows = "".join(
        f'<div class="row" style="grid-template-columns:.5fr 2.2fr .9fr .9fr">'
        f'<div class="cell calc">{a}</div><div class="cell calc">{b}</div>'
        f'<div class="cell hot">{c}</div><div class="cell ok">{d}</div></div>'
        for a, b, c, d in filas
    )
    return f"""
    <div class="sheet" style="font-size:{34*scale}px">
      <div class="sheet-bar" style="padding:.42em .6em">
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span style="font-size:.42em;font-weight:700;color:var(--gray);margin-left:.5em">2. Temario y Repasos</span>
      </div>
      <div class="row head" style="grid-template-columns:1.6fr 1fr">
        <div class="cell">Repasos para HOY</div><div class="cell hot" style="font-size:.62em">3</div>
      </div>
      <div class="row head" style="grid-template-columns:.5fr 2.2fr .9fr .9fr">
        <div class="cell">Nº</div><div class="cell">Tema</div>
        <div class="cell">Toca</div><div class="cell">Estado</div>
      </div>
      {rows}
    </div>"""


def hoja_tracker(scale=1.0):
    filas = [
        ("Constitución", "42/50", "84 %", ""),
        ("Ley 39/2015", "38/50", "76 %", ""),
        ("Función pública", "24/50", "48 %", "⚠ flojo"),
        ("UE", "31/50", "62 %", ""),
    ]
    rows = ""
    for a, b, c, d in filas:
        cls = "hot" if d else "calc"
        rows += (
            f'<div class="row" style="grid-template-columns:1.9fr .8fr .7fr 1fr">'
            f'<div class="cell {cls}">{a}</div><div class="cell {cls}">{b}</div>'
            f'<div class="cell {cls}">{c}</div><div class="cell {cls}">{d}</div></div>'
        )
    return f"""
    <div class="sheet" style="font-size:{34*scale}px">
      <div class="sheet-bar" style="padding:.42em .6em">
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span style="font-size:.42em;font-weight:700;color:var(--gray);margin-left:.5em">3. Tracker de Tests</span>
      </div>
      <div class="row head" style="grid-template-columns:1.9fr .8fr .7fr 1fr">
        <div class="cell">Tema</div><div class="cell">Aciertos</div>
        <div class="cell">%</div><div class="cell">Punto débil</div>
      </div>
      {rows}
    </div>"""


def _pagina(css_extra, cuerpo):
    return f"<!DOCTYPE html><html lang=es><head><meta charset=utf-8><style>{CSS_BASE}{css_extra}</style></head><body>{cuerpo}</body></html>"


# ── Piezas ────────────────────────────────────────────────────────────────────

def pieza_horizontal(w, h):
    """Facebook (1200×630), X (1600×900), Telegram (1280×720).

    Una sola hoja a la derecha: con dos, a 630px de alto se cortaba por abajo.
    """
    u = h / 630  # la restricción real es la altura, no el ancho
    return _pagina(
        f".card{{flex-direction:row;align-items:center;padding:{54*u}px {60*u}px;gap:{46*u}px}}",
        f"""
    <div class="card grain">
      <div style="flex:1.15;display:flex;flex-direction:column;gap:{20*u}px">
        {brand(int(28*u))}
        <div class="eyebrow" style="font-size:{15*u}px">Recurso gratuito</div>
        <h1 style="font-size:{50*u}px">El Excel que te lleva<br>la oposición <span class="hl">al día</span>.</h1>
        <ul style="gap:{12*u}px;font-size:{19*u}px;margin-top:{2*u}px">
          <li><span class="tick">✓</span><span><b>Retroplanning</b> desde la fecha de tu examen</span></li>
          <li><span class="tick">✓</span><span><b>Repaso espaciado</b> a 1, 7 y 30 días</span></li>
          <li><span class="tick">✓</span><span><b>Tracker de tests</b> que detecta tus temas flojos</span></li>
        </ul>
        <div style="margin-top:{12*u}px;font-size:{20*u}px;display:flex;align-items:center;gap:{16*u}px">
          <span style="background:var(--ink);color:#fff;padding:{10*u}px {19*u}px;border-radius:{9*u}px;font-weight:800">Gratis</span>
          <span class="url">oponoticias.com/recursos</span>
        </div>
      </div>
      <div style="flex:.85;display:flex;flex-direction:column;gap:{18*u}px">
        {hoja_retroplanning(u*0.70)}
        {hoja_repasos_chip(u)}
      </div>
    </div>""",
    )


def hoja_repasos_chip(u=1.0):
    """Tarjetita suelta: el gancho de los repasos sin la tabla entera."""
    return f"""
    <div class="sheet" style="padding:{20*u}px {24*u}px;display:flex;align-items:center;
                              justify-content:space-between;gap:{18*u}px">
      <div>
        <div style="font-size:{13*u}px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:var(--gray)">
          Repasos para hoy</div>
        <div style="font-size:{17*u}px;color:var(--primary);font-weight:600;margin-top:{4*u}px">
          Acto administrativo · Recursos · Ley&nbsp;39/2015</div>
      </div>
      <div style="font-family:var(--serif);font-weight:900;font-size:{44*u}px;color:#B4453A;line-height:1">3</div>
    </div>"""


def pieza_cuadrada():
    """WhatsApp / IG feed 1080×1080."""
    # Centrado, no space-between: con contenido corto en un lienzo cuadrado el
    # reparto de sobras dejaba dos huecos muertos enormes.
    return _pagina(
        ".card{padding:70px 66px;justify-content:center;gap:48px}",
        f"""
    <div class="card grain">
      <div style="display:flex;flex-direction:column;gap:20px">
        {brand(30)}
        <div class="eyebrow" style="font-size:17px;margin-top:4px">Recurso gratuito</div>
        <h1 style="font-size:64px">El Excel que te lleva<br>la oposición <span class="hl">al día</span>.</h1>
      </div>
      <div>{hoja_repasos(1.05)}</div>
      <div style="display:flex;align-items:center;justify-content:space-between">
        <span style="background:var(--ink);color:#fff;padding:15px 26px;border-radius:11px;font-weight:800;font-size:24px">Gratis</span>
        <span class="url" style="font-size:25px">oponoticias.com/recursos</span>
      </div>
    </div>""",
    )


def _slide(cuerpo, oscuro=False):
    fondo = "background:linear-gradient(150deg,#3A332C,#5A5047 60%,#6E6154)" if oscuro else ""
    return _pagina(
        f".card{{padding:88px 74px;justify-content:space-between;{fondo}}}",
        f'<div class="card grain">{cuerpo}</div>',
    )


def carrusel():
    """5 diapositivas 1080×1350 (4:5)."""
    s = []

    s.append(_slide(f"""
      {brand(30)}
      <h1 style="font-size:82px">Llevas 6 meses<br>estudiando.<br><span class="hl">¿Cuántos temas<br>recuerdas de verdad?</span></h1>
      <div style="font-size:26px;color:var(--gray);font-weight:600">Desliza →</div>"""))

    s.append(_slide(f"""
      <div><div class="eyebrow" style="font-size:19px">01 · Retroplanning</div>
        <h2 style="font-size:62px;margin-top:16px">Pon la fecha<br>del examen.</h2>
        <p style="font-size:27px;color:var(--primary);margin-top:20px;line-height:1.5;font-weight:500">
          Reparte el temario hacia atrás, semana a semana. Y te reserva tiempo
          para el repaso final y los simulacros.</p></div>
      <div style="flex:1;display:flex;align-items:center">{hoja_retroplanning(1.16)}</div>
      <div class="url" style="font-size:24px">oponoticias.com/recursos</div>"""))

    s.append(_slide(f"""
      <div><div class="eyebrow" style="font-size:19px">02 · Repaso espaciado</div>
        <h2 style="font-size:62px;margin-top:16px">Te dice qué<br>repasar <span class="hl">hoy</span>.</h2>
        <p style="font-size:27px;color:var(--primary);margin-top:20px;line-height:1.5;font-weight:500">
          Anotas cuándo estudias un tema. Él te avisa de los repasos
          a 1, 7 y 30 días. Sin llevar la cuenta a mano.</p></div>
      <div style="flex:1;display:flex;align-items:center">{hoja_repasos(1.20)}</div>
      <div class="url" style="font-size:24px">oponoticias.com/recursos</div>"""))

    s.append(_slide(f"""
      <div><div class="eyebrow" style="font-size:19px">03 · Tracker de tests</div>
        <h2 style="font-size:62px;margin-top:16px">Señala el tema<br>que estás evitando.</h2>
        <p style="font-size:27px;color:var(--primary);margin-top:20px;line-height:1.5;font-weight:500">
          Apuntas aciertos y fallos. Él calcula dónde flojeas.
          Ahí es donde tienes que meter horas.</p></div>
      <div style="flex:1;display:flex;align-items:center">{hoja_tracker(1.20)}</div>
      <div class="url" style="font-size:24px">oponoticias.com/recursos</div>"""))

    s.append(_slide(f"""
      {brand(32, dark=True)}
      <div>
        <h1 style="font-size:86px;color:#fff">Kit del<br>Opositor.</h1>
        <p style="font-size:30px;color:rgba(255,255,255,.82);margin-top:26px;font-weight:600">
          Excel + guía de uso en PDF.<br>Gratis, sin letra pequeña.</p>
      </div>
      <div style="display:flex;flex-direction:column;gap:16px">
        <span style="background:var(--secondary);color:#2B2622;padding:20px 0;border-radius:12px;
                     font-weight:800;font-size:29px;text-align:center">Descárgalo gratis</span>
        <span style="color:rgba(255,255,255,.65);font-size:23px;text-align:center;font-weight:600">
          Link en la bio · oponoticias.com/recursos</span>
      </div>""", oscuro=True))
    return s


PIEZAS = {
    "facebook":  (1200, 630,  pieza_horizontal),
    "x":         (1600, 900,  pieza_horizontal),
    "telegram":  (1280, 720,  pieza_horizontal),
    "whatsapp":  (1080, 1080, lambda w, h: pieza_cuadrada()),
}
for i, html in enumerate(carrusel(), 1):
    PIEZAS[f"ig-{i}"] = (1080, 1350, (lambda h: (lambda w, ht: h))(html))


class Navegador:
    """Un solo Chromium para todas las capturas (arrancarlo cuesta ~1 s)."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._b = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc):
        self._b.close()
        self._pw.stop()

    # `.card` lleva overflow:hidden, así que un elemento que se salga NO rompe el
    # PNG: se recorta en silencio y parece intencionado. Por eso se comprueba a
    # mano cada caja contra el lienzo, en vez de fiarse de mirar la imagen.
    _JS_DESBORDES = """() => {
      const fuera = [];
      const m = 2;  // holgura de 2px por redondeos de subpíxel
      document.querySelectorAll('.card *').forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        const d = [];
        if (r.left   < -m)                 d.push(`izq ${Math.round(-r.left)}px`);
        if (r.top    < -m)                 d.push(`arriba ${Math.round(-r.top)}px`);
        if (r.right  > innerWidth  + m)    d.push(`dcha ${Math.round(r.right - innerWidth)}px`);
        if (r.bottom > innerHeight + m)    d.push(`abajo ${Math.round(r.bottom - innerHeight)}px`);
        if (d.length) fuera.push(`${el.tagName.toLowerCase()}.${el.className || '?'}: ${d.join(', ')}`);
      });
      return fuera.slice(0, 4);
    }"""

    def capturar(self, html, w, h, destino):
        pg = self._b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.set_content(html, wait_until="load")
        pg.wait_for_function("document.fonts.ready.then(() => true)")
        desbordes = pg.evaluate(self._JS_DESBORDES)
        pg.screenshot(path=str(destino))
        pg.close()
        # Recomprime sin pérdida (mismo criterio que el commit 3fc8aaa)
        from PIL import Image
        Image.open(destino).save(destino, "PNG", optimize=True)
        return desbordes


def main():
    pedidas = sys.argv[1:] or list(PIEZAS)
    desconocidas = [p for p in pedidas if p not in PIEZAS]
    if desconocidas:
        sys.exit(f"✗ Piezas desconocidas: {', '.join(desconocidas)}\n  Disponibles: {', '.join(PIEZAS)}")

    SALIDA.mkdir(parents=True, exist_ok=True)
    with Navegador() as nav:
        for nombre in pedidas:
            w, h, fn = PIEZAS[nombre]
            destino = SALIDA / f"{nombre}.png"
            desbordes = nav.capturar(fn(w, h), w, h, destino)
            kb = destino.stat().st_size / 1024
            print(f"✓ {destino.relative_to(REPO)}  {w}×{h}  ({kb:.0f} KB)")
            for d in desbordes:
                print(f"    ⚠ se sale del lienzo → {d}")


if __name__ == "__main__":
    main()
