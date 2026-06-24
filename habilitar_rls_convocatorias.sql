-- Seguridad: habilitar Row-Level Security en la tabla convocatorias.
-- Soluciona el aviso "Table publicly accessible / rls_disabled_in_public".
--
-- Contexto: el frontend (assets/loader.js) lee convocatorias con la clave
-- ANÓNIMA, que va embebida en el JS público. Sin RLS, esa clave permite
-- también escribir y BORRAR. Con RLS + política de solo SELECT, el público
-- únicamente puede LEER.
--
-- Los procesos que escriben (GitHub Actions: leer_boe.py, etc.) usan la clave
-- SERVICE_ROLE, que IGNORA RLS: seguirán insertando/actualizando sin cambios.
--
-- Ejecutar en: Supabase → SQL Editor → New query → Run.

ALTER TABLE public.convocatorias ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "convocatorias lectura publica" ON public.convocatorias;
CREATE POLICY "convocatorias lectura publica"
  ON public.convocatorias
  FOR SELECT
  USING (true);
