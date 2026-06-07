-- ════════════════════════════════════════════════════════════════════
--  Añade la columna comunidad_autonoma a la tabla convocatorias
--  Ejecutar una vez en: Supabase → SQL Editor → New query → Run
-- ════════════════════════════════════════════════════════════════════

alter table public.convocatorias
  add column if not exists comunidad_autonoma text;

-- Índice para filtrar/agrupar por comunidad rápido
create index if not exists idx_conv_comunidad
  on public.convocatorias (comunidad_autonoma);

-- Después de ejecutar esto:
--   1) Rellena los 540 registros existentes:  python3 migrar_comunidad.py
--   2) leer_boe.py ya guardará la comunidad en cada nueva convocatoria.
--   3) El frontend usará la columna automáticamente (y si está vacía,
--      sigue infiriéndola en el navegador como hasta ahora).
