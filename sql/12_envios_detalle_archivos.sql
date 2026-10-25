-- ============================================================
-- 12 · Detalle por archivo de cada envío (v6.8)
-- ============================================================
-- Guarda, por cada archivo del ZIP: centro, código, tipo (c/e/h),
-- semana, año y huella SHA-256 (NUNCA el contenido). Sirve para:
--   · detectar duplicados por centro + tipo + semana + año, y separar
--     en un mismo ZIP lo nuevo de lo ya recibido;
--   · avisar si un archivo es idéntico a uno enviado en otra semana.
--
-- Es OPCIONAL y seguro: el sistema funciona sin esta columna (usa el
-- centro y tipo del formulario como respaldo), pero con ella la
-- detección es exacta. Se puede ejecutar varias veces.
-- Ejecutar en Supabase > SQL Editor.

ALTER TABLE public.envios
    ADD COLUMN IF NOT EXISTS detalle_archivos jsonb;

COMMENT ON COLUMN public.envios.detalle_archivos IS
    'Por archivo: centro, codigo, tipo, semana, anio, sha256 (sin contenido).';
