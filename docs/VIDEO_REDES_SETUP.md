# Vídeo diario automático → TikTok / Instagram Reels / Facebook Reels

El script `generar_video_diario.py` ya genera cada mañana un vídeo vertical
(1080×1920) con voz, subtítulos y marca, lo sube a Supabase Storage y hace un
POST a un webhook de Make.com con este JSON:

```json
{
  "video_url": "https://<supabase>/storage/v1/object/public/social/video/2026-06-20.mp4",
  "caption": "🎯 Convocatorias del BOE · 20 junio\n\n👉 ... #oposiciones ..."
}
```

Solo falta crear el escenario de Make que reciba ese JSON y publique en las
tres redes. Esto hay que hacerlo a mano una vez (requiere autorizar tus cuentas).

## 1. Crear el escenario en Make.com

1. **Create a new scenario**.
2. Primer módulo: **Webhooks → Custom webhook** → *Add* → nómbralo
   `oponoticias-video`. Make te da una URL. **Cópiala.**
3. Pulsa **Run once** y, para que Make aprenda la estructura, lanza el workflow
   manualmente en GitHub (ver paso 3) o envía un POST de prueba con el JSON de
   arriba. Make detectará los campos `video_url` y `caption`.

## 2. Añadir los módulos de publicación

Conecta en serie (o en rutas paralelas) tras el webhook:

### Facebook Reels
- Módulo: **Facebook Pages → Upload a Reel** (o *Create a Photo/Video Post*).
- Page: tu página OpoNoticias.
- Video URL: `{{1.video_url}}`  ·  Description: `{{1.caption}}`.
- Conexión: autoriza con la cuenta que administra la página. **100% automático.**

### Instagram Reels
- Módulo: **Instagram for Business → Create a Reel** (publica vía Graph API).
- Requiere cuenta de Instagram **Business/Creator** vinculada a la página de
  Facebook (ya la tienes para el carrusel).
- Video URL: `{{1.video_url}}`  ·  Caption: `{{1.caption}}`. **100% automático.**

### TikTok
- Módulo: **TikTok → Upload a video**.
- Conexión: autoriza tu cuenta `@oponoticias`.
- Video URL: `{{1.video_url}}`  ·  Title: `{{1.caption}}`.
- ⚠️ **Limitación**: hasta que la app de TikTok pase la auditoría de contenido,
  la API solo puede dejar el vídeo en **borradores** (lo abres en la app y das a
  publicar — 5 segundos). Para publicado 100% automático hay que solicitar la
  *Content Posting API audit* en el portal de desarrolladores de TikTok
  (1-2 semanas de revisión).

Activa el escenario (**Scheduling: ON**, modo *immediately as data arrives*).

## 3. Conectar GitHub con el webhook

1. En GitHub → repo `oponoticias-web` → **Settings → Secrets and variables →
   Actions → New repository secret**.
2. Nombre: `VIDEO_WEBHOOK_URL`  ·  Valor: la URL del webhook de Make (paso 1.2).
3. Listo. A la mañana siguiente el vídeo se generará y publicará solo.

> Para probar sin esperar: en GitHub → pestaña **Actions → Daily BOE Check →
> Run workflow**. Si `VIDEO_WEBHOOK_URL` no está configurado, el paso de vídeo
> simplemente se omite con un aviso (no rompe nada).

## Ajustes opcionales del vídeo

Variables de entorno (se pueden añadir como secrets o en el `env:` del workflow):

| Variable      | Por defecto          | Qué hace                              |
|---------------|----------------------|---------------------------------------|
| `VIDEO_VOZ`   | `es-ES-ElviraNeural` | Voz (alt.: `es-ES-AlvaroNeural`)      |
| `VIDEO_RATE`  | `+6%`                | Velocidad del habla                   |

**Música**: si colocas un MP3 en `assets/music_bed.mp3`, se mezcla de fondo a
volumen bajo. (En TikTok suele rendir más añadir un *sonido trending* desde la
app; para FB/IG la música incrustada está bien.)
