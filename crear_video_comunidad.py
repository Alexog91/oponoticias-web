#!/usr/bin/env python3
"""
crear_video_comunidad.py — Vídeo vertical (1080×1920) que anuncia los dos
espacios nuevos de Telegram: OpoNoticias Chat (comentarios) y OpoNoticias
Comunidad (temas). Sirve para TikTok, Reels, Shorts y stories (formato
vertical universal, con zonas seguras).

DELIBERADAMENTE FUERA DEL PIPELINE. Se ejecuta a mano, revisas el MP4 y lo
subes tú. Mismo motor que crear_video_policia.py (función seek(t) + Playwright
fotograma a fotograma), siguiendo la skill motion-design-serio: entrada
escalonada, easing sin rebote, xfade corto.

  python3 crear_video_comunidad.py                 # con música
  python3 crear_video_comunidad.py --sin-musica
  python3 crear_video_comunidad.py --solo-escenas   # PNG del estado final

Salida: videos/comunidad.mp4
"""

import argparse
import asyncio
import base64
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import crear_promo_kit as g   # CSS_BASE, brand, paleta

REPO = Path(__file__).resolve().parent
SALIDA = REPO / "videos" / "comunidad.mp4"
MUSICA = REPO / "assets" / "music_bed.mp3"
GRUPOS = REPO / "social" / "grupos"

FFMPEG, FFPROBE = "ffmpeg", "ffprobe"
W, H, FPS = 1080, 1920, 30
VOZ, RATE = "es-ES-XimenaNeural", "+2%"
GAP, TAIL, XFADE = 0.18, 0.9, 0.4
ANIM = 1.6   # ventana de entrada capturada (s)

# Zonas seguras (TikTok/Reels superponen UI abajo ~330px y a la derecha ~130px).
SEGURO = "padding:170px 140px 330px 82px"


def _data_uri(png_path):
    return "data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode()


ICONO_CHAT = _data_uri(GRUPOS / "icono-chat.png")
ICONO_COMUNIDAD = _data_uri(GRUPOS / "icono-comunidad.png")

# Runtime seek(t): igual que crear_video_policia (solo entradas escalonadas,
# aquí no hace falta contador).
RUNTIME = """
<script>
  function E(p){ p = p<0?0:p>1?1:p; return p*p*(3-2*p); }
  function seek(t){
    document.querySelectorAll('[data-in]').forEach(function(el){
      var s=parseFloat(el.dataset.in), d=parseFloat(el.dataset.dur||'0.55'),
          dist=parseFloat(el.dataset.dist||'26'), e=E((t-s)/d);
      el.style.opacity=e; el.style.transform='translateY('+((1-e)*dist).toFixed(2)+'px)';
    });
  }
  window.seek = seek;
</script>
"""


def _pagina(css_extra, cuerpo, oscuro=False):
    fondo = "background:linear-gradient(160deg,#3A332C,#5A5047 60%,#6E6154)" if oscuro else ""
    css = (g.CSS_BASE
           + f".card{{{SEGURO};justify-content:space-between;{fondo}}}"
           + "[data-in]{opacity:0}"
           + css_extra)
    return (f"<!DOCTYPE html><html lang=es><head><meta charset=utf-8>"
            f"<style>{css}</style></head><body>"
            f'<div class="card grain">{cuerpo}</div>{RUNTIME}</body></html>')


def _in(t, dist=26, dur=0.55):
    return f'data-in="{t}" data-dist="{dist}" data-dur="{dur}"'


def _avatar(src, size, t):
    return (f'<img {_in(t, dist=20)} src="{src}" style="width:{size}px;height:{size}px;'
            f'border-radius:50%;box-shadow:0 20px 50px rgba(43,38,34,.28)">')


ESCENAS = [
    {   # 0 · gancho
        "narr": "Ahora puedes hablar con otros opositores directamente en Telegram.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42)}</div>
          <div>
            <div {_in(0.15, dist=16)} class="eyebrow" style="font-size:26px">Nuevo en Telegram</div>
            <h1 {_in(0.35, dist=26)} style="font-size:96px;margin-top:22px">Habla con<br>otros <span class="hl">opositores</span>.</h1>
          </div>
          <div {_in(1.1, dist=16)} style="font-size:34px;color:var(--gray);font-weight:600">
            Dos espacios pensados para ti</div>"""),
    },
    {   # 1 · Chat
        "narr": "OpoNoticias Chat es donde ya se comenta cada convocatoria, todo en un mismo sitio.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42)}</div>
          <div style="display:flex;flex-direction:column;align-items:flex-start;gap:26px">
            {_avatar(ICONO_CHAT, 150, 0.2)}
            <h2 {_in(0.5, dist=24)} style="font-size:78px">OpoNoticias<br>Chat</h2>
            <p {_in(1.0, dist=20)} style="font-size:36px;color:var(--primary);font-weight:600;line-height:1.4">
              Los comentarios de cada<br>convocatoria, en un único sitio.</p>
          </div>
          <div {_in(1.3, dist=16)} style="font-size:32px;color:var(--gray);font-weight:600">💬 Comenta al vuelo</div>"""),
    },
    {   # 2 · Comunidad
        "narr": "Y OpoNoticias Comunidad es el grupo para hablar con calma: dudas y conversación, organizadas por temas.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42)}</div>
          <div style="display:flex;flex-direction:column;align-items:flex-start;gap:26px">
            {_avatar(ICONO_COMUNIDAD, 150, 0.2)}
            <h2 {_in(0.5, dist=24)} style="font-size:78px">OpoNoticias<br>Comunidad</h2>
            <p {_in(1.0, dist=20)} style="font-size:36px;color:var(--primary);font-weight:600;line-height:1.4">
              Dudas y conversación con otros<br>opositores, organizadas por temas.</p>
          </div>
          <div {_in(1.3, dist=16)} style="font-size:32px;color:var(--gray);font-weight:600">🗣️ Habla con calma</div>"""),
    },
    {   # 3 · recap (fondo oscuro, resume la diferencia)
        "narr": "Comenta en el Chat. Habla con calma en la Comunidad. O entra en los dos.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42, dark=True)}</div>
          <div style="display:flex;flex-direction:column;gap:34px">
            <div {_in(0.25, dist=22)} style="display:flex;align-items:center;gap:20px;font-size:40px;color:#fff;font-weight:700">
              <img src="{ICONO_CHAT}" style="width:64px;height:64px;border-radius:50%"> Comenta → Chat</div>
            <div {_in(0.75, dist=22)} style="display:flex;align-items:center;gap:20px;font-size:40px;color:#fff;font-weight:700">
              <img src="{ICONO_COMUNIDAD}" style="width:64px;height:64px;border-radius:50%"> Habla con calma → Comunidad</div>
          </div>
          <div {_in(1.3, dist=18)} style="font-size:38px;color:var(--secondary);font-weight:800">O entra en los dos 🙌</div>""", oscuro=True),
    },
    {   # 4 · cierre / CTA
        "narr": "Entra gratis, tienes el enlace en la bio.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42, dark=True)}</div>
          <div>
            <h1 {_in(0.35, dist=26)} style="font-size:104px;color:#fff">Entra<br>gratis.</h1>
            <p {_in(0.8, dist=20)} style="font-size:40px;color:rgba(255,255,255,.82);margin-top:30px;font-weight:600">
              Comentarios, dudas y<br>conversación con opositores.</p>
          </div>
          <div {_in(1.3, dist=22)} style="display:flex;flex-direction:column;gap:22px">
            <span style="background:var(--secondary);color:#2B2622;padding:30px 0;border-radius:18px;
                         font-weight:800;font-size:46px;text-align:center">Link en la bio</span>
            <span style="color:rgba(255,255,255,.68);font-size:32px;text-align:center;font-weight:700">
              OpoNoticias Chat · OpoNoticias Comunidad</span>
          </div>""", oscuro=True),
    },
]


# ── Audio ───────────────────────────────────────────────────────────────────────
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
    piezas, duraciones = [], []
    for i, esc in enumerate(ESCENAS):
        mp3, wav = tmp / f"raw{i}.mp3", tmp / f"seg{i}.wav"
        asyncio.run(_tts(esc["narr"], mp3))
        subprocess.run([FFMPEG, "-y", "-i", str(mp3), "-ar", "44100", "-ac", "2", str(wav)],
                       check=True, capture_output=True)
        duraciones.append(_dur(wav) + GAP + (TAIL if i == len(ESCENAS) - 1 else 0))
        piezas.append(wav)
    partes = []
    for i, wav in enumerate(piezas):
        partes.append(wav)
        sil = tmp / f"sil{i}.wav"
        d = GAP + (TAIL if i == len(piezas) - 1 else 0)
        subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-t", f"{d:.3f}", str(sil)], check=True, capture_output=True)
        partes.append(sil)
    lista = tmp / "voz.txt"
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


# ── Vídeo ─────────────────────────────────────────────────────────────────────
def capturar_escena(page, html, frames_dir, n_frames):
    page.set_content(html, wait_until="load")
    page.wait_for_function("document.fonts.ready.then(() => true)")
    for i in range(n_frames):
        page.evaluate("(t) => window.seek(t)", i / FPS)
        page.screenshot(path=str(frames_dir / f"{i:05d}.png"))


def clip_escena(frames_dir, target_dur, destino):
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
        shutil.copy(clips[0], destino); return
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
    from playwright.sync_api import sync_playwright

    if args.solo_escenas:
        d = REPO / "social" / "comunidad" / "video"
        d.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            for i, esc in enumerate(ESCENAS):
                page.set_content(esc["html"], wait_until="load")
                page.wait_for_function("document.fonts.ready.then(() => true)")
                page.evaluate("(t) => window.seek(t)", ANIM)
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
        clips = []
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            for i, esc in enumerate(ESCENAS):
                fdir = tmp / f"f{i}"; fdir.mkdir()
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
