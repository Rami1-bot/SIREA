-- ============================================================
-- 56_latido_robot.sql · SIREA 3.5
-- Función mínima para el robot de actividad (scripts/mantener_activo.py).
--
-- Supabase (plan gratuito) pausa el proyecto si pasa ~7 días con poca actividad.
-- El robot llama a esta función cada 1–2 días: es una consulta real a la base
-- (cuenta como actividad) pero NO lee ni toca ninguna tabla; solo devuelve la hora.
-- Por eso puede usarse con la clave PÚBLICA (anon), sin exponer la clave secreta.
-- Seguro de repetir.
-- ============================================================
create or replace function public.sirea_latido()
returns timestamptz
language sql
stable
security invoker
set search_path = ''
as $$ select now() $$;

revoke all on function public.sirea_latido() from public;
grant execute on function public.sirea_latido() to anon, authenticated, service_role;

comment on function public.sirea_latido() is
  'SIREA: latido del robot de actividad (solo devuelve la hora; no accede a tablas).';

-- Comprobación: debe devolver la hora actual.
select public.sirea_latido() as latido_ok;
