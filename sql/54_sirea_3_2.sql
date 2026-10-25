-- ============================================================
-- 54_sirea_3_2.sql  (SIREA 3.2)
-- 1) agente_atrasos_justificados: semanas en que un administrador indicó
--    que el atraso de una red tuvo una causa válida (feriado, caída del
--    sistema...). Esas semanas NO cuentan en los patrones de la red.
-- 2) agente_informes: informe semanal para la Jefatura. El sistema arma los
--    datos y un texto base; la IA propone una redacción verificada; una
--    persona elige, edita y APRUEBA. Un informe aprobado no se modifica ni se
--    borra (es evidencia).
--
-- Seguro de repetir. Ejecutar después de 53_skill_versiones.sql.
-- ============================================================

-- 1) Atrasos justificados ------------------------------------------------
create table if not exists public.agente_atrasos_justificados (
  id bigserial primary key,
  red text not null,
  anio integer not null,
  semana integer not null check (semana between 1 and 53),
  motivo text not null check (char_length(motivo) between 5 and 300),
  creado_por text not null default 'SYSTEM',
  creado_at timestamp with time zone not null default now(),
  activo boolean not null default true
);
create unique index if not exists uq_atraso_justificado_activo
  on public.agente_atrasos_justificados (red, anio, semana) where activo;
create index if not exists idx_atraso_justificado_red on public.agente_atrasos_justificados (red, anio, semana);

alter table public.agente_atrasos_justificados enable row level security;
revoke all on public.agente_atrasos_justificados from anon, authenticated;
grant all on public.agente_atrasos_justificados to service_role;
revoke all on sequence public.agente_atrasos_justificados_id_seq from anon, authenticated;
grant all on sequence public.agente_atrasos_justificados_id_seq to service_role;

-- Una justificación no se borra: se desactiva (queda quién y por qué).
create or replace function public.fn_atraso_justificado_sin_borrar() returns trigger
language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Las justificaciones de atraso no se borran: desactívelas (activo = false).';
  end if;
  if new.red is distinct from old.red or new.anio is distinct from old.anio or new.semana is distinct from old.semana
     or new.motivo is distinct from old.motivo or new.creado_por is distinct from old.creado_por then
    raise exception 'Una justificación no se edita: desactívela y registre otra.';
  end if;
  return new;
end $$;

drop trigger if exists trg_atraso_justificado_sin_borrar on public.agente_atrasos_justificados;
create trigger trg_atraso_justificado_sin_borrar before update or delete on public.agente_atrasos_justificados
  for each row execute function public.fn_atraso_justificado_sin_borrar();

-- 2) Informes semanales ---------------------------------------------------
create table if not exists public.agente_informes (
  id bigserial primary key,
  anio integer not null,
  semana integer not null check (semana between 1 and 53),
  estado text not null default 'BORRADOR' check (estado in ('BORRADOR', 'APROBADO', 'DESCARTADO')),
  datos jsonb not null default '{}'::jsonb,     -- cifras calculadas por el sistema (sin IA)
  texto_sistema text not null,                  -- texto base del sistema (sin IA)
  texto_ia text null,                           -- redacción de la IA que pasó los controles (o null)
  origen_sugerido text not null default 'sistema' check (origen_sugerido in ('ia', 'sistema')),
  proveedor text null,
  nota_ia text null,                            -- por qué no hay redacción de la IA, si no la hay
  creado_por text not null default 'SYSTEM',
  creado_at timestamp with time zone not null default now(),
  texto_final text null,                        -- lo que aprobó la persona (editado o no)
  origen_final text null check (origen_final in ('ia', 'sistema')),
  editado boolean null,
  aprobado_por text null,                       -- quién aprobó o descartó
  aprobado_at timestamp with time zone null,
  motivo_descarte text null
);
create index if not exists idx_informes_semana on public.agente_informes (anio, semana, estado);
create index if not exists idx_informes_fecha on public.agente_informes (creado_at desc);

alter table public.agente_informes enable row level security;
revoke all on public.agente_informes from anon, authenticated;
grant all on public.agente_informes to service_role;
revoke all on sequence public.agente_informes_id_seq from anon, authenticated;
grant all on sequence public.agente_informes_id_seq to service_role;

-- Los datos y los textos propuestos son evidencia; un informe decidido ya no cambia.
create or replace function public.fn_informe_inmutable() returns trigger
language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Los informes semanales son evidencia: no se borran (descarte el borrador).';
  end if;
  if new.datos is distinct from old.datos or new.texto_sistema is distinct from old.texto_sistema
     or new.texto_ia is distinct from old.texto_ia or new.anio is distinct from old.anio or new.semana is distinct from old.semana then
    raise exception 'Los datos y los textos propuestos de un informe no se modifican: prepare un borrador nuevo.';
  end if;
  if old.estado <> 'BORRADOR' then
    raise exception 'Un informe ya aprobado o descartado no se modifica: prepare uno nuevo.';
  end if;
  return new;
end $$;

drop trigger if exists trg_informe_inmutable on public.agente_informes;
create trigger trg_informe_inmutable before update or delete on public.agente_informes
  for each row execute function public.fn_informe_inmutable();

-- Que las tablas que se creen después también queden accesibles.
alter default privileges in schema public grant all on tables    to service_role;
alter default privileges in schema public grant all on sequences to service_role;
alter default privileges in schema public grant all on functions to service_role;
