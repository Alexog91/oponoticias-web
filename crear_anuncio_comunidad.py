#!/usr/bin/env python3
"""
crear_anuncio_comunidad.py — Imagen promocional (una sola composición, exportada
al tamaño de cada red) para anunciar los dos espacios nuevos de Telegram:
OpoNoticias Chat (comentarios) y OpoNoticias Comunidad (temas).

Uso puntual (NO va en ningún workflow): se ejecuta a mano, revisas el PNG y lo
publicas tú. Reutiliza el motor de crear_promo_kit.py (Playwright + marca +
chequeo de desbordes). Los enlaces de invitación van en el texto del post, no
en la imagen (son hashes largos, no aportan nada escritos en la pieza).

  python3 crear_anuncio_comunidad.py            # todas las piezas
  python3 crear_anuncio_comunidad.py facebook x # solo algunas

Salida: social/comunidad/*.png
"""

import base64
import sys
from pathlib import Path

import crear_promo_kit as g   # Navegador, CSS_BASE, brand, _pagina

REPO = Path(__file__).resolve().parent
SALIDA = REPO / "social" / "comunidad"
GRUPOS = REPO / "social" / "grupos"


def _data_uri(png_path):
    return "data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode()


ICONO_CHAT = _data_uri(GRUPOS / "icono-chat.png")
ICONO_COMUNIDAD = _data_uri(GRUPOS / "icono-comunidad.png")

ITEMS = [
    (ICONO_CHAT, "OpoNoticias Chat", "Los comentarios de cada convocatoria, en un único sitio"),
    (ICONO_COMUNIDAD, "OpoNoticias Comunidad", "Dudas y conversación con otros opositores, por temas"),
]


def chip(icono, titulo, desc, u=1.0):
    return f"""
    <div style="display:flex;align-items:flex-start;gap:{16*u}px;background:#fff;
                border:1px solid var(--line);border-radius:{14*u}px;padding:{18*u}px {20*u}px;
                box-shadow:0 14px 30px rgba(43,38,34,.08)">
      <img src="{icono}" style="width:{46*u}px;height:{46*u}px;border-radius:50%;flex:none;
                  box-shadow:0 2px 8px rgba(43,38,34,.18)">
      <div>
        <div style="font-family:var(--serif);font-weight:900;font-size:{21*u}px;color:var(--ink)">{titulo}</div>
        <div style="font-size:{15*u}px;color:var(--primary);font-weight:500;margin-top:{4*u}px;line-height:1.35">{desc}</div>
      </div>
    </div>"""


def chips(u=1.0, gap=16):
    return f'<div style="display:flex;flex-direction:column;gap:{gap*u}px">' + \
        "".join(chip(i, t, d, u) for i, t, d in ITEMS) + "</div>"


def cta(u=1.0, center=False):
    just = "center" if center else "flex-start"
    return f"""
    <div style="display:flex;align-items:center;justify-content:{just};gap:{14*u}px">
      <span style="background:var(--ink);color:#fff;padding:{10*u}px {19*u}px;border-radius:{9*u}px;
                   font-weight:800;font-size:{18*u}px">Únete gratis</span>
      <span style="color:var(--gray);font-weight:600;font-size:{15*u}px">🔗 Enlaces en este mensaje</span>
    </div>"""


def pieza_horizontal(w, h):
    """Facebook (1200×630), X (1600×900), Telegram (1280×720)."""
    u = h / 630
    return g._pagina(
        f".card{{flex-direction:row;align-items:center;padding:{44*u}px {60*u}px;gap:{52*u}px}}",
        f"""
    <div class="card grain">
      <div style="flex:1.1;display:flex;flex-direction:column;gap:{22*u}px">
        {g.brand(int(28*u))}
        <div class="eyebrow" style="font-size:{15*u}px">Nuevo en Telegram</div>
        <h1 style="font-size:{58*u}px">Habla con otros<br><span class="hl">opositores</span>.</h1>
        <div style="margin-top:{6*u}px">{cta(u*1.1)}</div>
      </div>
      <div style="flex:1">{chips(u*1.18, gap=22)}</div>
    </div>""",
    )


def pieza_cuadrada():
    """WhatsApp / IG feed 1080×1080."""
    return g._pagina(
        ".card{padding:76px 72px;justify-content:center;gap:44px}",
        f"""
    <div class="card grain">
      <div style="display:flex;flex-direction:column;gap:20px">
        {g.brand(32)}
        <div class="eyebrow" style="font-size:18px;margin-top:2px">Nuevo en Telegram</div>
        <h1 style="font-size:76px">Habla con otros<br><span class="hl">opositores</span>.</h1>
      </div>
      {chips(1.3, gap=22)}
      {cta(1.25)}
    </div>""",
    )


def pieza_vertical():
    """Instagram feed 4:5 (1080×1350)."""
    return g._pagina(
        ".card{padding:88px 76px;justify-content:center;gap:56px}",
        f"""
    <div class="card grain">
      <div style="display:flex;flex-direction:column;gap:24px">
        {g.brand(34)}
        <div class="eyebrow" style="font-size:19px;margin-top:4px">Nuevo en Telegram</div>
        <h1 style="font-size:88px">Habla con<br>otros<br><span class="hl">opositores</span>.</h1>
      </div>
      {chips(1.5, gap=26)}
      {cta(1.35, center=True)}
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
