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
FPS     = 30

# Motor de voz: "edge" (edge-tts, voz Ximena — la elegida) o "piper" (alternativa).
TTS_BACKEND = os.environ.get("VIDEO_TTS", "edge")
# Voz Piper (femenina sharvard por defecto; masculina: es_ES-davefx-medium).
PIPER_VOICE = os.environ.get("PIPER_VOICE", "es_ES-sharvard-medium")
PIPER_LENGTH = os.environ.get("PIPER_LENGTH", "1.0")   # >1 más lento, <1 más rápido
PIPER_BIN = shutil.which("piper") or "piper"
# Voz edge-tts (alternativa).
VOZ     = os.environ.get("VIDEO_VOZ", "es-ES-XimenaNeural")
RATE    = os.environ.get("VIDEO_RATE", "+2%")
PITCH   = os.environ.get("VIDEO_PITCH", "+0Hz")

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


# Categorías visuales: (clave de tema, emoji, palabras clave del puesto).
# La clave de tema la usa Remotion para teñir la escena con un color propio,
# así dos vídeos con contenido distinto se ven distintos sin tocar nada.
CATEGORIAS = [
    ("sanidad",   "🏥", ("enfermer", "medic", "sanitari", "salud", "farmac", "celador", "matron")),
    ("educacion", "🎓", ("maestro", "profesor", "docent", "educa", "catedrá", "secundaria")),
    ("seguridad", "🚓", ("policí", "guardia", "bombero", "militar", "segurid", "vigilan", "penitenciar")),
    ("justicia",  "⚖️", ("justicia", "tramitaci", "procesal", "fiscal", "jurídic", "letrad")),
    ("tech",      "💻", ("inform", "program", "sistemas", "digital", "tecnolog")),
    ("ciencia",   "🔬", ("investiga", "científic", "laboratori", "técnico especialista")),
    ("admin",     "🗂️", ("administrat", "auxiliar", "gestión", "gestor", "oficial", "ordenanza")),
]


def _categoria(puesto):
    """Devuelve (clave_tema, emoji) según el puesto. Fallback: ('general', '📋')."""
    p = (puesto or "").lower()
    for clave, emoji, claves in CATEGORIAS:
        if any(k in p for k in claves):
            return clave, emoji
    return "general", "📋"


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


# Nombre legible de cada categoría para la escena "Por sector".
CAT_NOMBRE = {
    "sanidad": "Sanidad",
    "educacion": "Educación",
    "seguridad": "Seguridad",
    "justicia": "Justicia",
    "tech": "Tecnología",
    "ciencia": "Ciencia",
    "admin": "Administración",
    "general": "Administración local",
}


def _es_nacional(lugar):
    return (lugar or "").strip().lower() in ("nacional/estatal", "nacional", "estatal")


def construir_guion(convocatorias, max_destacadas=3):
    """Guión EDITORIAL del día (mezcla total + sector + destacadas + newsletter).

    No lee convocatoria a convocatoria (habría días de 60): resume el conjunto con
    el total y un desglose por sector, y solo destaca 2-3. El filtrado por comunidad
    se delega a la web (CTA final). Devuelve escenas con narración + datos Remotion.
    """
    from datetime import datetime as _dt
    n = len(convocatorias)
    hoy = _dt.now()
    fecha_larga = f"{hoy.day} de {_MESES[hoy.month - 1]}"

    # Conteo por sector (sobre TODAS) y dedup ordenado por plazas para destacadas.
    conteo, vistas, todas = {}, set(), []
    for conv in sorted(convocatorias, key=_plazas_num, reverse=True):
        plazas, puesto, lugar = _datos(conv)
        cat = _categoria(puesto)[0]
        conteo[cat] = conteo.get(cat, 0) + 1
        clave = (puesto.lower(), lugar.lower())
        if clave not in vistas:
            vistas.add(clave)
            todas.append((plazas, puesto, lugar))

    # Fusiona el cajón "general" (catch-all) con "admin": se mostraban como
    # "Administración" y "Administración local" → dos barras casi idénticas y
    # confusas. La mayoría del catch-all es administración municipal/general.
    if "general" in conteo:
        conteo["admin"] = conteo.get("admin", 0) + conteo.pop("general")

    sectores = sorted(conteo.items(), key=lambda kv: kv[1], reverse=True)[:6]
    items_sector = [{"label": CAT_NOMBRE.get(k, k.title()), "count": v} for k, v in sectores]

    # Destacadas: las de más plazas (o ámbito nacional) — las que merecen foco.
    destacadas = []
    for plazas, puesto, lugar in todas[:max_destacadas]:
        m = re.search(r"\d+", plazas)
        num = m.group() if m else ""
        num_fmt = f"{int(num):,}".replace(",", ".") if num else ""
        if _es_nacional(lugar):
            org = "Ámbito nacional"
            tag = f"{num_fmt} plazas" if (num and num != "1") else "Estatal"
        else:
            org = lugar
            tag = f"{num_fmt} plazas" if (num and num != "1") else "1 plaza"
        destacadas.append({"puesto": puesto, "org": org, "tag": tag,
                           "tema": _categoria(puesto)[0]})

    # Listado completo del día (resumen estilo WhatsApp): todas, compactas, con
    # icono por categoría. Se cap­a a MAX_LISTADO para no saturar el scroll.
    MAX_LISTADO = 30
    listado = []
    for plazas, puesto, lugar in todas[:MAX_LISTADO]:
        m = re.search(r"\d+", plazas)
        num = m.group() if m else ""
        sitio = "Estatal" if _es_nacional(lugar) else lugar
        if num and num != "1":
            tag = f"{int(num):,}".replace(",", ".") + " plazas"
        else:
            tag = ""
        listado.append({"puesto": puesto, "lugar": sitio, "tag": tag,
                        "tema": _categoria(puesto)[0]})

    escenas = []
    # 1) Portada: el total del día.
    escenas.append({
        "kind": "portada",
        "narr": f"Hoy el BOE trae {_num_es(n)} convocatorias nuevas de empleo público.",
        "titulo": "El BOE de hoy",
        "total": n,
        "fecha": fecha_larga,
    })
    # 2) Por sector: resumen agregado de todas.
    escenas.append({
        "kind": "sector",
        "narr": "Estas son las áreas con más oferta hoy.",
        "titulo": "Por sector",
        "total": n,
        "items": items_sector,
    })
    # 3) Destacadas: 2-3 notables.
    if destacadas:
        escenas.append({
            "kind": "destacadas",
            "narr": "Y estas son las más destacadas del día.",
            "titulo": "Destacadas",
            "items": destacadas,
            "extra": max(0, n - len(destacadas)),
        })
    # 4) Listado completo: todas las del día de un vistazo (scroll si hay muchas).
    if listado:
        escenas.append({
            "kind": "listado",
            "narr": "Y este es el resumen del día al completo: toda la oferta de hoy, de un vistazo.",
            "titulo": "Todas las de hoy",
            "items": listado,
            "extra": max(0, len(todas) - len(listado)),
        })
    # 5) Newsletter: gancho con el lead magnet (Calendario del Opositor).
    escenas.append({
        "kind": "newsletter",
        "narr": "Suscríbete gratis y llévate el Calendario del Opositor en tu correo.",
        "regalo": "Calendario del Opositor 2026",
        "cta": "oponoticias.com",
    })
    # 6) Cierre: filtrado por comunidad en la web + seguir.
    escenas.append({
        "kind": "cierre",
        "narr": "¿Buscas las de tu comunidad? Encuéntralas en oponoticias punto com. Síguenos.",
        "lineas": ["¿Buscas las de", "tu comunidad?"],
        "cta": "Fíltralas en oponoticias.com",
    })
    return escenas


# ── 2) Voz frase a frase (tiempos exactos) ─────────────────────────────────────
def _piper_model():
    """Asegura el modelo Piper en caché (lo descarga de HuggingFace si falta).
    Devuelve la ruta al .onnx."""
    cache = REPO / ".cache" / "piper"
    cache.mkdir(parents=True, exist_ok=True)
    onnx = cache / f"{PIPER_VOICE}.onnx"
    cfg = cache / f"{PIPER_VOICE}.onnx.json"
    if onnx.exists() and cfg.exists():
        return str(onnx)
    m = re.match(r"(([a-z]{2})_[A-Z]{2})-([^-]+)-(.+)", PIPER_VOICE)
    if not m:
        raise RuntimeError(f"PIPER_VOICE inválida: {PIPER_VOICE}")
    loc, lang, name, qual = m.group(1), m.group(2), m.group(3), m.group(4)
    base = (f"https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            f"{lang}/{loc}/{name}/{qual}/{PIPER_VOICE}")
    for url, dest in ((f"{base}.onnx", onnx), (f"{base}.onnx.json", cfg)):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            dest.write_bytes(r.read())
    return str(onnx)


async def _tts_edge(texto, destino):
    import edge_tts
    comm = edge_tts.Communicate(texto, VOZ, rate=RATE, pitch=PITCH)
    with open(destino, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def _voz_frase(texto, wav_out, tmp, i, modelo):
    """Sintetiza una frase a WAV 44100 estéreo, según el backend elegido."""
    if TTS_BACKEND == "piper":
        raw = tmp / f"raw{i}.wav"
        subprocess.run(
            [PIPER_BIN, "-m", modelo, "--length-scale", PIPER_LENGTH,
             "--sentence-silence", "0.35", "-f", str(raw)],
            input=texto.encode("utf-8"), check=True, capture_output=True,
        )
    else:
        raw = tmp / f"raw{i}.mp3"
        asyncio.run(_tts_edge(texto, raw))
    subprocess.run([FFMPEG, "-y", "-i", str(raw), "-ar", "44100", "-ac", "2", str(wav_out)],
                   check=True, capture_output=True)


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
    modelo = _piper_model() if TTS_BACKEND == "piper" else None
    piezas, tiempos = [], []
    t = 0.0
    for i, esc in enumerate(escenas):
        wav = tmp / f"seg{i}.wav"
        _voz_frase(esc["narr"], wav, tmp, i, modelo)
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
    """Pista del día. Rota de forma determinista sobre assets/music/*.{mp3,m4a,wav}
    (índice = día del año % nº pistas → nunca repite en una semana). Si no hay
    carpeta, cae al archivo único assets/music_bed.* y, en último término, a None
    (música generada por _generar_musica)."""
    carpeta = REPO / "assets" / "music"
    if carpeta.is_dir():
        pistas = sorted(p for p in carpeta.iterdir()
                        if p.suffix.lower() in (".mp3", ".m4a", ".wav"))
        if pistas:
            idx = datetime.now().timetuple().tm_yday % len(pistas)
            print(f"🎵 Música del día: {pistas[idx].name} ({idx + 1}/{len(pistas)})")
            return str(pistas[idx])
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
    """Voz + música → WAV final, con la VOZ siempre por delante.

    Clave: se normaliza cada fuente por separado a un nivel fijo —voz a -16 LUFS,
    música ~14 dB por debajo (-30 LUFS)— en vez de normalizar la mezcla entera.
    Así el balance voz:música no depende de lo alta que venga la pista (los MP3
    comerciales rondan -12 LUFS). Además, ducking sidechain que baja la música
    durante la locución. Salida global ≈ -16 LUFS (igual que antes)."""
    fade = f"afade=t=out:st={max(0.0, total - 0.6):.2f}:d=0.6"
    if musica:
        cmd = [FFMPEG, "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(musica),
               "-filter_complex",
               "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,asplit=2[vmix][vkey];"
               "[1:a]loudnorm=I=-30:TP=-3:LRA=11[m];"
               "[m][vkey]sidechaincompress=threshold=0.04:ratio=6:attack=5:release=350[mduck];"
               "[vmix][mduck]amix=inputs=2:duration=longest:dropout_transition=0[mix];"
               f"[mix]loudnorm=I=-16:TP=-1.5:LRA=11,{fade},alimiter=limit=0.95[a]",
               "-map", "[a]", "-t", f"{total:.2f}", "-ar", "44100", "-ac", "2", str(destino)]
    else:
        cmd = [FFMPEG, "-y", "-i", str(voice), "-af",
               f"loudnorm=I=-16:TP=-1.5:LRA=11,{fade}",
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
    salida = salida or f"/tmp/video_{datetime.now():%Y-%m-%d}_{os.getpid()}.mp4"
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
                # Día del año → Remotion rota la paleta de fondo (variedad diaria).
                "seed": hoy.timetuple().tm_yday,
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
    """Genera el vídeo, lo sube y lo publica en redes. Best-effort.

    - Meta (FB + IG Reel): API directa con FB_PAGE_TOKEN, sin límite.
    - TikTok: API directa (borrador) si TIKTOK_CLIENT_KEY/SECRET están en env;
      el usuario ve el vídeo en Borradores y lo publica con un toque.
      Fallback: VIDEO_WEBHOOK_URL (Make) si no hay credenciales TikTok.
    """
    import publicar_meta
    api_directa = publicar_meta.configurado()
    if not (api_directa or VIDEO_WEBHOOK_URL):
        print("🎬 Vídeo: sin API directa ni VIDEO_WEBHOOK_URL, se omite.")
        return False
    fecha_slug = datetime.now().strftime("%Y-%m-%d")
    salida = f"/tmp/video_{fecha_slug}_{os.getpid()}.mp4"
    if not generar(convocatorias, salida):
        return False
    try:
        url = subir_video(salida, f"video/{fecha_slug}.mp4")
    except Exception as e:
        print(f"⚠️  Vídeo: subida a Supabase falló: {e}")
        return False

    hoy = datetime.now()
    # Nota de licencia de música: si en assets/music/ hay pistas de Incompetech
    # (Kevin MacLeod, CC BY) hay que mantener la atribución; las de Pixabay / YouTube
    # Audio Library marcadas "sin atribución" no la requieren. Por defecto, sin crédito
    # (usa fuentes sin atribución). Si añades Incompetech, pon VIDEO_MUSIC_CREDIT.
    credito = os.environ.get("VIDEO_MUSIC_CREDIT", "").strip()
    caption = (
        f"🎯 Convocatorias del BOE · {hoy.day} {_MESES[hoy.month - 1]}\n\n"
        "👉 Toda la información y el enlace al BOE en oponoticias.com\n\n"
        "#oposiciones #empleopublico #BOE #oposicion2026 #funcionario #opositar"
        + (f"\n\n🎵 {credito}" if credito else "")
    )

    ok = False
    # ── Vía preferente: API directa (FB vídeo + IG Reel) ───────────────────────
    if api_directa:
        fb = publicar_meta.publicar_video_facebook(url, caption)
        ig = publicar_meta.publicar_reel_instagram(url, caption)
        ok = fb or ig

    # ── TikTok: API directa (borrador) si hay credenciales ─────────────────────
    import publicar_tiktok
    if publicar_tiktok.configurado():
        if publicar_tiktok.publicar_draft_tiktok(url):
            ok = True
    elif VIDEO_WEBHOOK_URL:
        # Fallback: webhook de Make (solo si no hay TikTok API configurada)
        try:
            payload = json.dumps({"video_url": url, "caption": caption}).encode("utf-8")
            req = urllib.request.Request(VIDEO_WEBHOOK_URL, data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=20).read()
            print(f"🎬 Vídeo enviado al webhook (Make): {url}")
            ok = True
        except Exception as e:
            print(f"⚠️  Vídeo: webhook falló (no bloquea): {e}")
    return ok


if __name__ == "__main__":
    demo = [
        {"resumen_ia": "200 plazas - Enfermero/a - Andalucía", "comunidad_autonoma": "Andalucía"},
        {"resumen_ia": "1500 plazas - Auxiliar Administrativo - Madrid", "comunidad_autonoma": "Madrid"},
        {"resumen_ia": "40 plazas - Policía Local - Comunidad Valenciana", "comunidad_autonoma": "Comunidad Valenciana"},
        {"resumen_ia": "30 plazas - Maestro de Primaria - Galicia", "comunidad_autonoma": "Galicia"},
        {"resumen_ia": "12 plazas - Bombero - Cataluña", "comunidad_autonoma": "Cataluña"},
    ]
    generar(demo, "/tmp/video_demo.mp4")
