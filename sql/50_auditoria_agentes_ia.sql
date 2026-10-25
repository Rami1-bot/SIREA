-- ============================================================
-- 50_auditoria_agentes_ia.sql  (antes 001 en SIGRE)
-- Registro INMUTABLE de auditoría de los agentes de IA + estado inicial
-- del kill-switch.
--
-- Cumple: Informe EsSalud, Tabla 3.1 Riesgo 3 ("Módulo de Registro
-- activado antes de cualquier etapa experimental; captura inmutable de
-- usuario, hora, consulta, modelo, borrador y aprobación") y Tabla 4.2.1
-- ("Logs Auditables", "Mecanismo de Detención").
--
-- Ejecutar UNA vez en el SQL Editor de Supabase (proyecto DEMO).
-- ============================================================

-- 1) Tabla de auditoría -------------------------------------------------
create table if not exists public.auditoria_agentes_ia (
    id                  bigint generated always as identity primary key,
    fecha               timestamptz not null default now(),
    usuario             text        not null,           -- identificador institucional del admin
    rol                 text        not null,
    agente              text        not null,           -- orquestador | resumen | seguimiento | sistema
    evento              text        not null,           -- CONSULTA | BORRADOR | APROBACION | RECHAZO | ENVIO | BLOQUEO_GUARDRAIL | CAMBIO_ESTADO | ERROR
    modelo              text,                           -- modelo Gemini realmente usado
    entrada             text,                           -- consulta / datos de entrada (PII ya redactada)
    entrada_hash        text,                           -- sha256 corto de la entrada original
    salida              text,                           -- respuesta o borrador (PII ya redactada)
    herramientas        jsonb       not null default '[]'::jsonb,  -- function-calls ejecutadas
    guardrail_categoria text,
    guardrail_motivo    text,
    observaciones       jsonb       not null default '[]'::jsonb,  -- p.ej. cifras no verificadas
    aprobado_por        text,
    referencia          text,                           -- id del borrador que aprueba/envía
    duracion_ms         integer,
    anio                integer,
    semana              integer,
    constraint auditoria_agentes_ia_evento_chk check (
        evento in ('CONSULTA','BORRADOR','APROBACION','RECHAZO','ENVIO',
                   'BLOQUEO_GUARDRAIL','CAMBIO_ESTADO','ERROR')
    )
);

create index if not exists auditoria_agentes_ia_fecha_idx   on public.auditoria_agentes_ia (fecha desc);
create index if not exists auditoria_agentes_ia_agente_idx  on public.auditoria_agentes_ia (agente, evento);
create index if not exists auditoria_agentes_ia_usuario_idx on public.auditoria_agentes_ia (usuario);

comment on table public.auditoria_agentes_ia is
  'Registro inmutable (solo INSERT) de todas las interacciones con los agentes de IA. Ley 31814 / DS 115-2025-PCM: trazabilidad.';

-- 2) Inmutabilidad: trigger que rechaza UPDATE y DELETE -------------------
create or replace function public.fn_auditoria_ia_inmutable()
returns trigger
language plpgsql
as $$
begin
    raise exception 'auditoria_agentes_ia es inmutable: no se permite % (id=%)', tg_op, coalesce(old.id, -1)
        using errcode = 'P0001';
end;
$$;

drop trigger if exists trg_auditoria_ia_inmutable on public.auditoria_agentes_ia;
create trigger trg_auditoria_ia_inmutable
    before update or delete on public.auditoria_agentes_ia
    for each row execute function public.fn_auditoria_ia_inmutable();

-- También se bloquea el TRUNCATE (es a nivel de sentencia).
create or replace function public.fn_auditoria_ia_sin_truncate()
returns trigger
language plpgsql
as $$
begin
    raise exception 'auditoria_agentes_ia es inmutable: TRUNCATE no permitido' using errcode = 'P0001';
end;
$$;

drop trigger if exists trg_auditoria_ia_sin_truncate on public.auditoria_agentes_ia;
create trigger trg_auditoria_ia_sin_truncate
    before truncate on public.auditoria_agentes_ia
    for each statement execute function public.fn_auditoria_ia_sin_truncate();

-- 3) RLS: solo INSERT y SELECT --------------------------------------------
alter table public.auditoria_agentes_ia enable row level security;

drop policy if exists auditoria_ia_insert on public.auditoria_agentes_ia;
create policy auditoria_ia_insert on public.auditoria_agentes_ia
    for insert to anon, authenticated, service_role
    with check (true);

drop policy if exists auditoria_ia_select on public.auditoria_agentes_ia;
create policy auditoria_ia_select on public.auditoria_agentes_ia
    for select to anon, authenticated, service_role
    using (true);

-- Sin política de UPDATE/DELETE => denegado por RLS; además el trigger lo
-- rechaza aunque se use la service_role key.
revoke update, delete, truncate on public.auditoria_agentes_ia from anon, authenticated;

-- 4) Estado inicial del kill-switch ---------------------------------------
-- FAIL-CLOSED: los agentes arrancan INACTIVOS. Un SUPER_ADMIN debe
-- activarlos explícitamente desde el panel "Agentes IA" (Tabla 4.2.2:
-- autoridad de activación = Jefatura de la OIIS).
-- (el upsert desde la app requiere unicidad en `clave`)
create unique index if not exists configuracion_clave_uidx on public.configuracion (clave);

insert into public.configuracion (clave, valor, fecha_actualizacion)
values ('agentes_ia_estado', 'INACTIVO', now())
on conflict (clave) do nothing;

-- ============================================================
-- Verificación rápida (opcional):
--   select * from public.auditoria_agentes_ia order by fecha desc limit 5;
--   update public.auditoria_agentes_ia set salida = 'x' where id = 1;  -- debe fallar
-- ============================================================
