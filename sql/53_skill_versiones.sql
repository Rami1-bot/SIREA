-- ============================================================
-- 53_skill_versiones.sql  (SIREA 3.1)
-- Versiones de las skills propuestas por el agente a partir de los
-- rechazos de las personas ("aprender de los rechazos").
--
-- Flujo: el agente PROPONE una versión (agrega "ajustes aprendidos" al
-- procedimiento) -> un SUPER_ADMIN la APRUEBA o la RECHAZA -> la versión
-- aprobada tiene otra huella, así que debe volver a pasar las evaluaciones
-- antes de operar. El texto de cada versión no se edita (solo cambia su
-- estado). Sin esta tabla, el agente usa las skills del repositorio.
--
-- Seguro de repetir. Ejecutar después de 52_agente_operativo.sql.
-- ============================================================

create table if not exists public.agente_skill_versiones (
  id bigserial primary key,
  skill text not null,
  version text not null,
  version_base text not null,           -- versión sobre la que se propuso
  huella text not null,                 -- SHA-256 del texto completo
  texto text not null,                  -- la skill completa (encabezado + procedimiento)
  ajustes jsonb not null default '[]'::jsonb,   -- [{regla, por_que}] agregados
  evidencia jsonb not null default '{}'::jsonb, -- diagnóstico y rechazos usados
  origen text not null default 'mejora_ia' check (origen in ('mejora_ia', 'manual')),
  proveedor text null,
  estado text not null default 'PROPUESTA'
    check (estado in ('PROPUESTA', 'APROBADA', 'RECHAZADA', 'REEMPLAZADA')),
  creada_at timestamp with time zone not null default now(),
  creada_por text not null default 'SYSTEM',
  decidida_por text null,
  decidida_at timestamp with time zone null,
  motivo_decision text null
);
create index if not exists idx_skill_versiones on public.agente_skill_versiones (skill, estado, creada_at desc);
-- Solo una versión aprobada vigente por skill.
create unique index if not exists uq_skill_version_aprobada
  on public.agente_skill_versiones (skill) where estado = 'APROBADA';

alter table public.agente_skill_versiones enable row level security;
revoke all on public.agente_skill_versiones from anon, authenticated;
grant all on public.agente_skill_versiones to service_role;
revoke all on sequence public.agente_skill_versiones_id_seq from anon, authenticated;
grant all on sequence public.agente_skill_versiones_id_seq to service_role;

-- El texto, la huella y la evidencia de una versión no cambian nunca; solo su estado y la decisión.
create or replace function public.fn_skill_version_texto_fijo() returns trigger
language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Las versiones de skills son evidencia: no se borran.';
  end if;
  if new.texto is distinct from old.texto or new.huella is distinct from old.huella
     or new.evidencia is distinct from old.evidencia or new.skill is distinct from old.skill
     or new.version is distinct from old.version then
    raise exception 'El texto de una versión de skill no se modifica: proponga una versión nueva.';
  end if;
  return new;
end $$;

drop trigger if exists trg_skill_version_texto_fijo on public.agente_skill_versiones;
create trigger trg_skill_version_texto_fijo before update or delete on public.agente_skill_versiones
  for each row execute function public.fn_skill_version_texto_fijo();
