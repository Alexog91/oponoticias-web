# Música de fondo del vídeo diario

Suelta aquí **7-10 pistas** `.mp3` (o `.m4a` / `.wav`). `generar_video_diario.py`
elige una **por día** de forma determinista (día del año % nº de pistas), así no
repite música en una semana. Si esta carpeta está vacía, cae a `assets/music_bed.mp3`.

## De dónde sacarlas (gratis y libres para redes)

- **Pixabay Music** — https://pixabay.com/music/ — sin atribución obligatoria. ✅ recomendado
- **YouTube Audio Library** — Studio → Biblioteca de audio — filtra "Sin atribución". ✅
- **Free Music Archive** — https://freemusicarchive.org — revisar licencia por pista.
- **Incompetech (Kevin MacLeod)** — https://incompetech.com — CC BY: **exige atribución**.

## Atribución

Por defecto el pie de publicación NO incluye crédito (usa fuentes sin atribución).
Si añades pistas de Incompetech u otras CC BY, define la variable de entorno
`VIDEO_MUSIC_CREDIT` (p. ej. `Música: Kevin MacLeod · CC BY 4.0`) y se añadirá al caption.

## Recomendaciones

- Estilo: instrumental, ritmo medio/alto, sin voces (para no chocar con la locución).
- Duración: que dure ≥ 30 s (se hace loop con `-stream_loop -1`).
- Volumen: da igual el máster, se normaliza a -16 LUFS con ducking sobre la voz.
- Nombra con orden si quieres controlar la rotación: `01-xxx.mp3`, `02-yyy.mp3`, …
