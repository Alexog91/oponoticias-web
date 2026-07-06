-- Evita la condición de carrera en generar_blog.py: si el workflow se
-- dispara dos veces el mismo día (manual + cron), dos ejecuciones podían
-- comprobar "articulo_reciente(categoria)" casi al mismo tiempo, ver que no
-- había artículo reciente TODAVÍA (porque ninguna había terminado de
-- generar y guardar el suyo) y generar 2 artículos de la misma categoría.
--
-- Esta tabla es solo de coordinación interna (no la lee el frontend): cada
-- ejecución intenta "reservar" la categoría para HOY con un INSERT antes de
-- generar nada; el segundo INSERT choca con la clave primaria (categoria,
-- fecha) y falla con 409, así la segunda ejecución salta esa categoría sin
-- gastar una llamada a Claude ni duplicar el artículo.
--
-- Ejecutar una vez en Supabase → SQL Editor.

CREATE TABLE IF NOT EXISTS blog_claims (
  categoria  text NOT NULL,
  fecha      date NOT NULL DEFAULT CURRENT_DATE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (categoria, fecha)
);

ALTER TABLE blog_claims ENABLE ROW LEVEL SECURITY;
-- Sin políticas para anon: tabla totalmente privada (solo la usa el script
-- con la service_role key), igual que suscriptores/envios_newsletter.
