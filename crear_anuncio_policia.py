#!/usr/bin/env python3
"""
crear_anuncio_policia.py — Imágenes de anuncio de la convocatoria destacada
(Policía Nacional · 2.704 plazas) para cada red social.

Uso puntual (NO va en ningún workflow): se ejecuta a mano, revisas los PNG y los
publicas tú. Reutiliza el motor de crear_promo_kit.py (Playwright + marca +
chequeo de desbordes). Mismos tokens de assets/style.css.

  python3 crear_anuncio_policia.py            # todas las piezas
  python3 crear_anuncio_policia.py facebook x # solo algunas

Salida: social/policia/*.png
"""

import sys
from pathlib import Path

import crear_promo_kit as g   # Navegador, CSS_BASE, brand, _pagina, capturar

REPO = Path(__file__).resolve().parent
SALIDA = REPO / "social" / "policia"

# Datos EXACTOS de la convocatoria (BOE-A-2026-15055):
N_PLAZAS   = "2.704"
LIBRES     = "2.163"
MILITARES  = "541"
PLAZO      = "15 días hábiles"


def ficha_card(scale=1.0):
    """Tarjeta tipo ficha de la web con los datos clave — ancla el anuncio en el
    artefacto real (mismo lenguaje visual que las fichas de convocatoria)."""
    filas = [("Puesto", "Policía Nacional"),
             ("Plazas", f"{N_PLAZAS}"),
             ("Ámbito", "Nacional / Estatal"),
             ("Sistema", "Oposición libre")]
    rows = "".join(
        '<div class="row" style="grid-template-columns:1fr 1.4fr">'
        f'<div class="cell" style="font-weight:700;color:var(--ink)">{k}</div>'
        f'<div class="cell calc" style="color:var(--primary);font-weight:600">{v}</div></div>'
        for k, v in filas)
    return f"""
    <div class="sheet" style="font-size:{34*scale}px">
      <div class="sheet-bar" style="padding:.42em .6em">
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span style="font-size:.42em;font-weight:700;color:var(--gray);margin-left:.5em">BOE-A-2026-15055</span>
      </div>
      {rows}
    </div>"""


def badge(u=1.0):
    return (f'<span style="display:inline-flex;align-items:center;gap:{8*u}px;'
            f'background:#B4453A;color:#fff;padding:{9*u}px {18*u}px;border-radius:999px;'
            f'font-weight:800;font-size:{15*u}px;letter-spacing:.08em;text-transform:uppercase">'
            f'● Nueva convocatoria · BOE</span>')


def numero(u=1.0, color="var(--ink)"):
    """El número es el protagonista (frontend-design: el héroe es la tesis)."""
    return (f'<div style="display:flex;align-items:baseline;gap:{12*u}px;line-height:.9">'
            f'<span style="font-family:var(--serif);font-weight:900;font-size:{118*u}px;'
            f'color:{color};letter-spacing:-.02em">{N_PLAZAS}</span>'
            f'<span style="font-family:var(--serif);font-weight:900;font-size:{40*u}px;'
            f'color:var(--secondary)">PLAZAS</span></div>')


def pieza_horizontal(w, h):
    """Facebook (1200×630), X (1600×900), Telegram (1280×720)."""
    u = h / 630
    return g._pagina(
        f".card{{flex-direction:row;align-items:center;padding:{54*u}px {60*u}px;gap:{48*u}px}}",
        f"""
    <div class="card grain">
      <div style="flex:1.15;display:flex;flex-direction:column;gap:{18*u}px">
        {g.brand(int(28*u))}
        {badge(u)}
        {numero(u)}
        <h1 style="font-size:{50*u}px;margin-top:{-4*u}px">Policía Nacional</h1>
        <div style="font-size:{20*u}px;color:var(--primary);font-weight:600">
          Escala Básica · oposición libre · {LIBRES} libres + {MILITARES} militares</div>
        <div style="display:flex;align-items:center;gap:{14*u}px;margin-top:{4*u}px;font-size:{20*u}px">
          <span style="background:var(--ink);color:#fff;padding:{9*u}px {17*u}px;border-radius:{8*u}px;font-weight:800">⏳ Plazo: {PLAZO}</span>
          <span class="url">oponoticias.com</span>
        </div>
      </div>
      <div style="flex:.85;display:flex;align-items:center">{ficha_card(u*0.78)}</div>
    </div>""",
    )


def pieza_cuadrada():
    """WhatsApp / IG feed 1080×1080."""
    return g._pagina(
        ".card{padding:74px 70px;justify-content:center;gap:34px}",
        f"""
    <div class="card grain">
      <div style="display:flex;flex-direction:column;gap:20px">
        {g.brand(30)}
        {badge(1.15)}
      </div>
      {numero(1.15)}
      <div>
        <h1 style="font-size:66px">Policía Nacional</h1>
        <p style="font-size:26px;color:var(--primary);font-weight:600;margin-top:10px">
          Escala Básica · oposición libre<br>{LIBRES} libres + {MILITARES} reserva militares</p>
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
        <span style="background:var(--ink);color:#fff;padding:15px 26px;border-radius:11px;font-weight:800;font-size:24px">⏳ Plazo: {PLAZO}</span>
        <span class="url" style="font-size:25px">oponoticias.com</span>
      </div>
    </div>""",
    )


def pieza_vertical():
    """Instagram feed 4:5 (1080×1350)."""
    return g._pagina(
        ".card{padding:80px 74px;justify-content:space-between}",
        f"""
    <div class="card grain">
      <div style="display:flex;flex-direction:column;gap:22px">
        {g.brand(32)}
        {badge(1.2)}
      </div>
      <div>
        {numero(1.35)}
        <h1 style="font-size:82px;margin-top:12px">Policía<br>Nacional</h1>
        <p style="font-size:30px;color:var(--primary);font-weight:600;margin-top:20px;line-height:1.4">
          Escala Básica · oposición libre<br>{LIBRES} libres + {MILITARES} reserva militares</p>
      </div>
      <div style="display:flex;flex-direction:column;gap:16px">
        <span style="background:#B4453A;color:#fff;padding:20px 0;border-radius:14px;
                     font-weight:800;font-size:30px;text-align:center">⏳ Plazo: solo {PLAZO}</span>
        <span class="url" style="font-size:26px;text-align:center">oponoticias.com</span>
      </div>
    </div>""",
    )


PIEZAS = {
    "facebook":  (1200, 630,  pieza_horizontal),
    "x":         (1600, 900,  pieza_horizontal),
    "telegram":  (1280, 720,  pieza_horizontal),
    "whatsapp":  (1080, 1080, lambda w, h: pieza_cuadrada()),
    "instagram": (1080, 1350, lambda w, h: pieza_vertical()),
}


def main():
    pedidas = sys.argv[1:] or list(PIEZAS)
    desconocidas = [p for p in pedidas if p not in PIEZAS]
    if desconocidas:
        sys.exit(f"✗ Piezas desconocidas: {', '.join(desconocidas)}\n  Disponibles: {', '.join(PIEZAS)}")

    SALIDA.mkdir(parents=True, exist_ok=True)
    with g.Navegador() as nav:
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
