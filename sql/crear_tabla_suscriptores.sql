-- ════════════════════════════════════════════════════════════════════
--  Tablas para el motor de email propio (Amazon SES) — reemplaza a Brevo
--  como almacén de suscriptores y control de envíos.
--
--  Ejecutar UNA sola vez en: Supabase → SQL Editor → New query → Run
--  Proyecto: opnbxphxfclazxduhmkp
--
--  IMPORTANTE: esto NO borra ni toca nada de Brevo. Solo crea tablas
--  nuevas y vacías. Mientras no cambiemos los workflows, el boletín
--  sigue saliendo por Brevo exactamente igual que hoy.
-- ════════════════════════════════════════════════════════════════════

-- ── Suscriptores ────────────────────────────────────────────────────
-- Sustituye a la "lista" de contactos de Brevo. Guarda email + comunidad
-- (para la segmentación que ya calcula enviar_newsletter.py) + estado.
create table if not exists public.suscriptores (
  id          bigint generated always as identity primary key,
  email       text not null unique,               -- dedup por email
  comunidad   text,                               -- CCAA elegida (null = recibe todo)
  estado      text not null default 'activo',     -- 'activo' | 'baja' | 'rebote'
  -- Token opaco para el enlace de baja de 1 clic. NUNCA se pone el email
  -- en la URL (privacidad): el enlace lleva este token, no el correo.
  token_baja  uuid not null default gen_random_uuid() unique,
  material    text,                               -- lead magnet de origen (opcional)
  origen      text,                               -- popup | home | recursos (opcional)
  fecha_alta  timestamptz default now(),
  fecha_baja  timestamptz,                        -- se rellena al darse de baja
  created_at  timestamptz default now()
);

-- Índices para los dos filtros que hará el script de envío:
--   1) suscriptores activos, 2) por comunidad.
create index if not exists idx_suscriptores_estado    on public.suscriptores (estado);
create index if not exists idx_suscriptores_comunidad on public.suscriptores (comunidad);

-- ── Control de envíos (idempotencia) ────────────────────────────────
-- Equivale a la comprobación campana_de_hoy_ya_existe() que hoy se hace
-- contra Brevo. Una fila por día = ese día ya se envió (evita duplicados
-- si el workflow se re-dispara; ver el problema de los 3 correos del 26 jun).
create table if not exists public.envios_newsletter (
  fecha       date primary key,                   -- YYYY-MM-DD del envío
  enviados    int  default 0,                     -- nº de emails aceptados por SES
  errores     int  default 0,
  created_at  timestamptz default now()
);

-- ── Seguridad a nivel de fila (RLS) ─────────────────────────────────
-- CLAVE: a diferencia de noticias_rss (que tiene lectura pública para el
-- frontend), la tabla suscriptores contiene EMAILS → NO debe ser legible
-- por la clave anon bajo ninguna circunstancia. Activamos RLS y NO creamos
-- ninguna política para 'anon': así el rol anónimo no ve ni escribe nada.
-- El rol service_role SALTA la RLS por completo (Postgres), así que los
-- endpoints de Vercel (api/*.js) y los scripts Python que usan la clave
-- service_role + cabecera Authorization: Bearer seguirán leyendo/escribiendo
-- con normalidad. Ver la nota de la clave legacy JWT (no sb_secret_).
alter table public.suscriptores      enable row level security;
alter table public.envios_newsletter enable row level security;

-- (No se crean políticas para anon a propósito → tabla privada.)
