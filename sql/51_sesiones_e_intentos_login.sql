-- ============================================================
-- 51_sesiones_e_intentos_login.sql  (antes 002 en SIGRE)
-- (a) Sesiones e intentos de login PERSISTENTES (reemplazan los
--     diccionarios en memoria de src/auth.py y src/auth_red.py).
-- (b) Protección de la tabla `logs`: sin UPDATE, y sin DELETE de
--     registros con menos de 90 días (retención mínima de auditoría).
--
-- Ejecutar UNA vez en el SQL Editor de Supabase (proyecto DEMO),
-- después de 001_auditoria_agentes_ia.sql.
-- ============================================================

-- ------------------------------------------------------------
-- (a) SESIONES
-- ------------------------------------------------------------
create table if not exists public.sesiones_app (
    token_hash        text primary key,          -- sha256 del token; el token en claro nunca se guarda
    ambito            text not null,             -- 'admin' | 'red'
    sujeto            text not null,             -- usuario administrador o nombre de red
    datos             jsonb not null default '{}'::jsonb,
    ip                text,
    inicio            timestamptz not null default now(),
    ultima_actividad  timestamptz not null default now(),
    constraint sesiones_app_ambito_chk check (ambito in ('admin', 'red'))
);
create index if not exists sesiones_app_sujeto_idx on public.sesiones_app (ambito, sujeto);
create index if not exists sesiones_app_actividad_idx on public.sesiones_app (ultima_actividad);

comment on table public.sesiones_app is
  'Sesiones de la app (admin y red). Expiran a las 8 h o tras 30 min de inactividad; la app las valida en cada petición.';

-- Intentos fallidos / bloqueos temporales (por sujeto y por IP)
create table if not exists public.intentos_login (
    clave            text primary key,           -- '<ambito>:<sujeto|ip>:<valor>'
    intentos         integer not null default 0,
    ultimo_intento   timestamptz,
    bloqueado_hasta  timestamptz
);

-- Limpieza opcional de sesiones vencidas (ejecutar a mano o con pg_cron):
--   delete from public.sesiones_app
--    where inicio < now() - interval '8 hours' or ultima_actividad < now() - interval '30 minutes';
--   delete from public.intentos_login where coalesce(bloqueado_hasta, ultimo_intento) < now() - interval '1 day';

alter table public.sesiones_app   enable row level security;
alter table public.intentos_login enable row level security;

-- La app accede con su clave de servidor; estas políticas permiten operar
-- desde ella. Si se usa la clave `anon`, ajustar a los roles reales.
drop policy if exists sesiones_app_all on public.sesiones_app;
create policy sesiones_app_all on public.sesiones_app
    for all to anon, authenticated, service_role using (true) with check (true);

drop policy if exists intentos_login_all on public.intentos_login;
create policy intentos_login_all on public.intentos_login
    for all to anon, authenticated, service_role using (true) with check (true);

-- ------------------------------------------------------------
-- (b) LOGS: inmutables y con retención mínima de 90 días
-- ------------------------------------------------------------
create or replace function public.fn_logs_proteger()
returns trigger
language plpgsql
as $$
begin
    if tg_op = 'UPDATE' then
        raise exception 'La tabla logs es inmutable: no se permite UPDATE (id=%)', old.id
            using errcode = 'P0001';
    end if;
    if tg_op = 'DELETE' and old.fecha > now() - interval '90 days' then
        raise exception 'Retención de auditoría: no se pueden borrar logs con menos de 90 días (id=%, fecha=%)', old.id, old.fecha
            using errcode = 'P0001';
    end if;
    return old;
end;
$$;

drop trigger if exists trg_logs_proteger on public.logs;
create trigger trg_logs_proteger
    before update or delete on public.logs
    for each row execute function public.fn_logs_proteger();

create or replace function public.fn_logs_sin_truncate()
returns trigger
language plpgsql
as $$
begin
    raise exception 'La tabla logs no admite TRUNCATE' using errcode = 'P0001';
end;
$$;

drop trigger if exists trg_logs_sin_truncate on public.logs;
create trigger trg_logs_sin_truncate
    before truncate on public.logs
    for each statement execute function public.fn_logs_sin_truncate();

-- ============================================================
-- Verificación rápida (opcional):
--   update public.logs set detalle = 'x' where id = (select max(id) from public.logs);  -- debe fallar
--   delete from public.logs where id = (select max(id) from public.logs);               -- debe fallar
-- ============================================================
