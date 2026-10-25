-- ============================================================
-- 09_solicitudes_cambio_password.sql
--
-- Crea las tablas del flujo "solicitud de cambio de contrasena":
-- despues del primer cambio (de la clave generica a una propia), una
-- red que quiera volver a cambiar su contrasena debe enviar un
-- sustento; un SUPER_ADMIN lo revisa en el panel, responde y, si lo
-- aprueba, se habilita el cambio de contrasena para esa red.
--
--   solicitudes_password            una fila por solicitud
--   solicitudes_password_mensajes   intercambio de mensajes (red <-> admin)
--
-- Es idempotente (IF NOT EXISTS): se puede correr varias veces.
-- Ejecutar en el SQL Editor de Supabase, DESPUES de 01 y 07.
-- ============================================================

create table if not exists public.solicitudes_password (
  id bigserial primary key,
  codigo text not null unique,
  red text not null,
  nombre text not null,
  correo text not null,
  estado text not null default 'PENDIENTE'
    check (estado in ('PENDIENTE','APROBADA','RECHAZADA','COMPLETADA','CANCELADA','VENCIDA')),
  fecha_creacion timestamp with time zone not null default now(),
  fecha_resolucion timestamp with time zone null,
  resuelto_por text null,
  fecha_vencimiento timestamp with time zone null,
  fecha_uso timestamp with time zone null
);

-- Una red solo puede tener UNA solicitud abierta (pendiente o aprobada) a la vez.
create unique index if not exists uq_solicitudes_password_abierta
  on public.solicitudes_password (red)
  where estado in ('PENDIENTE','APROBADA');

create index if not exists idx_solicitudes_password_estado
  on public.solicitudes_password (estado, fecha_creacion desc);

create table if not exists public.solicitudes_password_mensajes (
  id bigserial primary key,
  solicitud_id bigint not null references public.solicitudes_password(id) on delete cascade,
  autor_tipo text not null check (autor_tipo in ('RED','ADMIN','SISTEMA')),
  autor text not null,
  mensaje text not null,
  fecha timestamp with time zone not null default now()
);

create index if not exists idx_solicitudes_password_mensajes_sol
  on public.solicitudes_password_mensajes (solicitud_id, fecha);

-- Seguridad: igual que el resto de tablas, solo la clave service_role (servidor) accede.
alter table public.solicitudes_password enable row level security;
alter table public.solicitudes_password_mensajes enable row level security;

revoke all on public.solicitudes_password from anon, authenticated;
revoke all on public.solicitudes_password_mensajes from anon, authenticated;
revoke all on sequence public.solicitudes_password_id_seq from anon, authenticated;
revoke all on sequence public.solicitudes_password_mensajes_id_seq from anon, authenticated;

grant all on public.solicitudes_password to service_role;
grant all on public.solicitudes_password_mensajes to service_role;
grant all on sequence public.solicitudes_password_id_seq to service_role;
grant all on sequence public.solicitudes_password_mensajes_id_seq to service_role;

-- Fin de 09_solicitudes_cambio_password.sql
