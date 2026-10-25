-- ============================================================
-- 52_agente_operativo.sql  (SIREA 3.0)
-- Tablas del Agente Operativo: corridas (con traza paso a paso), cola de
-- acciones propuestas con aprobación humana, memoria por red y resultados
-- de las evaluaciones que habilitan cada skill.
--
-- Seguro de repetir. Ejecutar en el SQL Editor de Supabase después de
-- 50_auditoria_agentes_ia.sql.
-- ============================================================

-- 1) Corridas del agente (una por skill y disparo) ---------------------------
create table if not exists public.agente_corridas (
  id bigserial primary key,
  skill text not null,
  skill_version text not null,
  skill_hash text not null,
  disparo text not null default 'manual' check (disparo in ('manual', 'programado', 'evaluacion')),
  usuario text not null default 'SYSTEM',
  inicio timestamp with time zone not null default now(),
  fin timestamp with time zone null,
  estado text not null default 'EN_CURSO' check (estado in ('EN_CURSO', 'COMPLETADA', 'PARCIAL', 'FALLIDA', 'BLOQUEADA')),
  proveedor text null,
  n_casos integer not null default 0,
  n_propuestas integer not null default 0,
  n_descartadas integer not null default 0,
  n_sin_accion integer not null default 0,
  resumen text null,
  error text null
);
create index if not exists idx_agente_corridas_inicio on public.agente_corridas (inicio desc);

-- 2) Traza (observabilidad): qué vio, qué consultó y qué decidió en cada caso -
create table if not exists public.agente_traza (
  id bigserial primary key,
  corrida_id bigint not null references public.agente_corridas (id) on delete cascade,
  fecha timestamp with time zone not null default now(),
  caso text null,                       -- p. ej. 'red:PUNO' u 'observacion:123'
  tipo text not null check (tipo in ('CASO', 'HERRAMIENTA', 'PROPUESTA', 'DESCARTADA', 'SIN_ACCION', 'REGLA', 'ERROR')),
  detalle jsonb not null default '{}'::jsonb
);
create index if not exists idx_agente_traza_corrida on public.agente_traza (corrida_id, id);

-- 3) Cola de acciones propuestas (Human-in-the-loop) -------------------------
create table if not exists public.agente_acciones (
  id bigserial primary key,
  corrida_id bigint null references public.agente_corridas (id) on delete set null,
  skill text not null,
  skill_version text not null,
  tipo text not null,
  red text null,
  semana integer null,
  anio integer null,
  objetivo_ref text null,               -- p. ej. id de la observación
  clave_unica text not null,            -- evita proponer dos veces lo mismo mientras está abierta
  payload jsonb not null default '{}'::jsonb,
  justificacion text null,
  evidencia jsonb not null default '{}'::jsonb,
  origen text not null default 'ia' check (origen in ('ia', 'regla')),
  proveedor text null,
  estado text not null default 'PROPUESTA'
    check (estado in ('PROPUESTA', 'EJECUTADA', 'FALLIDA', 'RECHAZADA', 'VENCIDA')),
  creada_at timestamp with time zone not null default now(),
  decidida_por text null,
  decidida_at timestamp with time zone null,
  motivo_decision text null,
  editada boolean not null default false,
  ejecutada_at timestamp with time zone null,
  resultado text null
);
create unique index if not exists uq_agente_acciones_abierta
  on public.agente_acciones (clave_unica) where estado = 'PROPUESTA';
create index if not exists idx_agente_acciones_estado on public.agente_acciones (estado, creada_at desc);
create index if not exists idx_agente_acciones_red on public.agente_acciones (red, creada_at desc);

-- 4) Memoria por red (notas que el agente lee en cada corrida) ---------------
create table if not exists public.agente_memoria_red (
  id bigserial primary key,
  red text not null,
  nota text not null check (char_length(nota) <= 400),
  fuente text not null default 'humano' check (fuente in ('humano', 'agente')),
  accion_id bigint null,
  creada_por text not null default 'SYSTEM',
  creada_at timestamp with time zone not null default now(),
  vigente_hasta date null,
  activa boolean not null default true
);
create index if not exists idx_agente_memoria_red on public.agente_memoria_red (red, activa);

-- 5) Evaluaciones (compuerta de activación por versión de skill) -------------
create table if not exists public.agente_evals (
  id bigserial primary key,
  fecha timestamp with time zone not null default now(),
  skill text not null,
  skill_version text not null,
  skill_hash text not null,
  usuario text not null default 'SYSTEM',
  modo text not null default 'ia' check (modo in ('ia', 'sin_ia')),
  proveedor text null,
  total integer not null,
  aprobados integer not null,
  puntaje numeric(5, 4) not null,
  detalle jsonb not null default '[]'::jsonb
);
create index if not exists idx_agente_evals_skill on public.agente_evals (skill, skill_hash, fecha desc);

-- 6) Seguridad: solo la clave de servidor ----------------------------------
do $$
declare t text;
begin
  foreach t in array array['agente_corridas', 'agente_traza', 'agente_acciones', 'agente_memoria_red', 'agente_evals'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant all on public.%I to service_role', t);
    execute format('revoke all on sequence public.%I from anon, authenticated', t || '_id_seq');
    execute format('grant all on sequence public.%I to service_role', t || '_id_seq');
  end loop;
end $$;

-- La traza y las evaluaciones son evidencia: no se modifican ni se borran.
create or replace function public.fn_agente_evidencia_inmutable() returns trigger
language plpgsql as $$
begin
  raise exception 'La tabla % es evidencia del agente: no se permite % ', tg_table_name, tg_op;
end $$;

drop trigger if exists trg_agente_traza_inmutable on public.agente_traza;
create trigger trg_agente_traza_inmutable before update or delete on public.agente_traza
  for each row execute function public.fn_agente_evidencia_inmutable();

drop trigger if exists trg_agente_evals_inmutable on public.agente_evals;
create trigger trg_agente_evals_inmutable before update or delete on public.agente_evals
  for each row execute function public.fn_agente_evidencia_inmutable();

-- Estado inicial: el agente operativo nace INACTIVO (se activa desde el panel, tras pasar las evaluaciones).
insert into public.configuracion (clave, valor, fecha_actualizacion)
values ('agentes_ia_estado_operativo', 'INACTIVO', now())
on conflict (clave) do nothing;
