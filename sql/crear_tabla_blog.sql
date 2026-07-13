-- Tabla de artículos del blog de OpoNoticias
-- Ejecutar en Supabase SQL Editor

CREATE TABLE IF NOT EXISTS public.articulos_blog (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  titulo      TEXT NOT NULL,
  slug        TEXT UNIQUE NOT NULL,
  resumen     TEXT NOT NULL,
  contenido   TEXT NOT NULL,
  categoria   TEXT,
  tipo        TEXT DEFAULT 'ia',  -- 'ia' | 'colaboracion' | 'cita'
  fuente_url  TEXT,               -- URL original si es cita/colaboración
  fuente_nombre TEXT,             -- Nombre del autor o medio
  publicado   BOOLEAN DEFAULT TRUE,
  fecha_pub   TIMESTAMPTZ DEFAULT NOW(),
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_blog_categoria  ON public.articulos_blog (categoria);
CREATE INDEX IF NOT EXISTS idx_blog_fecha      ON public.articulos_blog (fecha_pub DESC);
CREATE INDEX IF NOT EXISTS idx_blog_slug       ON public.articulos_blog (slug);
CREATE INDEX IF NOT EXISTS idx_blog_publicado  ON public.articulos_blog (publicado);

-- Row Level Security: solo lectura pública
ALTER TABLE public.articulos_blog ENABLE ROW LEVEL SECURITY;

CREATE POLICY "lectura_publica_blog"
  ON public.articulos_blog
  FOR SELECT
  USING (publicado = TRUE);
