#!/usr/bin/env python3
"""
crear_video_web.py — Vídeo de presentación de oponoticias.com para TikTok.

Toma la grabación de pantalla de la web, selecciona los mejores segmentos
(hero + listado de convocatorias + explora por área), los escala a 1080×1920,
añade narración con edge-tts y overlays de texto sincronizados.

Uso: python3 crear_video_web.py
Requiere: ffmpeg, edge-tts, Pillow
Salida: oponoticias_web.mp4
"""

import asyncio
import subprocess
import tempfile
import os
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO    = Path(__file__).resolve().parent
MOV     = REPO / "videos" / "Grabación de pantalla 2026-06-18 a las 12.38.19.mov"
SALIDA  = REPO / "oponoticias_web.mp4"
FFMPEG  = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

VOZ   = "es-ES-XimenaNeural"
RATE  = "+2%"
FPS   = 30
GAP   = 0.25   # silencio entre frases (s)

W, H      = 1080, 1920
OVERLAY_H = 290

# ── Segmentos de la grabación a usar ─────────────────────────────────────────
# (t_inicio, duracion_seg) — suma = duración del vídeo final antes de CTA
SEGMENTOS = [
    (0.0,  14.0),   # Hero: "Las oposiciones del BOE…" + inicio listado
    (40.0, 20.0),   # "Explora por área" + fichas de categorías
    (88.0, 12.0),   # "Del BOE a tu bolsillo en 3 pasos"
]
# Duración total del fondo = suma de duración de segmentos
DUR_FONDO = sum(d for _, d in SEGMENTOS)   # 46 s

# ── Guión (narración + texto del overlay) ────────────────────────────────────
FRASES = [
    {
        "narr":  "Bienvenido a OpoNoticias: las oposiciones del BOE "
                 "contadas en lenguaje claro.",
        "title": "OPONOTICIAS",
        "sub":   "Las oposiciones del BOE en lenguaje claro",
    },
    {
        "narr":  "Cada día publicamos todas las convocatorias nuevas "
                 "del Boletín Oficial del Estado.",
        "title": "CONVOCATORIAS DEL BOE",
        "sub":   "Actualizadas cada mañana",
    },
    {
        "narr":  "Explora por área: educación, sanidad, administración, "
                 "seguridad y mucho más.",
        "title": "8 ÁREAS TEMÁTICAS",
        "sub":   "Educación · Sanidad · Administración · Seguridad",
    },
    {
        "narr":  "Del BOE a tu bolsillo en tres pasos: leemos, resumimos "
                 "y te lo enviamos sin jerga.",
        "title": "SIMPLE Y AUTOMÁTICO",
        "sub":   "Sin jerga · Sin registro · Gratis",
    },
    {
        "narr":  "Síguenos para no perderte ninguna convocatoria. "
                 "Todo en oponoticias punto com.",
        "title": "¡SÍGUENOS!",
        "sub":   "@OpoNoticias · oponoticias.com",
    },
]

# Paleta
BG_BAR  = (10, 12, 20)
ACCENT  = (122, 139, 110)
WHITE   = (255, 255, 255)

TITLE_SIZE = 52
SUB_SIZE   = 30


# ── Fuentes ──────────────────────────────────────────────────────────────────
def _font(size):
    for p in [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Overlay PNG (barra inferior) ─────────────────────────────────────────────
def crear_overlay(title, sub, out_path):
    img  = Image.new("RGB", (W, OVERLAY_H), BG_BAR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 6], fill=ACCENT)      # franja verde

    ft = _font(TITLE_SIZE)
    fs = _font(SUB_SIZE)

    try:
        th = draw.textbbox((0, 0), title, font=ft)[3]
        sh = draw.textbbox((0, 0), sub,   font=fs)[3]
        tw = draw.textbbox((0, 0), title, font=ft)[2]
        sw = draw.textbbox((0, 0), sub,   font=fs)[2]
    except AttributeError:
        th, sh = TITLE_SIZE, SUB_SIZE
        tw = len(title) * (TITLE_SIZE // 2)
        sw = len(sub) * (SUB_SIZE // 2)

    espacio = 16
    bloque  = th + espacio + sh
    y0      = (OVERLAY_H - bloque) // 2 + 6

    draw.text(((W - tw) // 2, y0),             title, font=ft, fill=WHITE)
    draw.text(((W - sw) // 2, y0 + th + espacio), sub, font=fs, fill=ACCENT)

    img.save(out_path, "PNG")
    return out_path


# ── TTS frase a frase ─────────────────────────────────────────────────────────
async def _edge_tts(texto, destino):
    import edge_tts
    comm = edge_tts.Communicate(texto, VOZ, rate=RATE)
    with open(destino, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def _generar_narr(texto, mp3_out, wav_out):
    asyncio.run(_edge_tts(texto, mp3_out))
    subprocess.run(
        [FFMPEG, "-y", "-i", str(mp3_out), "-ar", "44100", "-ac", "2", str(wav_out)],
        check=True, capture_output=True,
    )


def _dur(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


# ── Audio: narración + mezcla ────────────────────────────────────────────────
def construir_audio(tmp, duracion_video):
    tmp    = Path(tmp)
    segs   = []
    t      = 0.0
    tiempos = []

    print("  🎙️  Generando narración…")
    for i, fr in enumerate(FRASES):
        mp3 = tmp / f"raw{i}.mp3"
        wav = tmp / f"seg{i}.wav"
        _generar_narr(fr["narr"], mp3, wav)
        d = _dur(wav)
        if i > 0:
            sil = tmp / f"sil{i}.wav"
            subprocess.run(
                [FFMPEG, "-y", "-f", "lavfi",
                 "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                 "-t", str(GAP), str(sil)],
                check=True, capture_output=True,
            )
            segs.append(str(sil))
            t += GAP
        tiempos.append((round(t, 3), round(t + d, 3)))
        segs.append(str(wav))
        t += d

    lista = tmp / "segs.txt"
    with open(lista, "w") as f:
        for s in segs:
            f.write(f"file '{s}'\n")
    voz = tmp / "voz.wav"
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
         "-c", "copy", str(voz)],
        check=True, capture_output=True,
    )

    # Mezcla: narración + música (si existe) con ducking
    music_src = REPO / "assets" / "music_bed.mp3"
    dur_audio  = max(_dur(voz) + 0.5, duracion_video)
    norm_expr  = (f"loudnorm=I=-16:TP=-1.5:LRA=11,"
                  f"afade=t=out:st={dur_audio - 0.8:.2f}:d=0.8")
    audio_out  = tmp / "audio.wav"

    if music_src.exists():
        subprocess.run(
            [FFMPEG, "-y",
             "-i", str(voz),
             "-stream_loop", "-1", "-i", str(music_src),
             "-filter_complex",
             "[1:a]volume=1.5[m];"
             "[0:a]volume=1.0,asplit=2[vmix][vkey];"
             "[m][vkey]sidechaincompress=threshold=0.06:ratio=4:attack=20:release=400[mduck];"
             "[vmix][mduck]amix=inputs=2:duration=first:dropout_transition=0[premix];"
             f"[premix]{norm_expr}[a]",
             "-map", "[a]",
             "-t", str(dur_audio), "-ar", "44100", "-ac", "2", str(audio_out)],
            check=True, capture_output=True,
        )
    else:
        subprocess.run(
            [FFMPEG, "-y", "-i", str(voz),
             "-af", norm_expr,
             "-t", str(dur_audio), "-ar", "44100", "-ac", "2", str(audio_out)],
            check=True, capture_output=True,
        )

    return audio_out, tiempos


# ── Fondo: segmentos de la grabación escalados a 1080×1920 ───────────────────
def construir_fondo(tmp):
    """Extrae y concatena los segmentos seleccionados de la grabación."""
    tmp   = Path(tmp)
    clips = []
    print("  🎞️  Preparando segmentos de la grabación…")
    for i, (t_ini, dur) in enumerate(SEGMENTOS):
        clip = tmp / f"seg{i}.mp4"
        print(f"     Segmento {i+1}: {t_ini:.0f}s–{t_ini+dur:.0f}s ({dur:.0f}s)")
        subprocess.run(
            [FFMPEG, "-y",
             "-ss", str(t_ini), "-t", str(dur),
             "-i", str(MOV),
             # Escala a 1080×1920: primero sube a la altura, luego recorta ancho al centro
             "-vf", "scale=-1:1920,crop=1080:1920",
             "-r", str(FPS),
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-an",   # sin audio de la grabación
             str(clip)],
            check=True, capture_output=True,
        )
        clips.append(clip)

    lista = tmp / "fondo_clips.txt"
    with open(lista, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    fondo = tmp / "fondo.mp4"
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         str(fondo)],
        check=True, capture_output=True,
    )
    return fondo


# ── Overlay track ────────────────────────────────────────────────────────────
def construir_overlay_track(tmp, tiempos):
    tmp   = Path(tmp)
    clips = []

    t_inicio = tiempos[0][0]
    if t_inicio > 0.1:
        negro = tmp / "negro_ini.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-f", "lavfi",
             "-i", f"color=c=black:s={W}x{OVERLAY_H}:r={FPS}",
             "-t", str(t_inicio), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             str(negro)],
            check=True, capture_output=True,
        )
        clips.append(negro)

    for i, (fr, (t0, t1)) in enumerate(zip(FRASES, tiempos)):
        print(f"  🖼️   Overlay {i+1}/{len(FRASES)}: {fr['title']}")
        png  = tmp / f"ov{i}.png"
        clip = tmp / f"ovc{i}.mp4"
        crear_overlay(fr["title"], fr["sub"], png)
        dur = t1 - t0
        subprocess.run(
            [FFMPEG, "-y", "-loop", "1", "-framerate", str(FPS),
             "-i", str(png), "-t", str(dur),
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             str(clip)],
            check=True, capture_output=True,
        )
        clips.append(clip)

    # Relleno negro hasta el final del fondo (sin overlay tras la última frase)
    t_fin = tiempos[-1][1]
    cola  = DUR_FONDO - t_fin
    if cola > 0.2:
        negro = tmp / "negro_fin.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-f", "lavfi",
             "-i", f"color=c=black:s={W}x{OVERLAY_H}:r={FPS}",
             "-t", str(cola), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             str(negro)],
            check=True, capture_output=True,
        )
        clips.append(negro)

    lista = tmp / "ov_clips.txt"
    with open(lista, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    overlays = tmp / "overlays.mp4"
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         str(overlays)],
        check=True, capture_output=True,
    )
    return overlays


# ── Composición final ─────────────────────────────────────────────────────────
def componer(fondo, overlays, audio, salida):
    dur = DUR_FONDO
    print("  🎬  Componiendo vídeo final…")
    subprocess.run(
        [FFMPEG, "-y",
         "-i", str(fondo),
         "-i", str(overlays),
         "-i", str(audio),
         "-filter_complex",
         f"[0:v][1:v]overlay=0:{H - OVERLAY_H}[vout]",
         "-map", "[vout]",
         "-map", "2:a",
         "-t", str(dur),
         "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart",
         str(salida)],
        check=True, capture_output=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not MOV.exists():
        print(f"❌ No se encontró: {MOV}")
        return False
    if not shutil.which("ffmpeg"):
        print("❌ ffmpeg no está en PATH")
        return False
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("❌ edge-tts no instalado: pip install edge-tts")
        return False

    print(f"🎬 Fuente  : {MOV.name}")
    print(f"📤 Salida  : {SALIDA.name}")
    print(f"⏱️  Duración: {DUR_FONDO:.0f}s (3 segmentos)\n")

    with tempfile.TemporaryDirectory() as tmp:
        fondo    = construir_fondo(tmp)
        audio, tiempos = construir_audio(tmp, DUR_FONDO)
        print()
        overlays = construir_overlay_track(tmp, tiempos)

        print("\n  ⏱️  Tiempos de escenas:")
        for fr, (t0, t1) in zip(FRASES, tiempos):
            print(f"     [{t0:.1f}s–{t1:.1f}s] {fr['title']}")

        componer(fondo, overlays, audio, SALIDA)

    print(f"\n✅ Vídeo listo: {SALIDA}")
    print("   Sube a TikTok y fíjalo como vídeo de presentación del canal.")
    return True


if __name__ == "__main__":
    main()
