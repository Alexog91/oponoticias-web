-- ════════════════════════════════════════════════════════════════════
--  Tabla noticias_rss — columna de NOTICIAS del Diario del Opositor
--  Ejecutar una sola vez en: Supabase → SQL Editor → New query → Run
-- ════════════════════════════════════════════════════════════════════

create table if not exists public.noticias_rss (
  id          bigint generated always as identity primary key,
  titulo      text not null,
  descripcion text,
  enlace      text not null unique,          -- evita duplicados (dedup por URL)
  fuente      text default '20minutos',
  imagen      text,
  fecha_pub   timestamptz,
  created_at  timestamptz default now()
);

-- Índice para ordenar por fecha rápido
create index if not exists idx_noticias_fecha on public.noticias_rss (fecha_pub desc);

-- Seguridad a nivel de fila: lectura pública (anon), escritura solo con service_role
alter table public.noticias_rss enable row level security;

-- Política de SOLO LECTURA para el frontend (clave anon de loader.js)
drop policy if exists "noticias lectura publica" on public.noticias_rss;
create policy "noticias lectura publica"
  on public.noticias_rss
  for select
  to anon
  using (true);

-- Nota: el script actualizar_noticias.py debe usar la SERVICE_ROLE key
-- (no la anon) para poder insertar, ya que la inserción salta la RLS.
