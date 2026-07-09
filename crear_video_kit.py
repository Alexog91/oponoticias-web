#!/usr/bin/env python3
"""
crear_video_kit.py — Vídeo vertical (1080×1920) para promocionar el Kit del
Opositor en TikTok / Reels / Shorts.

DELIBERADAMENTE FUERA DEL PIPELINE: no lo llama ningún workflow, no publica
nada. Se ejecuta a mano, revisas el MP4 y lo subes tú.

No usa Remotion (su única composición, DailyVideo, está atada a las tarjetas de
convocatorias). El motor es propio y sigue la skill `motion-design-serio`:

  1. Cada escena es una página HTML que expone `seek(t)` en JS: una función del
     tiempo que coloca cada elemento (opacidad + desplazamiento + contadores).
     No hay animaciones CSS sueltas; el estado en el instante t es determinista.
  2. Playwright pinta fotograma a fotograma (seek → screenshot). El texto NO se
     escala: entra y se queda nítido. Movimiento concentrado en la entrada
     (~2 s) y luego reposo — registro institucional, no "Ken Burns" constante.
  3. Staging real: los elementos entran escalonados (titular → hoja → dato),
     nunca todos a la vez. Cada escena tiene UN beat anclado en el contenido:
     un contador que sube, una fila que se marca. Ease serio (smoothstep, sin
     rebote ni overshoot).
  4. Locución edge-tts + cama musical con ducking (igual que el vídeo diario).
  5. Escenas encadenadas con fundido corto (xfade 0.4 s), no cortes secos.

  python3 crear_video_kit.py                 # con música
  python3 crear_video_kit.py --sin-musica
  python3 crear_video_kit.py --solo-escenas  # PNG del estado final, para revisar

Salida: videos/kit-del-opositor.mp4
"""

import argparse
import asyncio
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import crear_promo_kit as g   # reutiliza CSS_BASE, marca y paleta

REPO = Path(__file__).resolve().parent
SALIDA = REPO / "videos" / "kit-del-opositor.mp4"
MUSICA = REPO / "assets" / "music_bed.mp3"

FFMPEG, FFPROBE = "ffmpeg", "ffprobe"
W, H, FPS = 1080, 1920, 30
VOZ, RATE = "es-ES-XimenaNeural", "+2%"
GAP, TAIL, XFADE = 0.18, 0.9, 0.4    # silencio entre frases / cola final / fundido
ANIM = 2.3                            # ventana de entrada capturada por escena (s)

# Zonas seguras de TikTok/Reels sobre 1080×1920: la app superpone usuario, pie y
# música en la franja inferior (~300px) y los iconos a la derecha (~130px). Este
# relleno no es estético: impide que el CTA acabe tapado por la interfaz.
SEGURO = "padding:170px 140px 330px 82px"


# ── Runtime de animación (se inyecta en cada escena) ────────────────────────────
# seek(t): estado determinista en el instante t. Ease = smoothstep (ease-in-out,
# SIN overshoot ni rebote — la skill prohíbe curvas tipo bounce/elastic/back).
RUNTIME = """
<script>
  function E(p){ p = p<0?0:p>1?1:p; return p*p*(3-2*p); }   // smoothstep
  function seek(t){
    // Entradas: opacidad 0→1 + desplazamiento vertical dist→0.
    document.querySelectorAll('[data-in]').forEach(function(el){
      var s = parseFloat(el.dataset.in),
          d = parseFloat(el.dataset.dur || '0.55'),
          dist = parseFloat(el.dataset.dist || '26'),
          e = E((t - s) / d);
      el.style.opacity = e;
      el.style.transform = 'translateY(' + ((1 - e) * dist).toFixed(2) + 'px)';
    });
    // Contadores: el número sube de 0 al valor final (beat anclado en el dato).
    document.querySelectorAll('[data-count]').forEach(function(el){
      var s = parseFloat(el.dataset.cstart),
          d = parseFloat(el.dataset.cdur || '0.7'),
          to = parseFloat(el.dataset.count),
          e = E((t - s) / d);
      el.textContent = Math.round(e * to);
    });
  }
  window.seek = seek;
</script>
"""


def _pagina_anim(css_extra, cuerpo, oscuro=False):
    fondo = "background:linear-gradient(160deg,#3A332C,#5A5047 60%,#6E6154)" if oscuro else ""
    css = (g.CSS_BASE
           + f".card{{{SEGURO};justify-content:space-between;{fondo}}}"
           + ".sheet{box-shadow:0 30px 70px rgba(43,38,34,.22)}"
           + "[data-in]{opacity:0}"          # oculto hasta que seek() lo revele
           + css_extra)
    return (f"<!DOCTYPE html><html lang=es><head><meta charset=utf-8>"
            f"<style>{css}</style></head><body>"
            f'<div class="card grain">{cuerpo}</div>{RUNTIME}</body></html>')


def _in(t, dist=26, dur=0.55):
    return f'data-in="{t}" data-dist="{dist}" data-dur="{dur}"'


# ── Hojas animables (mismas clases CSS que crear_promo_kit, con hooks de anim) ───
def _sheet(barra, filas_html, scale):
    return f"""
    <div class="sheet" style="font-size:{34*scale}px">
      <div class="sheet-bar" style="padding:.42em .6em">
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span class="dot" style="width:.28em;height:.28em"></span>
        <span style="font-size:.42em;font-weight:700;color:var(--gray);margin-left:.5em">{barra}</span>
      </div>
      {filas_html}
    </div>"""


def sheet_retroplanning(scale, count_start):
    filas = [("1", "8 sep", "14 sep", "1ª vuelta", "Temas 1-3"),
             ("2", "15 sep", "21 sep", "1ª vuelta", "Temas 4-6"),
             ("3", "22 sep", "28 sep", "1ª vuelta", "Temas 7-9"),
             ("…", "", "", "", ""),
             ("19", "12 ene", "18 ene", "Simulacros", "3 tests")]
    cuerpo = "".join(
        '<div class="row" style="grid-template-columns:.62fr .85fr .85fr 1.15fr 1.5fr">'
        + "".join(f'<div class="cell calc">{v}</div>' for v in f) + "</div>"
        for f in filas)
    filas_html = f"""
      <div class="row head" style="grid-template-columns:1.2fr 1fr">
        <div class="cell">Fecha del examen</div>
        <div class="cell fill" style="color:#8a6d2f;font-weight:800">18/01/2027</div>
      </div>
      <div class="row" style="grid-template-columns:1.2fr 1fr">
        <div class="cell">Días que faltan</div>
        <div class="cell calc" style="font-weight:800;color:var(--accent)"><span
             data-count="194" data-cstart="{count_start}" data-cdur="0.8">0</span></div>
      </div>
      <div class="row head" style="grid-template-columns:.62fr .85fr .85fr 1.15fr 1.5fr">
        <div class="cell">Sem</div><div class="cell">Desde</div><div class="cell">Hasta</div>
        <div class="cell">Fase</div><div class="cell">Qué estudiar</div>
      </div>{cuerpo}"""
    return _sheet("1. Retroplanning", filas_html, scale)


def sheet_repasos(scale, count_start):
    filas = [("3", "Acto administrativo", "hoy", "✓ hecho"),
             ("7", "Recursos", "hoy", "✓ hecho"),
             ("12", "Ley 39/2015 · Tít. IV", "hoy", "✓ hecho")]
    cuerpo = "".join(
        '<div class="row" style="grid-template-columns:.5fr 2.2fr .9fr .9fr">'
        f'<div class="cell calc">{a}</div><div class="cell calc">{b}</div>'
        f'<div class="cell hot">{c}</div><div class="cell ok">{d}</div></div>'
        for a, b, c, d in filas)
    filas_html = f"""
      <div class="row head" style="grid-template-columns:1.6fr 1fr">
        <div class="cell">Repasos para HOY</div>
        <div class="cell hot" style="font-size:.62em"><span
             data-count="3" data-cstart="{count_start}" data-cdur="0.7">0</span></div>
      </div>
      <div class="row head" style="grid-template-columns:.5fr 2.2fr .9fr .9fr">
        <div class="cell">Nº</div><div class="cell">Tema</div>
        <div class="cell">Toca</div><div class="cell">Estado</div>
      </div>{cuerpo}"""
    return _sheet("2. Temario y Repasos", filas_html, scale)


def sheet_tracker(scale, flag_start):
    # La fila floja (Función pública) NO está roja al principio: un overlay rojo
    # entra al final (flag_start) — es el beat de pago de la escena.
    base = [("Constitución", "42/50", "84 %"),
            ("Ley 39/2015", "38/50", "76 %"),
            ("Función pública", "24/50", "48 %"),   # idx 2 = la floja
            ("UE", "31/50", "62 %")]
    filas = ""
    for i, (a, b, c) in enumerate(base):
        if i == 2:
            filas += (
                '<div class="row" style="grid-template-columns:1.9fr .8fr .7fr 1fr;position:relative">'
                f'<div class="cell calc">{a}</div><div class="cell calc">{b}</div>'
                f'<div class="cell calc">{c}</div><div class="cell calc"></div>'
                f'<div {_in(flag_start, dist=0, dur=0.35)} style="position:absolute;inset:0;'
                'display:grid;grid-template-columns:1.9fr .8fr .7fr 1fr;'
                'background:#FBEAE6">'
                f'<div class="cell hot">{a}</div><div class="cell hot">{b}</div>'
                f'<div class="cell hot">{c}</div><div class="cell hot">⚠ flojo</div></div></div>')
        else:
            filas += (
                '<div class="row" style="grid-template-columns:1.9fr .8fr .7fr 1fr">'
                f'<div class="cell calc">{a}</div><div class="cell calc">{b}</div>'
                f'<div class="cell calc">{c}</div><div class="cell calc"></div></div>')
    filas_html = f"""
      <div class="row head" style="grid-template-columns:1.9fr .8fr .7fr 1fr">
        <div class="cell">Tema</div><div class="cell">Aciertos</div>
        <div class="cell">%</div><div class="cell">Punto débil</div>
      </div>{filas}"""
    return _sheet("3. Tracker de Tests", filas_html, scale)


# ── Escenas ─────────────────────────────────────────────────────────────────────
# Cada escena: narración + HTML con la línea de tiempo embebida en data-in/-count.
# El orden de entrada es siempre titular → hoja → dato de apoyo (staging).
def _bloque_titulo(eyebrow, h2):
    return (f'<div {_in(0.0, dist=20)}>'
            f'<div class="eyebrow" style="font-size:26px">{eyebrow}</div>'
            f'<h2 {_in(0.15, dist=24)} style="font-size:84px;margin-top:22px">{h2}</h2></div>')


def _apoyo(texto, t=1.5):
    return (f'<div {_in(t, dist=18)} style="font-size:34px;color:var(--primary);'
            f'font-weight:600;line-height:1.45">{texto}</div>')


ESCENAS = [
    {   # 0 · gancho — dos líneas escalonadas, la pregunta (ocre) entra después
        "narr": "Esto es lo que le falta al noventa por ciento de opositores.",
        "html": _pagina_anim("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(40)}</div>
          <h1 style="font-size:108px">
            <span {_in(0.25, dist=26)} style="display:block">Estudias mucho.</span>
            <span {_in(0.85, dist=26)} class="hl" style="display:block">¿Y recuerdas<br>lo de marzo?</span>
          </h1>
          <div {_in(1.6, dist=16)} style="font-size:34px;color:var(--gray);font-weight:600">
            Kit del Opositor · gratis</div>"""),
    },
    {   # 1 · retroplanning — la hoja entra, luego "194 días" cuenta
        "narr": "Pones la fecha del examen, y reparte el temario hacia atrás. Semana a semana.",
        "html": _pagina_anim("", f"""
          {_bloque_titulo("01 · Retroplanning", "Pon la fecha<br>del examen.")}
          <div {_in(0.6, dist=40, dur=0.7)} style="flex:1;display:flex;align-items:center">
            {sheet_retroplanning(1.34, count_start=1.4)}</div>
          {_apoyo("Te reserva tiempo para el<br>repaso final y los simulacros.", 1.9)}"""),
    },
    {   # 2 · repaso — la hoja entra, luego "Repasos para HOY" sube a 3
        "narr": "Y cada mañana te dice qué tienes que repasar. A uno, siete y treinta días.",
        "html": _pagina_anim("", f"""
          {_bloque_titulo("02 · Repaso espaciado", 'Qué repasar<br><span class="hl">hoy</span>.')}
          <div {_in(0.6, dist=40, dur=0.7)} style="flex:1;display:flex;align-items:center">
            {sheet_repasos(1.40, count_start=1.4)}</div>
          {_apoyo("Sin llevar la cuenta a mano.", 1.9)}"""),
    },
    {   # 3 · tracker — la hoja entra, luego la fila floja se marca en rojo
        "narr": "Apuntas tus tests. Y te señala el tema que estás evitando.",
        "html": _pagina_anim("", f"""
          {_bloque_titulo("03 · Tracker de tests", "Tu punto<br>débil, a la vista.")}
          <div {_in(0.6, dist=40, dur=0.7)} style="flex:1;display:flex;align-items:center">
            {sheet_tracker(1.40, flag_start=1.6)}</div>
          {_apoyo("Ahí es donde tienes que meter horas.", 2.0)}"""),
    },
    {   # 4 · cierre — marca, título, y el CTA entra al final
        "narr": "Se llama Kit del Opositor. Es gratis. Está en oponoticias punto com.",
        "html": _pagina_anim("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42, dark=True)}</div>
          <div>
            <h1 {_in(0.35, dist=26)} style="font-size:128px;color:#fff">Kit del<br>Opositor.</h1>
            <p {_in(0.8, dist=20)} style="font-size:42px;color:rgba(255,255,255,.82);
               margin-top:34px;font-weight:600">Excel + guía de uso.<br>Gratis, sin letra pequeña.</p>
          </div>
          <div {_in(1.3, dist=22)} style="display:flex;flex-direction:column;gap:22px">
            <span style="background:var(--secondary);color:#2B2622;padding:30px 0;border-radius:18px;
                         font-weight:800;font-size:44px;text-align:center">Descárgalo gratis</span>
            <span style="color:rgba(255,255,255,.68);font-size:32px;text-align:center;font-weight:700">
              oponoticias.com/recursos</span>
          </div>""", oscuro=True),
    },
]


# ── Audio (sin cambios respecto a la versión anterior) ──────────────────────────
async def _tts(texto, destino):
    import edge_tts
    comm = edge_tts.Communicate(texto, VOZ, rate=RATE)
    with open(destino, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def _dur(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def sintetizar(tmp):
    """Locución completa + duración de cada escena (voz + GAP)."""
    piezas, duraciones = [], []
    for i, esc in enumerate(ESCENAS):
        mp3, wav = tmp / f"raw{i}.mp3", tmp / f"seg{i}.wav"
        asyncio.run(_tts(esc["narr"], mp3))
        subprocess.run([FFMPEG, "-y", "-i", str(mp3), "-ar", "44100", "-ac", "2", str(wav)],
                       check=True, capture_output=True)
        d = _dur(wav)
        duraciones.append(d + GAP + (TAIL if i == len(ESCENAS) - 1 else 0))
        piezas.append(wav)

    lista = tmp / "voz.txt"
    partes = []
    for i, wav in enumerate(piezas):
        partes.append(wav)
        sil = tmp / f"sil{i}.wav"
        d = GAP + (TAIL if i == len(piezas) - 1 else 0)
        subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-t", f"{d:.3f}", str(sil)], check=True, capture_output=True)
        partes.append(sil)
    lista.write_text("".join(f"file '{p}'\n" for p in partes), encoding="utf-8")
    voz = tmp / "voice.wav"
    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
                    "-c", "copy", str(voz)], check=True, capture_output=True)
    return voz, duraciones, _dur(voz)


def mezclar(voz, total, destino, con_musica):
    fade = f"afade=t=out:st={max(0.0, total - 0.6):.2f}:d=0.6"
    if con_musica and MUSICA.exists():
        cmd = [FFMPEG, "-y", "-i", str(voz), "-stream_loop", "-1", "-i", str(MUSICA),
               "-filter_complex",
               "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,asplit=2[vmix][vkey];"
               "[1:a]loudnorm=I=-30:TP=-3:LRA=11[m];"
               "[m][vkey]sidechaincompress=threshold=0.04:ratio=6:attack=5:release=350[mduck];"
               "[vmix][mduck]amix=inputs=2:duration=longest:dropout_transition=0[mix];"
               f"[mix]loudnorm=I=-16:TP=-1.5:LRA=11,{fade},alimiter=limit=0.95[a]",
               "-map", "[a]", "-t", f"{total:.2f}", "-ar", "44100", "-ac", "2", str(destino)]
    else:
        cmd = [FFMPEG, "-y", "-i", str(voz), "-af",
               f"loudnorm=I=-16:TP=-1.5:LRA=11,{fade}",
               "-t", f"{total:.2f}", "-ar", "44100", "-ac", "2", str(destino)]
    subprocess.run(cmd, check=True, capture_output=True)


# ── Vídeo: captura por fotogramas + hold ────────────────────────────────────────
def capturar_escena(nav_page, html, frames_dir, n_frames):
    """Pinta [0..ANIM] fotograma a fotograma llamando a seek(t)."""
    nav_page.set_content(html, wait_until="load")
    nav_page.wait_for_function("document.fonts.ready.then(() => true)")
    for i in range(n_frames):
        t = i / FPS
        nav_page.evaluate("(t) => window.seek(t)", t)
        nav_page.screenshot(path=str(frames_dir / f"{i:05d}.png"))


def clip_escena(frames_dir, target_dur, destino):
    """Codifica los fotogramas de entrada y clona el último hasta target_dur
    (reposo tras la animación — el movimiento vive solo en la entrada)."""
    n = len(list(frames_dir.glob("*.png")))
    hold = max(0.0, target_dur - n / FPS)
    subprocess.run(
        [FFMPEG, "-y", "-framerate", str(FPS), "-i", str(frames_dir / "%05d.png"),
         "-vf", f"tpad=stop_mode=clone:stop_duration={hold:.3f},format=yuv420p",
         "-r", str(FPS), "-t", f"{target_dur:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", str(destino)],
        check=True, capture_output=True)


def encadenar(clips, duraciones, destino):
    if len(clips) == 1:
        shutil.copy(clips[0], destino)
        return
    entradas = []
    for c in clips:
        entradas += ["-i", str(c)]
    filtros, prev, offset = [], "[0:v]", 0.0
    for i in range(1, len(clips)):
        offset += duraciones[i - 1] - XFADE
        etiqueta = f"[v{i}]"
        filtros.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}{etiqueta}")
        prev = etiqueta
    subprocess.run([FFMPEG, "-y", *entradas, "-filter_complex", ";".join(filtros),
                    "-map", prev, "-c:v", "libx264", "-preset", "medium",
                    "-crf", "18", "-pix_fmt", "yuv420p", str(destino)],
                   check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-musica", action="store_true")
    ap.add_argument("--solo-escenas", action="store_true")
    args = ap.parse_args()

    n_anim = math.ceil(ANIM * FPS) + 1

    if args.solo_escenas:
        d = REPO / "social" / "kit" / "video"
        d.mkdir(parents=True, exist_ok=True)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            for i, esc in enumerate(ESCENAS):
                page.set_content(esc["html"], wait_until="load")
                page.wait_for_function("document.fonts.ready.then(() => true)")
                page.evaluate("(t) => window.seek(t)", ANIM)   # estado final
                page.screenshot(path=str(d / f"escena-{i}.png"))
                print(f"✓ {(d / f'escena-{i}.png').relative_to(REPO)}")
            b.close()
        return

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        print("· Locución (edge-tts)…")
        voz, duraciones, total = sintetizar(tmp)
        print(f"  {total:.1f}s · {len(ESCENAS)} escenas")

        print(f"· Escenas — animación por fotogramas ({n_anim} frames/entrada)…")
        from playwright.sync_api import sync_playwright
        clips = []
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            for i, esc in enumerate(ESCENAS):
                fdir = tmp / f"f{i}"
                fdir.mkdir()
                capturar_escena(page, esc["html"], fdir, n_anim)
                target = duraciones[i] + (XFADE if i < len(ESCENAS) - 1 else 0)
                c = tmp / f"clip{i}.mp4"
                clip_escena(fdir, target, c)
                clips.append(c)
                print(f"  escena {i+1}/{len(ESCENAS)}  {duraciones[i]:.1f}s")
            b.close()

        print("· Montaje + audio…")
        mudo = tmp / "mudo.mp4"
        encadenar(clips, [d + XFADE for d in duraciones], mudo)

        audio = tmp / "audio.wav"
        mezclar(voz, total, audio, con_musica=not args.sin_musica)

        subprocess.run([FFMPEG, "-y", "-i", str(mudo), "-i", str(audio),
                        "-map", "0:v", "-map", "1:a", "-shortest",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                        str(SALIDA)], check=True, capture_output=True)

    mb = SALIDA.stat().st_size / 1024 / 1024
    print(f"\n✓ {SALIDA.relative_to(REPO)}  {W}×{H}  {_dur(SALIDA):.1f}s  ({mb:.1f} MB)")


if __name__ == "__main__":
    main()
