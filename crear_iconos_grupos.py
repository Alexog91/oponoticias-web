#!/usr/bin/env python3
"""
crear_iconos_grupos.py — Iconos de perfil para los dos grupos de Telegram
("OpoNoticias Chat" y "OpoNoticias Comunidad"), derivados del icono de marca
real (social/perfil-icono.png: fondo degradado oliva/tostado + "ON" grande en
serif blanco), añadiendo la palabra diferenciadora debajo con el mismo
tratamiento tipográfico que las "eyebrow" labels de la web (mayúsculas,
tracking amplio, Inter).

Uso puntual, NO va en ningún workflow.

  python3 crear_iconos_grupos.py           # los dos
  python3 crear_iconos_grupos.py chat      # solo uno

Salida: social/grupos/icono-chat.png, social/grupos/icono-comunidad.png
"""

import sys
from pathlib import Path

import crear_promo_kit as g   # Navegador (Playwright + chequeo de desbordes)

REPO = Path(__file__).resolve().parent
SALIDA = REPO / "social" / "grupos"

TAMANO = 512

# Mismo degradado orgánico que el icono de marca real (perfil-icono.png):
# varias paradas oliva/tostado/dorado en radiales superpuestos, no un simple
# linear-gradient de dos colores (ese es el mini-sello de las promos, no este).
FONDO = """
  background-color: #6b6252;
  background-image:
    radial-gradient(circle at 25% 20%, rgba(196,165,116,.55), transparent 55%),
    radial-gradient(circle at 80% 15%, rgba(122,139,110,.45), transparent 50%),
    radial-gradient(circle at 70% 85%, rgba(90,80,71,.65), transparent 60%),
    radial-gradient(circle at 20% 80%, rgba(43,38,34,.5), transparent 55%);
"""


def icono(palabra):
    return f"""<!DOCTYPE html><html><head><meta charset=utf-8><style>
      @import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@900&family=Inter:wght@800&display=swap');
      *{{margin:0;padding:0;box-sizing:border-box}}
      body{{width:{TAMANO}px;height:{TAMANO}px;{FONDO}
           display:flex;flex-direction:column;align-items:center;justify-content:center;
           overflow:hidden;font-family:'Inter',sans-serif}}
      .on{{font-family:'Merriweather',serif;font-weight:900;color:#fff;
           font-size:{TAMANO*0.34}px;line-height:1;letter-spacing:-.01em;
           text-shadow:0 2px 18px rgba(0,0,0,.18)}}
      .bar{{width:{TAMANO*0.30}px;height:{TAMANO*0.028}px;border-radius:999px;
            background:#C4A574;margin-top:{TAMANO*0.075}px}}
      .word{{margin-top:{TAMANO*0.055}px;color:rgba(255,255,255,.94);
             font-size:{TAMANO*0.088}px;font-weight:800;letter-spacing:.14em;
             text-transform:uppercase}}
    </style></head><body>
      <div class="on">ON</div>
      <div class="bar"></div>
      <div class="word">{palabra}</div>
    </body></html>"""


PIEZAS = {
    "chat":      ("CHAT", "icono-chat.png"),
    "comunidad": ("COMUNIDAD", "icono-comunidad.png"),
}


def main():
    pedidas = sys.argv[1:] or list(PIEZAS)
    desconocidas = [p for p in pedidas if p not in PIEZAS]
    if desconocidas:
        sys.exit(f"✗ Desconocidas: {', '.join(desconocidas)}\n  Disponibles: {', '.join(PIEZAS)}")

    SALIDA.mkdir(parents=True, exist_ok=True)
    with g.Navegador() as nav:
        for nombre in pedidas:
            palabra, archivo = PIEZAS[nombre]
            destino = SALIDA / archivo
            desbordes = nav.capturar(icono(palabra), TAMANO, TAMANO, destino)
            kb = destino.stat().st_size / 1024
            print(f"✓ {destino.relative_to(REPO)}  {TAMANO}×{TAMANO}  ({kb:.0f} KB)")
            for d in desbordes:
                print(f"    ⚠ se sale del lienzo → {d}")


if __name__ == "__main__":
    main()
