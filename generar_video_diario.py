#!/usr/bin/env python3
"""
generar_video_diario.py — Vídeo vertical diario (1080×1920) para TikTok,
Instagram Reels y Facebook Reels, con MOTION GRAPHICS reales vía Remotion.

Pipeline (corre en GitHub Actions, sin intervención):
  1. Construye un guión a partir de las convocatorias con más plazas.
  2. Sintetiza voz neural española con edge-tts, frase a frase, midiendo la
     duración real de cada una (números convertidos a palabras con num2words).
  3. Mezcla voz + cama de música (ducking sidechain + loudnorm -16 LUFS) → WAV.
  4. Escribe props.json (escenas + tiempos + audio) y renderiza con Remotion
     (React/Chrome headless): fondo animado, entradas con spring, contador de
     plazas, transiciones y barra de progreso.
  5. Sube el MP4 a Supabase Storage y dispara VIDEO_WEBHOOK_URL (Make.com).

Best-effort: cualquier fallo se reporta y devuelve None sin romper leer_boe.py.
"""

import os
import re
import json
import shutil
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
FPS     = 30

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")
STORAGE_BUCKET   = os.environ.get("SUPABASE_STORAGE_BUCKET", "social")
VIDEO_WEBHOOK_URL = os.environ.get("VIDEO_WEBHOOK_URL", "")

GAP  = 0.16   # silencio entre frases (s)
TAIL = 0.5    # cola final (s)

REPO     = Path(__file__).resolve().parent
REMOTION = REPO / "remotion"
NPX      = shutil.which("npx") or "/opt/homebrew/bin/npx"
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _num_es(n, fem=True):
    """Número → palabras en español (femenino para 'plazas'). Fallback: dígito."""
    try:
        from num2words import num2words
        w = num2words(int(n), lang="es")
    except Exception:
        return str(n)
    if fem:
        w = w.replace("quinientos", "quinientas")
        w = w.replace("cientos", "cientas")
        w = re.sub(r"\bveintiuno\b", "veintiuna", w)
        w = re.sub(r"\buno\b", "una", w)
        w = re.sub(r"uno$", "una", w)
    return w


def _icono(puesto):
    p = (puesto or "").lower()
    pares = [
        ("🏥", ("enfermer", "medic", "sanitari", "salud", "farmac", "celador", "matron")),
        ("🎓", ("maestro", "profesor", "docent", "educa", "catedrá", "secundaria")),
        ("🚓", ("policí", "guardia", "bombero", "militar", "segurid", "vigilan", "penitenciar")),
        ("⚖️", ("justicia", "tramitaci", "procesal", "fiscal", "jurídic", "letrad")),
        ("💻", ("inform", "program", "sistemas", "digital", "tecnolog")),
        ("🔬", ("investiga", "científic", "laboratori", "técnico especialista")),
        ("🗂️", ("administrat", "auxiliar", "gestión", "gestor", "oficial", "ordenanza")),
    ]
    for emoji, claves in pares:
        if any(k in p for k in claves):
            return emoji
    return "📋"


# ── 1) Guión (escenas estructuradas) ───────────────────────────────────────────
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
    """Devuelve lista de escenas: cada una con narración (TTS) + datos (Remotion)."""
    n = len(convocatorias)
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

    escenas = []
    escenas.append({
        "kind": "hook",
        "narr": f"¡Atención, opositores! Hoy el BOE trae {_num_es(n)} convocatorias nuevas. "
                f"Estas son las que más plazas ofrecen.",
        "titulo": "HOY en el BOE",
        "destacado": f"{n} oposiciones nuevas",
    })
    for plazas, puesto, lugar in sel:
        m = re.search(r"\d+", plazas)
        num_txt = m.group() if m else ""
        narr = (f"{_num_es(num_txt)} plazas de {puesto}, en {lugar}." if num_txt
                else f"{puesto}, en {lugar}.")
        escenas.append({
            "kind": "item",
            "narr": narr,
            "plazas": num_txt or plazas,
            "puesto": puesto,
            "lugar": lugar,
            "icon": _icono(puesto),
        })
    escenas.append({
        "kind": "cta",
        "narr": "Síguenos para no perderte ninguna. Todo en oponoticias punto com.",
        "lineas": ["Síguenos y no te", "pierdas ninguna"],
    })
    return escenas


# ── 2) Voz frase a frase (tiempos exactos) ─────────────────────────────────────
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


def sintetizar(escenas, tmp):
    """Genera voice.wav y los tiempos por escena. Devuelve (voice, tiempos, total)."""
    tmp = Path(tmp)
    piezas, tiempos = [], []
    t = 0.0
    for i, esc in enumerate(escenas):
        mp3 = tmp / f"seg{i}.mp3"
        asyncio.run(_tts_a_mp3(esc["narr"], mp3))
        wav = tmp / f"seg{i}.wav"
        subprocess.run([FFMPEG, "-y", "-i", str(mp3), "-ar", "44100", "-ac", "2", str(wav)],
                       check=True, capture_output=True)
        d = _dur(wav)
        if i > 0:
            t += GAP
            piezas.append("sil")
        inicio = t
        t += d
        tiempos.append((round(inicio, 3), round(t, 3)))
        piezas.append(str(wav))

    sil = tmp / "sil.wav"
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-t", str(GAP), str(sil)], check=True, capture_output=True)
    lista = tmp / "concat.txt"
    with open(lista, "w") as f:
        for p in piezas:
            f.write(f"file '{sil if p == 'sil' else p}'\n")
    voice = tmp / "voice.wav"
    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
                    "-c", "copy", str(voice)], check=True, capture_output=True)
    return voice, tiempos, t + TAIL


# ── 3) Música + mezcla con ducking ─────────────────────────────────────────────
def _music_bed():
    for nombre in ("assets/music_bed.mp3", "assets/music_bed.m4a", "assets/music_bed.wav"):
        if (REPO / nombre).exists():
            return str(REPO / nombre)
    return None


def _generar_musica(tmp, destino):
    """Fallback: progresión de 4 acordes (Do-Sol-Lam-Fa) si no hay pista propia."""
    tmp = Path(tmp)
    D = 4.0
    acordes = [(130.81, 164.81, 196.00), (98.00, 123.47, 146.83),
               (110.00, 130.81, 164.81), (87.31, 110.00, 130.81)]
    try:
        cfs = []
        for i, (f1, f2, f3) in enumerate(acordes):
            cf = tmp / f"chord{i}.wav"
            subprocess.run([FFMPEG, "-y",
                            "-f", "lavfi", "-i", f"sine=f={f1}:d={D}",
                            "-f", "lavfi", "-i", f"sine=f={f2}:d={D}",
                            "-f", "lavfi", "-i", f"sine=f={f3}:d={D}",
                            "-filter_complex",
                            "[0][1][2]amix=inputs=3:normalize=1,lowpass=f=950,volume=2.0[a]",
                            "-map", "[a]", str(cf)], check=True, capture_output=True)
            cfs.append(cf)
        prog = 4 * D - 3 * 1.0
        cadena = ("[0][1]acrossfade=d=1[x1];[x1][2]acrossfade=d=1[x2];"
                  "[x2][3]acrossfade=d=1[x3];"
                  "[x3]aecho=0.8:0.7:70:0.3,tremolo=f=0.2:d=0.25,highpass=f=70,"
                  f"afade=t=in:d=1,afade=t=out:st={prog - 1:.2f}:d=1,volume=1.3[a]")
        cmd = [FFMPEG, "-y"]
        for cf in cfs:
            cmd += ["-i", str(cf)]
        cmd += ["-filter_complex", cadena, "-map", "[a]", str(destino)]
        subprocess.run(cmd, check=True, capture_output=True)
        return str(destino)
    except subprocess.CalledProcessError:
        return None


def mezclar_audio(voice, musica, total, destino):
    """Voz + música con DUCKING (sidechain) y loudnorm -16 LUFS → WAV final."""
    norm = (f"loudnorm=I=-16:TP=-1.5:LRA=11,"
            f"afade=t=out:st={max(0.0, total - 0.6):.2f}:d=0.6")
    if musica:
        cmd = [FFMPEG, "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(musica),
               "-filter_complex",
               "[1:a]volume=1.8[m];"
               "[0:a]volume=1.0,asplit=2[vmix][vkey];"
               "[m][vkey]sidechaincompress=threshold=0.06:ratio=4:attack=20:release=400[mduck];"
               "[vmix][mduck]amix=inputs=2:duration=longest:dropout_transition=0[premix];"
               f"[premix]{norm}[a]",
               "-map", "[a]", "-t", f"{total:.2f}", "-ar", "44100", "-ac", "2", str(destino)]
    else:
        cmd = [FFMPEG, "-y", "-i", str(voice), "-af", norm,
               "-t", f"{total:.2f}", "-ar", "44100", "-ac", "2", str(destino)]
    subprocess.run(cmd, check=True, capture_output=True)


# ── 4) Render con Remotion ──────────────────────────────────────────────────────
def _render_remotion(props, salida):
    public = REMOTION / "public"
    public.mkdir(exist_ok=True)
    (REMOTION / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    chrome = os.environ.get("VIDEO_CHROME") or os.environ.get("CHROME_BIN") or MAC_CHROME
    cmd = [NPX, "remotion", "render", "DailyVideo", str(Path(salida).resolve()),
           "--props=props.json", "--concurrency=1"]
    if chrome and Path(chrome).exists():
        cmd.append(f"--browser-executable={chrome}")
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
    subprocess.run(cmd, check=True, capture_output=True, cwd=str(REMOTION), env=env)


# ── Orquestación ───────────────────────────────────────────────────────────────
def generar(convocatorias, salida=None):
    """Genera el MP4 con Remotion y devuelve su ruta (o None si falla)."""
    if not convocatorias:
        return None
    salida = salida or f"/tmp/video_{datetime.now():%Y-%m-%d}.mp4"
    try:
        escenas = construir_guion(convocatorias)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            voice, tiempos, total = sintetizar(escenas, tmp)
            musica = _music_bed() or _generar_musica(tmp, tmp / "music.wav")
            audio_pub = REMOTION / "public" / "audio.wav"
            audio_pub.parent.mkdir(exist_ok=True)
            mezclar_audio(voice, musica, total, audio_pub)

            captions = []
            for esc, (inicio, fin) in zip(escenas, tiempos):
                c = {k: v for k, v in esc.items() if k != "narr"}
                c["start"], c["end"] = inicio, fin
                captions.append(c)
            hoy = datetime.now()
            props = {
                "fps": FPS,
                "total": round(total, 3),
                "fecha": f"{hoy.day} {_MESES[hoy.month - 1]}",
                "audio": "audio.wav",
                "captions": captions,
            }
            _render_remotion(props, salida)
        print(f"🎬 Vídeo generado: {salida} ({total:.1f}s)")
        return salida
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", "ignore")[-800:]
        print(f"⚠️  Vídeo: comando falló: {err}")
        return None
    except Exception as e:
        print(f"⚠️  Vídeo: error inesperado: {e}")
        return None


def subir_video(archivo, nombre_remoto):
    if not (SUPABASE_URL and SUPABASE_API_KEY):
        raise RuntimeError("Faltan SUPABASE_URL / SUPABASE_API_KEY")
    datos = Path(archivo).read_bytes()
    destino = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{nombre_remoto}"
    req = urllib.request.Request(
        destino, data=datos, method="POST",
        headers={"Authorization": f"Bearer {SUPABASE_API_KEY}", "apikey": SUPABASE_API_KEY,
                 "Content-Type": "video/mp4", "x-upsert": "true"},
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
        "#oposiciones #empleopublico #BOE #oposicion2026 #funcionario #opositar\n\n"
        "🎵 Música: Kevin MacLeod (incompetech.com) · CC BY 4.0"
    )
    try:
        payload = json.dumps({"video_url": url, "caption": caption}).encode("utf-8")
        req = urllib.request.Request(VIDEO_WEBHOOK_URL, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=20).read()
        print(f"🎬 Vídeo enviado a redes: {url}")
        return True
    except Exception as e:
        print(f"⚠️  Vídeo: webhook falló (no bloquea): {e}")
        return False


if __name__ == "__main__":
    demo = [
        {"resumen_ia": "200 plazas - Enfermero/a - Andalucía", "comunidad_autonoma": "Andalucía"},
        {"resumen_ia": "1500 plazas - Auxiliar Administrativo - Madrid", "comunidad_autonoma": "Madrid"},
        {"resumen_ia": "40 plazas - Policía Local - Comunidad Valenciana", "comunidad_autonoma": "Comunidad Valenciana"},
        {"resumen_ia": "30 plazas - Maestro de Primaria - Galicia", "comunidad_autonoma": "Galicia"},
        {"resumen_ia": "12 plazas - Bombero - Cataluña", "comunidad_autonoma": "Cataluña"},
    ]
    generar(demo, "/tmp/video_demo.mp4")
