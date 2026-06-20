#!/usr/bin/env python3
"""
generar_video_diario.py — Genera un vídeo vertical (1080×1920) para TikTok,
Instagram Reels y Facebook Reels con las convocatorias destacadas del día.

Pipeline 100 % automatizable (corre en GitHub Actions, sin navegador):
  1. Construye un guión corto a partir de las convocatorias con más plazas.
  2. Sintetiza voz neural en español con edge-tts, línea a línea, midiendo la
     duración real de cada frase para sincronizar los subtítulos con precisión.
  3. Renderiza un fondo de marca con Pillow (degradado + logo + footer).
  4. Genera subtítulos ASS estilados (grandes, centrados, número en dorado).
  5. Monta el vídeo con ffmpeg: fondo con leve zoom (Ken Burns), subtítulos
     incrustados y la voz (con cama de música opcional si existe assets/).
  6. Sube el MP4 a Supabase Storage y devuelve la URL pública.

Diseñado para ser best-effort: cualquier fallo se reporta y devuelve None sin
romper el flujo principal de leer_boe.py.
"""

import os
import re
import json
import asyncio
import tempfile
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime

# ── Configuración ──────────────────────────────────────────────────────────────
FFMPEG  = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")
VOZ     = os.environ.get("VIDEO_VOZ", "es-ES-AlvaroNeural")
RATE    = os.environ.get("VIDEO_RATE", "+2%")
PITCH   = os.environ.get("VIDEO_PITCH", "+0Hz")

SUPABASE_URL    = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
STORAGE_BUCKET  = os.environ.get("SUPABASE_STORAGE_BUCKET", "social")
VIDEO_WEBHOOK_URL = os.environ.get("VIDEO_WEBHOOK_URL", "")  # Make.com → TikTok/IG/FB Reels

W, H = 1080, 1920
GAP  = 0.16   # silencio entre frases (s) — ritmo ágil para TikTok
TAIL = 0.4    # cola final (s)

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _num_es(n, fem=True):
    """Convierte un número a palabras en español (femenino para 'plazas') para
    que la voz lo lea con naturalidad. Si num2words no está, devuelve el dígito."""
    try:
        from num2words import num2words
        w = num2words(int(n), lang="es")
    except Exception:
        return str(n)
    if fem:
        w = w.replace("quinientos", "quinientas")    # 500 (irregular)
        w = w.replace("cientos", "cientas")          # doscientos → doscientas, etc.
        w = re.sub(r"\bveintiuno\b", "veintiuna", w)
        w = re.sub(r"\buno\b", "una", w)             # uno → una
        w = re.sub(r"uno$", "una", w)                # treinta y uno → ... una
    return w

# Paleta de marca (RGB)
INK   = (43, 38, 34)
WARM  = (90, 80, 71)
GOLD  = (196, 165, 116)
CREAM = (248, 246, 242)
WHITE = (255, 255, 255)


# ── Fuentes (resuelve según el entorno: Mac local, CI Ubuntu) ──────────────────
def _resolver_fuentes():
    """Devuelve (ruta_pillow_bold, ruta_pillow_black, familia_ass, dir_fuentes)."""
    candidatos = [
        # (bold, black/heavy, familia ass) — en orden de preferencia por entorno.
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial Black.ttf", "Arial"),                # Mac local
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVu Sans"),        # CI Ubuntu (bold real)
        (str(Path.home() / ".fonts/Inter.ttf"),
         str(Path.home() / ".fonts/Inter.ttf"), "Inter"),                               # respaldo
    ]
    for bold, black, fam in candidatos:
        if Path(bold).exists():
            return bold, black if Path(black).exists() else bold, fam, str(Path(bold).parent)
    # Último recurso: que Pillow use su fuente por defecto
    return None, None, "sans-serif", "."


# ── 1) Guión ───────────────────────────────────────────────────────────────────
def _datos(conv):
    partes = [p.strip() for p in (conv.get("resumen_ia") or "").split(" - ")]
    plazas = partes[0] if partes and partes[0] else ""
    puesto = partes[1] if len(partes) > 1 and partes[1] else "Convocatoria"
    lugar  = conv.get("comunidad_autonoma") or (partes[2] if len(partes) > 2 else "España")
    return plazas, puesto, lugar or "España"


def _plazas_num(conv):
    m = re.search(r"\d+", (conv.get("resumen_ia") or "").split(" - ")[0])
    return int(m.group()) if m else 0


def construir_guion(convocatorias, max_items=4):
    """Devuelve [(caption, narracion), ...] listo para sintetizar."""
    hoy = datetime.now()
    # Dedup por (puesto, lugar) y ordenar por plazas desc
    vistas, sel = set(), []
    for conv in sorted(convocatorias, key=_plazas_num, reverse=True):
        plazas, puesto, lugar = _datos(conv)
        clave = (puesto.lower(), lugar.lower())
        if clave in vistas:
            continue
        vistas.add(clave)
        sel.append((plazas, puesto, lugar))
        if len(sel) == max_items:
            break

    n = len(convocatorias)
    lineas = []
    # Hook (los primeros 2 segundos deciden la retención)
    lineas.append((
        f"HOY en el BOE\n{n} oposiciones nuevas",
        f"¡Atención, opositores! Hoy el BOE trae {_num_es(n)} convocatorias nuevas. "
        f"Estas son las que más plazas ofrecen.",
    ))
    # Cuerpo
    for plazas, puesto, lugar in sel:
        m = re.search(r"\d+", plazas)
        num_txt = m.group() if m else ""
        cap = f"{num_txt} plazas\n{puesto}\n{lugar}" if num_txt else f"{puesto}\n{lugar}"
        # Narración con números en palabras y pausas naturales
        narr = (f"{_num_es(num_txt)} plazas de {puesto}, en {lugar}." if num_txt
                else f"{puesto}, en {lugar}.")
        lineas.append((cap, narr))
    # CTA
    lineas.append((
        "Síguenos y no te\npierdas ninguna\noponoticias.com",
        "Síguenos para no perderte ninguna. Todo en oponoticias punto com.",
    ))
    return lineas


# ── 2) Voz (línea a línea, con tiempos exactos) ────────────────────────────────
async def _tts_a_mp3(texto, destino):
    import edge_tts
    comm = edge_tts.Communicate(texto, VOZ, rate=RATE, pitch=PITCH)
    with open(destino, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def _dur(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def sintetizar(lineas, tmp):
    """Genera la voz completa y la línea de tiempos de los subtítulos.

    Devuelve (voice_wav, [(start, end, caption), ...], total)."""
    tmp = Path(tmp)
    segmentos_wav, tiempos = [], []
    t = 0.0
    for i, (caption, narr) in enumerate(lineas):
        mp3 = tmp / f"seg{i}.mp3"
        asyncio.run(_tts_a_mp3(narr, mp3))
        wav = tmp / f"seg{i}.wav"
        subprocess.run(
            [FFMPEG, "-y", "-i", str(mp3), "-ar", "44100", "-ac", "2", str(wav)],
            check=True, capture_output=True,
        )
        d = _dur(wav)
        if i > 0:
            t += GAP
            segmentos_wav.append(("sil", GAP))
        inicio = t
        t += d
        tiempos.append((inicio, t, caption))
        segmentos_wav.append((str(wav), d))

    # Silencio reutilizable
    sil = tmp / "sil.wav"
    subprocess.run(
        [FFMPEG, "-y", "-f", "lavfi", "-i",
         f"anullsrc=channel_layout=stereo:sample_rate=44100",
         "-t", str(GAP), str(sil)],
        check=True, capture_output=True,
    )

    # Lista de concatenación
    lista = tmp / "concat.txt"
    with open(lista, "w") as f:
        for item, _d in segmentos_wav:
            ruta = str(sil) if item == "sil" else item
            f.write(f"file '{ruta}'\n")

    voice = tmp / "voice.wav"
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
         "-c", "copy", str(voice)],
        check=True, capture_output=True,
    )
    return voice, tiempos, t + TAIL


# ── 3) Fondo de marca ──────────────────────────────────────────────────────────
def crear_fondo(destino):
    from PIL import Image, ImageDraw, ImageFont
    bold, black, _fam, _dir = _resolver_fuentes()

    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    # Degradado vertical INK → WARM → INK oscuro
    for y in range(H):
        ty = y / H
        if ty < 0.5:
            t = ty / 0.5
            c = tuple(int(INK[i] * (1 - t) + WARM[i] * t) for i in range(3))
        else:
            t = (ty - 0.5) / 0.5
            c = tuple(int(WARM[i] * (1 - t) + (24, 20, 17)[i] * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)

    def F(size, heavy=False):
        ruta = black if heavy else bold
        try:
            return ImageFont.truetype(ruta, size) if ruta else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    def centrado(text, y, fnt, color):
        bx = d.textbbox((0, 0), text, font=fnt)
        d.text(((W - (bx[2] - bx[0])) // 2, y), text, font=fnt, fill=color)

    centrado("OPONOTICIAS", 120, F(58, heavy=True), CREAM)
    # Línea dorada bajo el logo
    d.rectangle([(W // 2 - 90, 200), (W // 2 + 90, 206)], fill=GOLD)
    centrado("oponoticias.com", H - 160, F(40), GOLD)
    img.save(destino)


# ── 4) Subtítulos como PNG transparentes (portable, sin libass) ────────────────
def _color_linea(linea):
    """Número o dominio → dorado; el resto → blanco."""
    if re.match(r"^\s*\d", linea) or linea.strip().lower() == "oponoticias.com":
        return GOLD
    return WHITE


def crear_overlays(tiempos, tmp):
    """Renderiza un PNG transparente por caption. Devuelve [(png, start, end)]."""
    from PIL import Image, ImageDraw, ImageFont
    _bold, black, _fam, _dir = _resolver_fuentes()
    tmp = Path(tmp)
    margen = 90
    overlays = []

    for i, (inicio, fin, caption) in enumerate(tiempos):
        lineas = caption.split("\n")

        # Auto-ajuste del tamaño de fuente para que la línea más ancha entre
        def fuente(sz):
            try:
                return ImageFont.truetype(black, sz) if black else ImageFont.load_default()
            except Exception:
                return ImageFont.load_default()

        size = 104
        scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        while size > 54:
            f = fuente(size)
            ancho_max = max(scratch.textlength(l, font=f) for l in lineas)
            if ancho_max <= W - 2 * margen:
                break
            size -= 4
        f = fuente(size)
        gap = int(size * 0.28)

        # Altura total del bloque
        alturas = []
        for l in lineas:
            bx = scratch.textbbox((0, 0), l, font=f)
            alturas.append(bx[3] - bx[1])
        total_h = sum(alturas) + gap * (len(lineas) - 1)

        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        y = (H - total_h) // 2
        for l, h in zip(lineas, alturas):
            bx = scratch.textbbox((0, 0), l, font=f)
            x = (W - (bx[2] - bx[0])) // 2 - bx[0]
            d.text((x, y - bx[1]), l, font=f, fill=_color_linea(l),
                   stroke_width=max(4, size // 22), stroke_fill=(15, 12, 10, 235))
            y += h + gap

        png = tmp / f"ov{i}.png"
        img.save(png)
        overlays.append((str(png), inicio, fin))
    return overlays


# ── 5) Montaje ─────────────────────────────────────────────────────────────────
def _music_bed():
    for nombre in ("assets/music_bed.mp3", "assets/music_bed.m4a", "assets/music_bed.wav"):
        if Path(nombre).exists():
            return nombre
    return None


def _generar_musica(tmp, destino):
    """Sintetiza una cama musical en bucle si no hay pista propia en assets/.
    Progresión de 4 acordes (Do–Sol–Lam–Fa) tipo pad ambiental cálido, con
    crossfade entre acordes, reverb y leve tremolo. Suena a música (no a un
    zumbido). El bucle lo repite ffmpeg en el montaje. Devuelve ruta o None."""
    tmp = Path(tmp)
    D = 4.0  # duración por acorde
    # Triadas en registro grave-medio para sentarse bajo la voz (Hz)
    acordes = [
        (130.81, 164.81, 196.00),   # Do mayor  (C E G)
        (98.00, 123.47, 146.83),    # Sol mayor (G B D)
        (110.00, 130.81, 164.81),   # La menor  (A C E)
        (87.31, 110.00, 130.81),    # Fa mayor  (F A C)
    ]
    try:
        chord_files = []
        for i, (f1, f2, f3) in enumerate(acordes):
            cf = tmp / f"chord{i}.wav"
            subprocess.run([
                FFMPEG, "-y",
                "-f", "lavfi", "-i", f"sine=f={f1}:d={D}",
                "-f", "lavfi", "-i", f"sine=f={f2}:d={D}",
                "-f", "lavfi", "-i", f"sine=f={f3}:d={D}",
                "-filter_complex",
                "[0][1][2]amix=inputs=3:normalize=1,lowpass=f=950,volume=2.0[a]",
                "-map", "[a]", str(cf),
            ], check=True, capture_output=True)
            chord_files.append(cf)

        # Encadena con crossfade y añade reverb + tremolo + fundidos del bucle
        prog = 4 * D - 3 * 1.0  # 13 s
        fade_out = prog - 1.0
        cadena = (
            "[0][1]acrossfade=d=1[x1];[x1][2]acrossfade=d=1[x2];"
            "[x2][3]acrossfade=d=1[x3];"
            "[x3]aecho=0.8:0.7:70:0.3,tremolo=f=0.2:d=0.25,"
            f"highpass=f=70,afade=t=in:d=1,afade=t=out:st={fade_out:.2f}:d=1,"
            "volume=1.3[a]"
        )
        cmd = [FFMPEG, "-y"]
        for cf in chord_files:
            cmd += ["-i", str(cf)]
        cmd += ["-filter_complex", cadena, "-map", "[a]", str(destino)]
        subprocess.run(cmd, check=True, capture_output=True)
        return str(destino)
    except subprocess.CalledProcessError:
        return None


def montar(fondo, voice, overlays, total, salida, musica=None):
    """Fondo con leve Ken Burns + overlays PNG temporizados (con fundido) + voz
    (+ cama de música opcional). Solo filtros básicos de ffmpeg (sin libass)."""
    total_frames = int(total * 30) + 2
    fade = 0.2

    cmd = [FFMPEG, "-y", "-loop", "1", "-i", str(fondo), "-i", str(voice)]
    for png, _s, _e in overlays:
        cmd += ["-loop", "1", "-i", str(png)]
    if musica:
        cmd += ["-stream_loop", "-1", "-i", str(musica)]

    # Cadena de vídeo
    zoom = (f"[0:v]zoompan=z='min(zoom+0.0006,1.08)':d={total_frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30[bg]")
    partes = [zoom]
    prev = "bg"
    base_idx = 2  # 0=fondo, 1=voz, overlays empiezan en 2
    for k, (_png, inicio, fin) in enumerate(overlays):
        idx = base_idx + k
        fout = max(0.0, fin - fade)
        partes.append(
            f"[{idx}:v]format=yuva420p,"
            f"fade=t=in:st={inicio:.2f}:d={fade}:alpha=1,"
            f"fade=t=out:st={fout:.2f}:d={fade}:alpha=1[ov{k}]"
        )
        sig = f"v{k}"
        partes.append(
            f"[{prev}][ov{k}]overlay=0:0:enable='between(t,{inicio:.2f},{fin:.2f})'[{sig}]"
        )
        prev = sig
    partes.append(f"[{prev}]format=yuv420p[vout]")

    # Cadena de audio: música de fondo con DUCKING (sidechain) — suena clara en
    # las pausas y baja automáticamente bajo la voz. Cierre con loudnorm a
    # -16 LUFS (estándar de redes) para volumen alto y consistente cada día.
    norm = "loudnorm=I=-16:TP=-1.5:LRA=11"
    if musica:
        mus_idx = base_idx + len(overlays)
        partes.append(
            f"[{mus_idx}:a]volume=1.6[m];"
            f"[1:a]volume=1.0,asplit=2[vmix][vkey];"
            f"[m][vkey]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[mduck];"
            f"[vmix][mduck]amix=inputs=2:duration=longest:dropout_transition=0[premix];"
            f"[premix]{norm}[aout]"
        )
    else:
        partes.append(f"[1:a]{norm}[aout]")
    amap = "[aout]"

    cmd += ["-filter_complex", ";".join(partes), "-map", "[vout]", "-map", amap]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-r", "30", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total:.2f}", "-movflags", "+faststart", str(Path(salida).resolve()),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


# ── Orquestación ───────────────────────────────────────────────────────────────
def generar(convocatorias, salida=None):
    """Genera el MP4 y devuelve su ruta (o None si falla)."""
    if not convocatorias:
        return None
    salida = salida or f"video_{datetime.now():%Y-%m-%d}.mp4"
    try:
        lineas = construir_guion(convocatorias)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            voice, tiempos, total = sintetizar(lineas, tmp)
            fondo = tmp / "fondo.png"
            crear_fondo(fondo)
            overlays = crear_overlays(tiempos, tmp)
            musica = _music_bed() or _generar_musica(tmp, tmp / "music.wav")
            montar(fondo, voice, overlays, total, salida, musica)
        print(f"🎬 Vídeo generado: {salida} ({total:.1f}s)")
        return salida
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", "ignore")[-600:]
        print(f"⚠️  Vídeo: ffmpeg falló: {err}")
        return None
    except Exception as e:
        print(f"⚠️  Vídeo: error inesperado: {e}")
        return None


def subir_video(archivo, nombre_remoto):
    """Sube el MP4 a Supabase Storage y devuelve la URL pública."""
    if not (SUPABASE_URL and SUPABASE_API_KEY):
        raise RuntimeError("Faltan SUPABASE_URL / SUPABASE_API_KEY")
    datos = Path(archivo).read_bytes()
    destino = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{nombre_remoto}"
    req = urllib.request.Request(
        destino, data=datos, method="POST",
        headers={
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "apikey": SUPABASE_API_KEY,
            "Content-Type": "video/mp4",
            "x-upsert": "true",
        },
    )
    urllib.request.urlopen(req, timeout=120).read()
    return f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{nombre_remoto}"


def enviar_video_redes(convocatorias):
    """Genera el vídeo, lo sube y dispara el webhook de Make. Best-effort."""
    if not VIDEO_WEBHOOK_URL:
        print("🎬 Vídeo: VIDEO_WEBHOOK_URL no configurado, se omite.")
        return False
    fecha_slug = datetime.now().strftime("%Y-%m-%d")
    salida = f"/tmp/video_{fecha_slug}.mp4"
    if not generar(convocatorias, salida):
        return False
    try:
        url = subir_video(salida, f"video/{fecha_slug}.mp4")
    except Exception as e:
        print(f"⚠️  Vídeo: subida a Supabase falló: {e}")
        return False

    hoy = datetime.now()
    caption = (
        f"🎯 Convocatorias del BOE · {hoy.day} {_MESES[hoy.month - 1]}\n\n"
        "👉 Toda la información y el enlace al BOE en oponoticias.com\n\n"
        "#oposiciones #empleopublico #BOE #oposicion2026 #funcionario #opositar"
    )
    try:
        payload = json.dumps({"video_url": url, "caption": caption}).encode("utf-8")
        req = urllib.request.Request(
            VIDEO_WEBHOOK_URL, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=20).read()
        print(f"🎬 Vídeo enviado a redes: {url}")
        return True
    except Exception as e:
        print(f"⚠️  Vídeo: webhook falló (no bloquea): {e}")
        return False


if __name__ == "__main__":
    # Prueba local con datos de ejemplo
    demo = [
        {"resumen_ia": "200 plazas - Enfermero/a - Andalucía", "comunidad_autonoma": "Andalucía"},
        {"resumen_ia": "85 plazas - Auxiliar Administrativo - Madrid", "comunidad_autonoma": "Madrid"},
        {"resumen_ia": "40 plazas - Policía Local - Comunidad Valenciana", "comunidad_autonoma": "Comunidad Valenciana"},
        {"resumen_ia": "30 plazas - Maestro de Primaria - Galicia", "comunidad_autonoma": "Galicia"},
        {"resumen_ia": "12 plazas - Bombero - Cataluña", "comunidad_autonoma": "Cataluña"},
    ]
    generar(demo, "/tmp/video_demo.mp4")
