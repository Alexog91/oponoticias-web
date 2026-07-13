#!/usr/bin/env python3
"""
crear_video_intro.py — Genera el vídeo de presentación del canal OpoNoticias
para TikTok a partir de la grabación de pantalla de la web.

Narración con edge-tts · Overlays con Pillow · Composición con ffmpeg.
Salida: oponoticias_intro.mp4 (1080×1920, H.264, AAC).

Uso: python3 crear_video_intro.py
"""

import asyncio
import subprocess
import tempfile
import os
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO    = Path(__file__).resolve().parent
VIDEO   = Path.home() / "Downloads" / "oponoticias_video_demo.mp4"
SALIDA  = REPO / "oponoticias_intro.mp4"
FFMPEG  = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

VOZ   = "es-ES-XimenaNeural"
RATE  = "+2%"
FPS   = 30
GAP   = 0.25   # silencio entre frases (s)

W, H        = 1080, 1920     # dimensiones del vídeo
OVERLAY_H   = 290            # altura del bar inferior
CORNER_PAD  = 40             # padding lateral en el bar

# ── Paleta ─────────────────────────────────────────────────────────────────────
BG_BAR     = (10, 12, 20)        # fondo barra (RGB sólido oscuro)
ACCENT     = (122, 139, 110)     # #7A8B6E verde marca
WHITE      = (255, 255, 255)
TITLE_SIZE = 52
SUB_SIZE   = 30

# ── Guión ──────────────────────────────────────────────────────────────────────
FRASES = [
    {
        "narr":  "Bienvenido a OpoNoticias, tu canal de oposiciones.",
        "title": "BIENVENIDO",
        "sub":   "Tu canal de oposiciones",
    },
    {
        "narr":  "Cada día publicamos todas las convocatorias nuevas del BOE, "
                 "organizadas por sector.",
        "title": "CONVOCATORIAS DEL BOE",
        "sub":   "Actualizadas cada día",
    },
    {
        "narr":  "Sanidad, educación, administración, seguridad y mucho más.",
        "title": "SANIDAD · EDUCACIÓN",
        "sub":   "Administración · Seguridad · Y más",
    },
    {
        "narr":  "Y también artículos y guías para preparar tu oposición.",
        "title": "ARTÍCULOS Y GUÍAS",
        "sub":   "Todo lo que necesitas para opositar",
    },
    {
        "narr":  "Síguenos para no perderte ninguna convocatoria. Gratis. Cada día.",
        "title": "¡SÍGUENOS!",
        "sub":   "@OpoNoticias · oponoticias.com",
    },
]


# ── Fuentes ─────────────────────────────────────────────────────────────────────
def _font(size):
    candidates = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Generación de overlays (PNGs) ──────────────────────────────────────────────
def crear_overlay(title, sub, out_path):
    """Genera un PNG 1080×OVERLAY_H con el texto de la escena."""
    img  = Image.new("RGB", (W, OVERLAY_H), BG_BAR)
    draw = ImageDraw.Draw(img)

    # Franja de acento en la parte superior del bar
    draw.rectangle([0, 0, W, 6], fill=ACCENT)

    ft = _font(TITLE_SIZE)
    fs = _font(SUB_SIZE)

    # Altura del bloque de texto para centrarlo verticalmente
    try:
        th = draw.textbbox((0, 0), title, font=ft)[3]
        sh = draw.textbbox((0, 0), sub,   font=fs)[3]
    except AttributeError:
        th, sh = TITLE_SIZE, SUB_SIZE
    espacio   = 16
    bloque    = th + espacio + sh
    y_title   = (OVERLAY_H - bloque) // 2 + 6

    # Título centrado
    try:
        tw = draw.textbbox((0, 0), title, font=ft)[2]
    except AttributeError:
        tw = len(title) * (TITLE_SIZE // 2)
    draw.text(((W - tw) // 2, y_title), title, font=ft, fill=WHITE)

    # Subtítulo centrado
    try:
        sw = draw.textbbox((0, 0), sub, font=fs)[2]
    except AttributeError:
        sw = len(sub) * (SUB_SIZE // 2)
    draw.text(((W - sw) // 2, y_title + th + espacio), sub, font=fs, fill=ACCENT)

    img.save(out_path, "PNG")
    return out_path


# ── TTS frase a frase ──────────────────────────────────────────────────────────
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


# ── Audio: narración + música ─────────────────────────────────────────────────
def construir_audio(tmp, duracion_video):
    """Genera voz segmentada, mide tiempos y mezcla con música. Devuelve (wav, tiempos)."""
    tmp  = Path(tmp)
    segs = []
    t    = 0.0
    tiempos = []

    print("  🎙️  Generando narración…")
    for i, fr in enumerate(FRASES):
        mp3 = tmp / f"raw{i}.mp3"
        wav = tmp / f"seg{i}.wav"
        _generar_narr(fr["narr"], mp3, wav)
        d = _dur(wav)
        if i > 0:
            # silencio entre frases
            sil = tmp / f"sil{i}.wav"
            subprocess.run(
                [FFMPEG, "-y", "-f", "lavfi",
                 "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                 "-t", str(GAP), str(sil)],
                check=True, capture_output=True,
            )
            segs.append(str(sil))
            t += GAP
        tiempos.append((round(t, 3), round(t + d, 3)))
        segs.append(str(wav))
        t += d

    # Concatenar narración
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

    # Música de fondo (si existe assets/music_bed.mp3)
    music_src = REPO / "assets" / "music_bed.mp3"
    dur_audio  = max(_dur(voz) + 0.5, duracion_video)
    norm_expr  = f"loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=out:st={dur_audio - 0.8:.2f}:d=0.8"
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


# ── Overlay: un clip por escena, concatenados ─────────────────────────────────
def construir_overlay_track(tmp, tiempos, duracion_video):
    """Genera un vídeo 1080×OVERLAY_H que muestra los textos en sus tiempos."""
    tmp   = Path(tmp)
    clips = []

    # Posible breve silencio al inicio antes de que empiece la primera frase
    t_inicio = tiempos[0][0]
    if t_inicio > 0.1:
        negro = tmp / "negro_inicio.mp4"
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
        png = tmp / f"ov{i}.png"
        crear_overlay(fr["title"], fr["sub"], png)
        clip = tmp / f"clip{i}.mp4"
        dur  = t1 - t0
        subprocess.run(
            [FFMPEG, "-y", "-loop", "1", "-framerate", str(FPS),
             "-i", str(png), "-t", str(dur),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
             str(clip)],
            check=True, capture_output=True,
        )
        clips.append(clip)

    # Silencio tras la última frase (video sigue sin overlay)
    t_fin = tiempos[-1][1]
    cola = duracion_video - t_fin
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

    lista = tmp / "overlay_clips.txt"
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


# ── Composición final ──────────────────────────────────────────────────────────
def componer(video, overlays, audio, salida, duracion_video):
    """Combina vídeo principal + overlay inferior + audio → MP4 final."""
    print("  🎬  Componiendo vídeo final…")
    # overlay=0:H-OVERLAY_H coloca el bar en la parte inferior del frame
    subprocess.run(
        [FFMPEG, "-y",
         "-i", str(video),        # 0: vídeo original
         "-i", str(overlays),     # 1: overlay track (1080×OVERLAY_H)
         "-i", str(audio),        # 2: audio mezcla
         "-filter_complex",
         f"[0:v][1:v]overlay=0:{H - OVERLAY_H}[vout]",
         "-map", "[vout]",
         "-map", "2:a",
         "-t", str(duracion_video),
         "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart",
         str(salida)],
        check=True, capture_output=True,
    )


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if not VIDEO.exists():
        print(f"❌ No se encontró el vídeo: {VIDEO}")
        return False
    if not shutil.which("ffmpeg"):
        print("❌ ffmpeg no está en PATH")
        return False
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("❌ edge-tts no instalado: pip install edge-tts")
        return False

    print(f"🎬 Vídeo fuente : {VIDEO}")
    print(f"📤 Salida       : {SALIDA}")
    duracion_video = _dur(VIDEO)
    print(f"⏱️  Duración     : {duracion_video:.1f}s\n")

    with tempfile.TemporaryDirectory() as tmp:
        audio, tiempos = construir_audio(tmp, duracion_video)
        overlays = construir_overlay_track(tmp, tiempos, duracion_video)

        print("\n  ⏱️  Tiempos de escenas:")
        for fr, (t0, t1) in zip(FRASES, tiempos):
            print(f"     [{t0:.1f}s–{t1:.1f}s] {fr['title']}")

        componer(VIDEO, overlays, audio, SALIDA, duracion_video)

    print(f"\n✅ Vídeo intro listo: {SALIDA}")
    print(f"   Sube a TikTok y fíjalo en el perfil como vídeo de presentación.")
    return True


if __name__ == "__main__":
    main()
