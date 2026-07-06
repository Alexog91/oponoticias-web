-- publicar_hoy_en_x.py es un script interactivo (no cron): si se relanza
-- manualmente, volvía a tuitear las mismas convocatorias porque no había
-- ningún campo que marcara qué ya se había publicado en X.
--
-- Ejecutar una vez en Supabase → SQL Editor.

ALTER TABLE convocatorias
  ADD COLUMN IF NOT EXISTS twitter_enviado boolean NOT NULL DEFAULT false;
