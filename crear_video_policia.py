#!/usr/bin/env python3
"""
crear_video_policia.py — Vídeo vertical (1080×1920) que anuncia la convocatoria
destacada (Policía Nacional · 2.704 plazas). Sirve para TikTok, Reels, Shorts y
stories de cualquier red (formato vertical universal, con zonas seguras).

DELIBERADAMENTE FUERA DEL PIPELINE. Se ejecuta a mano, revisas el MP4 y lo subes
tú. Mismo motor que crear_video_kit.py (función seek(t) + Playwright fotograma a
fotograma), siguiendo la skill motion-design-serio: entrada escalonada, el número
cuenta hasta 2.704 (beat anclado en el dato), easing sin rebote, xfade corto.

  python3 crear_video_policia.py                 # con música
  python3 crear_video_policia.py --sin-musica
  python3 crear_video_policia.py --solo-escenas  # PNG del estado final

Salida: videos/policia-2704.mp4
"""

import argparse
import asyncio
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import crear_promo_kit as g   # CSS_BASE, brand, paleta

REPO = Path(__file__).resolve().parent
SALIDA = REPO / "videos" / "policia-2704.mp4"
MUSICA = REPO / "assets" / "music_bed.mp3"

FFMPEG, FFPROBE = "ffmpeg", "ffprobe"
W, H, FPS = 1080, 1920, 30
VOZ, RATE = "es-ES-XimenaNeural", "+2%"
GAP, TAIL, XFADE = 0.18, 0.9, 0.4
ANIM = 2.6   # ventana de entrada capturada (s); cubre el contador hasta 2.704

# Zonas seguras (TikTok/Reels superponen UI abajo ~330px y a la derecha ~130px).
SEGURO = "padding:170px 140px 330px 82px"

# Runtime seek(t): igual que crear_video_kit pero el contador formatea miles
# (2704 → "2.704") con toLocaleString('es-ES'). Ease = smoothstep (sin rebote).
RUNTIME = r"""
<script>
  function E(p){ p = p<0?0:p>1?1:p; return p*p*(3-2*p); }
  // Separador de miles manual (toLocaleString no agrupa sin locale ICU en headless).
  function miles(n){ return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
  function seek(t){
    document.querySelectorAll('[data-in]').forEach(function(el){
      var s=parseFloat(el.dataset.in), d=parseFloat(el.dataset.dur||'0.55'),
          dist=parseFloat(el.dataset.dist||'26'), e=E((t-s)/d);
      el.style.opacity=e; el.style.transform='translateY('+((1-e)*dist).toFixed(2)+'px)';
    });
    document.querySelectorAll('[data-count]').forEach(function(el){
      var s=parseFloat(el.dataset.cstart), d=parseFloat(el.dataset.cdur||'0.9'),
          to=parseFloat(el.dataset.count), e=E((t-s)/d);
      el.textContent=miles(Math.round(e*to));
    });
  }
  window.seek = seek;
</script>
"""


def _pagina(css_extra, cuerpo, oscuro=False):
    fondo = "background:linear-gradient(160deg,#3A332C,#5A5047 60%,#6E6154)" if oscuro else ""
    css = (g.CSS_BASE
           + f".card{{{SEGURO};justify-content:space-between;{fondo}}}"
           + ".sheet{box-shadow:0 30px 70px rgba(43,38,34,.22)}"
           + "[data-in]{opacity:0}"
           + css_extra)
    return (f"<!DOCTYPE html><html lang=es><head><meta charset=utf-8>"
            f"<style>{css}</style></head><body>"
            f'<div class="card grain">{cuerpo}</div>{RUNTIME}</body></html>')


def _in(t, dist=26, dur=0.55):
    return f'data-in="{t}" data-dist="{dist}" data-dur="{dur}"'


def _badge(dark=False):
    return (f'<span {_in(0.15, dist=16)} style="display:inline-flex;align-items:center;gap:10px;'
            f'background:#B4453A;color:#fff;padding:14px 26px;border-radius:999px;'
            f'font-weight:800;font-size:26px;letter-spacing:.08em;text-transform:uppercase">'
            f'● Nueva convocatoria · BOE</span>')


ESCENAS = [
    {   # 0 · gancho
        "narr": "Ya es oficial en el Boletín Oficial del Estado.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42)}</div>
          <div>{_badge()}
            <h1 {_in(0.5, dist=26)} style="font-size:96px;margin-top:30px">Ya es<br>oficial<br>en el <span class="hl">BOE</span>.</h1>
          </div>
          <div {_in(1.3, dist=16)} style="font-size:34px;color:var(--gray);font-weight:600">
            Convocatoria destacada</div>"""),
    },
    {   # 1 · el número (fondo oscuro para máximo impacto) — cuenta hasta 2.704
        "narr": "Dos mil setecientas cuatro plazas de Policía Nacional.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42, dark=True)}</div>
          <div style="display:flex;flex-direction:column;align-items:flex-start">
            <span {_in(0.3, dist=20)} data-count="2704" data-cstart="0.4" data-cdur="1.3"
                  style="font-family:var(--serif);font-weight:900;font-size:280px;color:#fff;line-height:.9;letter-spacing:-.02em">0</span>
            <span {_in(1.5, dist=18)} style="font-family:var(--serif);font-weight:900;font-size:88px;color:var(--secondary);margin-top:6px">PLAZAS</span>
          </div>
          <div {_in(1.9, dist=18)} style="font-size:48px;color:#fff;font-weight:700">Policía Nacional</div>""", oscuro=True),
    },
    {   # 2 · quién / detalles
        "narr": "Ingreso en la Escala Básica, por oposición libre.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}><div class="eyebrow" style="font-size:26px">La convocatoria</div>
            <h2 {_in(0.2, dist=24)} style="font-size:82px;margin-top:22px">Escala Básica.<br><span class="hl">Oposición libre</span>.</h2></div>
          <div {_in(0.9, dist=22)} style="display:flex;flex-direction:column;gap:20px;font-size:40px;color:var(--primary);font-weight:600">
            <span>👮 Cuerpo Nacional de Policía</span>
            <span>🔢 2.163 libres + 541 militares</span>
            <span>📅 Publicada el 10 de julio</span>
          </div>
          <div {_in(1.7, dist=16)} style="font-size:34px;color:var(--gray);font-weight:600">BOE-A-2026-15055</div>"""),
    },
    {   # 3 · urgencia (el plazo real: 15 días hábiles)
        "narr": "Pero atención: el plazo para solicitarla es de solo quince días hábiles.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}><div class="eyebrow" style="font-size:26px">No lo dejes pasar</div>
            <h2 {_in(0.2, dist=26)} style="font-size:92px;margin-top:22px">Plazo:<br><span style="color:#B4453A">solo 15 días</span><br>hábiles.</h2></div>
          <div {_in(1.0, dist=20)} style="font-size:38px;color:var(--primary);font-weight:600;line-height:1.45">
            Desde el día siguiente a su<br>publicación en el BOE.</div>
          <div></div>"""),
    },
    {   # 4 · cierre / CTA
        "narr": "Tienes el resumen completo y el enlace al BOE en oponoticias punto com.",
        "html": _pagina("", f"""
          <div {_in(0.0, dist=18)}>{g.brand(42, dark=True)}</div>
          <div>
            <h1 {_in(0.35, dist=26)} style="font-size:104px;color:#fff">Toda la<br>info aquí.</h1>
            <p {_in(0.8, dist=20)} style="font-size:40px;color:rgba(255,255,255,.82);margin-top:30px;font-weight:600">
              Resumen, requisitos y enlace<br>directo al BOE oficial.</p>
          </div>
          <div {_in(1.3, dist=22)} style="display:flex;flex-direction:column;gap:22px">
            <span style="background:var(--secondary);color:#2B2622;padding:30px 0;border-radius:18px;
                         font-weight:800;font-size:46px;text-align:center">oponoticias.com</span>
            <span style="color:rgba(255,255,255,.68);font-size:32px;text-align:center;font-weight:700">
              Y cada mañana, gratis, en Telegram</span>
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
        d = REPO / "social" / "policia" / "video"
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
