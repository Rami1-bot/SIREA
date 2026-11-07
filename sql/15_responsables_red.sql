-- ============================================================
-- 15_responsables_red.sql   (v7.4)
--
-- Responsables (encargados) de cada red para autocompletar los datos del
-- destinatario en «Notificaciones». Guarda a quienes el panel marcó con
-- «Guardar como responsable de la red».
--
-- Es OPCIONAL e idempotente: sin esta tabla «Notificaciones» sigue
-- funcionando y propone igualmente a las personas que ya enviaron reportes
-- (nombre y correo de sus envíos anteriores); solo no se pueden guardar
-- responsables aparte. Ejecutar en el SQL Editor de Supabase.
-- ============================================================

create table if not exists public.responsables_red (
  id bigserial primary key,
  red text not null,
  nombre text not null default '',
  apellido text not null default '',
  correo text not null,                       -- siempre en minúsculas
  telefono text null,
  activo boolean not null default true,
  creado_por text null,
  fecha_creacion timestamp with time zone not null default now(),
  fecha_actualizacion timestamp with time zone not null default now(),
  constraint uq_responsables_red_correo unique (red, correo)
);

create index if not exists idx_responsables_red_red
  on public.responsables_red (red, activo);

alter table public.responsables_red enable row level security;
revoke all on public.responsables_red from anon, authenticated;
revoke all on sequence public.responsables_red_id_seq from anon, authenticated;
grant all on public.responsables_red to service_role;
grant all on sequence public.responsables_red_id_seq to service_role;

-- Fin de 15_responsables_red.sql
