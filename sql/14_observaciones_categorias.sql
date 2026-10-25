-- ============================================================
-- 14_observaciones_categorias.sql   (v7.2)
--
-- Separa en «Observaciones» lo que escriben las redes de las fallas
-- técnicas del sistema (por ejemplo, Drive sin permiso para mover un
-- archivo): agrega el motivo FALLA y una columna `datos` con lo necesario
-- para reintentar la operación desde el panel.
--
-- Requiere haber ejecutado antes sql/13. Es OPCIONAL e idempotente: sin
-- esto todo funciona, pero las fallas aparecen mezcladas como «Reemplazo»
-- y no se puede reintentar. Ejecutar en el SQL Editor de Supabase.
-- ============================================================

alter table public.observaciones_envio
  add column if not exists datos jsonb null;

alter table public.observaciones_envio
  drop constraint if exists observaciones_envio_motivo_check;

alter table public.observaciones_envio
  add constraint observaciones_envio_motivo_check
  check (motivo in ('SUSTENTO','OBSERVADO','DUPLICADO','REEMPLAZO','FALLA'));

-- Las fallas que ya quedaron registradas como «Reemplazo» (v7.0/v7.1) pasan a FALLA.
update public.observaciones_envio
   set motivo = 'FALLA'
 where motivo = 'REEMPLAZO'
   and texto is null
   and detalle like 'No se pudo mover a REEMPLAZADOS%';
