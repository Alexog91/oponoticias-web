#!/usr/bin/env python3
"""
test_tiktok_subida.py — Prueba de subida de borrador a TikTok (sandbox).

Genera un vídeo corto de prueba (1080×1920, ~6s), lo sube a Supabase y lo
manda a TikTok como BORRADOR vía publicar_tiktok. Sirve para validar el
pipeline OAuth + Content Posting API sin tocar el flujo diario.

El usuario verá el borrador en TikTok app → Perfil → Borradores.

Requiere: TIKTOK_CLIENT_KEY/SECRET (sandbox), SUPABASE_URL, SUPABASE_API_KEY, ffmpeg.
"""

import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publicar_tiktok
import generar_video_diario as gvd


def main():
    print("=" * 60)
    print("Prueba de subida a TikTok (borrador, sandbox)")
    print("=" * 60)

    if not publicar_tiktok.configurado():
        print("❌ TikTok no configurado (faltan TIKTOK_CLIENT_KEY/SECRET o Supabase)")
        raise SystemExit(1)

    # 1) Generar un vídeo de prueba vertical de ~6s (color de marca + tono suave)
    salida = "/tmp/tiktok_test.mp4"
    print("🎬 Generando vídeo de prueba…")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x2B2622:s=1080x1920:d=6:r=30",
        "-f", "lavfi", "-i", "sine=frequency=330:duration=6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        salida,
    ], check=True, capture_output=True)
    print(f"   OK: {salida} ({os.path.getsize(salida)} bytes)")

    # 2) Subir a Supabase Storage (de ahí lo descarga publicar_tiktok)
    print("☁️  Subiendo a Supabase…")
    url = gvd.subir_video(salida, "video/tiktok-test.mp4")
    print(f"   URL: {url}")

    # 3) Mandar a TikTok como borrador
    print("🎵 Enviando a TikTok (borrador)…")
    ok = publicar_tiktok.publicar_draft_tiktok(url, "Prueba OpoNoticias", verificar_estado=True)
    print("=" * 60)
    if ok:
        print("✅ TikTok aceptó el vídeo. Ábrelo en la app → Perfil → Borradores.")
    else:
        print("❌ La subida a TikTok falló (ver mensajes arriba).")
        raise SystemExit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
