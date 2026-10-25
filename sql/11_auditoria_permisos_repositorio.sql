-- ============================================================
-- 11_auditoria_permisos_repositorio.sql
--
-- Trazabilidad y control del repositorio de archivos (Drive):
--
--   auditoria_acciones     registro de quién hizo qué y cuándo. SOLO SE AÑADE:
--                          un disparador impide modificar o borrar filas, y cada
--                          fila lleva la huella (SHA-256) de la anterior, de modo
--                          que cualquier alteración se detecta al verificar la cadena.
--   permisos_operaciones   permisos que asigna ÚNICAMENTE el SUPER_ADMIN principal
--                          (descarga masiva, retiro del repositorio, respaldo
--                          manual y ver la auditoría), por persona, con alcance
--                          opcional por redes y fecha de vencimiento.
--   descargas_masivas      cada ZIP masivo preparado/descargado (con su huella).
--   solicitudes_retiro     retiros de archivos del repositorio: quién los pide,
--                          quién los aprueba y el resultado.
--   retiros_archivos       detalle archivo por archivo de cada retiro.
--
-- Es idempotente (IF NOT EXISTS / CREATE OR REPLACE): se puede correr varias veces.
-- Ejecutar en el SQL Editor de Supabase, DESPUES de 01 y 10.
-- ============================================================

-- ---------------------------------------------------------------- auditoría

create table if not exists public.auditoria_acciones (
  id bigserial primary key,
  ocurrio_en timestamp with time zone not null default now(),
  ocurrio_iso text not null,                   -- 'AAAA-MM-DD HH:MM:SS' (hora de Lima); entra en la huella
  usuario text not null,
  rol text null,
  accion text not null,
  categoria text not null default 'GENERAL',
  objeto text null,
  detalle text null,                           -- JSON en texto (exacto, para poder recalcular la huella)
  resultado text not null default 'OK',        -- OK | ERROR | RECHAZADO | PENDIENTE
  ip text null,
  hash_prev text not null,
  hash text not null
);

-- Una sola fila puede seguir a otra: evita que dos procesos bifurquen la cadena.
create unique index if not exists uq_auditoria_hash_prev on public.auditoria_acciones (hash_prev);
create index if not exists idx_auditoria_fecha on public.auditoria_acciones (ocurrio_iso desc);
create index if not exists idx_auditoria_usuario on public.auditoria_acciones (usuario, ocurrio_iso desc);
create index if not exists idx_auditoria_accion on public.auditoria_acciones (categoria, accion);

-- Solo se añade: ni siquiera la clave de servidor puede editar o borrar.
create or replace function public.auditoria_solo_anexar() returns trigger
language plpgsql as $$
begin
  raise exception 'auditoria_acciones es de solo escritura: no se permite % de filas', tg_op
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_auditoria_no_modificar on public.auditoria_acciones;
create trigger trg_auditoria_no_modificar
  before update or delete on public.auditoria_acciones
  for each row execute function public.auditoria_solo_anexar();

drop trigger if exists trg_auditoria_no_truncar on public.auditoria_acciones;
create trigger trg_auditoria_no_truncar
  before truncate on public.auditoria_acciones
  for each statement execute function public.auditoria_solo_anexar();

-- ---------------------------------------------------------------- permisos

create table if not exists public.permisos_operaciones (
  id bigserial primary key,
  usuario text not null,
  permiso text not null
    check (permiso in ('DESCARGA_MASIVA','RETIRO_REPOSITORIO','RESPALDO_MANUAL','VER_AUDITORIA')),
  redes text[] null,                           -- null = todas las redes
  vence_en timestamp with time zone null,      -- null = sin vencimiento
  activo boolean not null default true,
  nota text null,
  otorgado_por text not null,
  fecha_creacion timestamp with time zone not null default now(),
  revocado_por text null,
  fecha_revocacion timestamp with time zone null,
  motivo_revocacion text null
);

-- Un solo permiso vigente de cada tipo por persona.
create unique index if not exists uq_permisos_vigente
  on public.permisos_operaciones (usuario, permiso) where activo;
create index if not exists idx_permisos_usuario on public.permisos_operaciones (usuario, activo);

-- ---------------------------------------------------------------- descargas

create table if not exists public.descargas_masivas (
  id bigserial primary key,
  anio integer not null,
  semana integer not null,
  redes text[] not null default '{}',
  todas_las_redes boolean not null default false,
  incluye_duplicados boolean not null default false,
  parte integer not null default 1,
  total_partes integer not null default 1,
  nombre_zip text not null,
  n_envios integer not null default 0,
  n_archivos integer not null default 0,
  bytes bigint not null default 0,
  sha256 text null,
  envio_ids bigint[] not null default '{}',
  usuario text not null,
  usuario_nombre text null,
  rol text null,
  estado text not null default 'PREPARADA'
    check (estado in ('PREPARADA','DESCARGADA')),
  fecha_preparada timestamp with time zone not null default now(),
  fecha_descarga timestamp with time zone null,
  ip text null
);
create index if not exists idx_descargas_semana on public.descargas_masivas (anio, semana);

-- ---------------------------------------------------------------- retiros

create table if not exists public.solicitudes_retiro (
  id bigserial primary key,
  anio integer not null,
  semana integer not null,
  redes text[] not null default '{}',
  todas_las_redes boolean not null default false,
  envio_ids bigint[] not null default '{}',
  n_envios integer not null default 0,
  bytes_estimados bigint not null default 0,
  motivo_categoria text not null,
  motivo text not null,
  sin_descarga_previa boolean not null default false,
  definitivo boolean not null default false,   -- true = borrado definitivo (no va a la papelera)
  solicitado_por text not null,
  solicitado_nombre text null,
  rol_solicitante text null,
  estado text not null default 'PENDIENTE'
    check (estado in ('PENDIENTE','EJECUTADA','PARCIAL','ERROR','RECHAZADA','CANCELADA')),
  decidido_por text null,
  decidido_nombre text null,
  fecha_decision timestamp with time zone null,
  nota_decision text null,
  n_ok integer not null default 0,
  n_error integer not null default 0,
  fecha_creacion timestamp with time zone not null default now(),
  fecha_ejecucion timestamp with time zone null,
  ip text null
);
create index if not exists idx_retiro_estado on public.solicitudes_retiro (estado, fecha_creacion desc);

create table if not exists public.retiros_archivos (
  id bigserial primary key,
  solicitud_id bigint not null,
  envio_id bigint null,
  codigo_seguimiento text null,
  red text null,
  semana integer null,
  anio integer null,
  centros text null,
  drive_file_id text null,
  ruta_zip text null,
  resultado text not null default 'OK',        -- OK | ERROR
  detalle text null,
  fecha timestamp with time zone not null default now()
);
create index if not exists idx_retiros_solicitud on public.retiros_archivos (solicitud_id);
create index if not exists idx_retiros_envio on public.retiros_archivos (envio_id);

-- ---------------------------------------------------------------- seguridad

alter table public.auditoria_acciones enable row level security;
alter table public.permisos_operaciones enable row level security;
alter table public.descargas_masivas enable row level security;
alter table public.solicitudes_retiro enable row level security;
alter table public.retiros_archivos enable row level security;

revoke all on public.auditoria_acciones from anon, authenticated;
revoke all on public.permisos_operaciones from anon, authenticated;
revoke all on public.descargas_masivas from anon, authenticated;
revoke all on public.solicitudes_retiro from anon, authenticated;
revoke all on public.retiros_archivos from anon, authenticated;
revoke all on sequence public.auditoria_acciones_id_seq from anon, authenticated;
revoke all on sequence public.permisos_operaciones_id_seq from anon, authenticated;
revoke all on sequence public.descargas_masivas_id_seq from anon, authenticated;
revoke all on sequence public.solicitudes_retiro_id_seq from anon, authenticated;
revoke all on sequence public.retiros_archivos_id_seq from anon, authenticated;

-- A la auditoría el servidor solo le puede AÑADIR y LEER (nunca editar ni borrar).
revoke all on public.auditoria_acciones from service_role;
grant select, insert on public.auditoria_acciones to service_role;
grant all on public.permisos_operaciones to service_role;
grant all on public.descargas_masivas to service_role;
grant all on public.solicitudes_retiro to service_role;
grant all on public.retiros_archivos to service_role;
grant all on sequence public.auditoria_acciones_id_seq to service_role;
grant all on sequence public.permisos_operaciones_id_seq to service_role;
grant all on sequence public.descargas_masivas_id_seq to service_role;
grant all on sequence public.solicitudes_retiro_id_seq to service_role;
grant all on sequence public.retiros_archivos_id_seq to service_role;

-- Fin de 11_auditoria_permisos_repositorio.sql
