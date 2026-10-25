# SIREA 3.2 · Lista de verificación con claves reales (40 minutos)

Hágala en orden antes de desplegar. Marque cada paso. Use el proyecto de Supabase **de demo**.

## Preparación (5 min)

- [ ] **1. SQL.** En Supabase → SQL Editor, pegar `sql/ACTUALIZAR_TODO_SIREA_3_2.sql` completo → Run. Al final todas
      las filas deben decir **OK** (lo nuevo de esta versión es `sql/54_sirea_3_2.sql`).
- [ ] **2. `.env`.** Copiar `.env.example` a `.env` y completar Supabase, Drive, correo, `GEMINI_API_KEY` y,
      si quiere respaldo, `GROQ_API_KEY`. Nuevo en 3.2 (opcional): `PATRONES_SEMANAS=8`, `PATRONES_MIN_SEMANAS=4`,
      `ASISTENTE_LIMITE_HORA=30`. Instalar dependencias de nuevo: `pip install -r requirements.txt` (agrega python-docx).
- [ ] **3. Arrancar.** `python -m streamlit run app.py` (o Docker). El pie debe decir **v3.2**.
- [ ] **4. Verificar.** `python verificar_despliegue.py` → las tablas `agente_*` deben salir en OK.

## Agente de IA (20 min)

- [ ] **5. Proveedores.** Entrar como `oiis.winepi` → **Agente de IA → Estado → Probar los proveedores**: Gemini (y Groq) en verde.
- [ ] **6. Evaluaciones.** Pestaña **Evaluaciones** → elegir «Seguimiento de redes» → **Correr las evaluaciones**.
      Debe mostrar «Sin IA» con 9/12 y «Con IA» con su puntaje. Si llega a 85 % o más, la compuerta dice **Habilitada**.
      Repetir con «Revisión de observaciones» (sin IA da 1/8). Si alguna queda bloqueada, abrir «Casos que la IA no
      resolvió» y anotar el motivo.
- [ ] **7. Activar.** Estado → **Activar la IA**. Si ninguna skill pasó, el agente operativo no se activa y lo explica.
- [ ] **8. Correr.** Pestaña **Corridas** → «Correr Seguimiento ahora». Debe terminar con N casos y M propuestas.
      Elegir la corrida y abrir un caso: se ve qué vio, qué consultó y qué propuso.
- [ ] **9. Bandeja.** Pestaña **Bandeja** → revisar una propuesta: centros pendientes, destinatario (lo pone el sistema),
      mensaje adicional. **Poner su propio correo** como destinatario y «Aprobar y enviar»: debe llegar el recordatorio
      oficial con la caja «Mensaje de la OIIS». Rechazar otra con un motivo.
- [ ] **10. Memoria.** Pestaña **Memoria** → agregar «La red X envía los jueves por falta de internet» a una red con centros
      pendientes → volver a correr: el agente debe proponer **no actuar** (o mencionarlo) para esa red.
- [ ] **11. Observaciones.** Si hay observaciones pendientes, correr «Revisión de observaciones» (si está habilitada).
      Estas propuestas solo las aprueba un SUPER_ADMIN.
- [ ] **11b. Centro de pendientes.** Agente de IA → **Pendientes**: debe listar las secciones con lo urgente primero.
      Pulse «Ir a …» en una tarjeta: debe abrir esa sección del panel.
- [ ] **11c. Notificaciones.** Con una sugerencia de recordatorio pendiente, abra **Notificaciones**: arriba aparece
      «Sugerencias del agente». Envíe un recordatorio **a mano** a una red y luego corra el seguimiento: el agente
      **no** debe proponer otro a esa red (descarta por «últimas 20 horas»).
- [ ] **11d. Aprender de los rechazos.** Rechace 3 propuestas de una skill con un motivo parecido. En **Skills** pulse
      «Proponer mejoras ahora»: aparece la versión 1.1.0 con las reglas nuevas. Apruébela: la skill queda **Bloqueada**
      hasta correr sus evaluaciones. Pruebe «Volver a la versión del repositorio».
- [ ] **11e. Historial para la demo (solo base DEMO).** `python scripts/sembrar_historial_demo.py --confirmo-base-demo`
      carga 10 semanas simuladas (marcadas DEMO-SIM; correos en example.org). Antes de producción:
      `python scripts/sembrar_historial_demo.py --confirmo-base-demo --borrar`.
- [ ] **11f. Patrones.** Agente de IA → **Patrones**: tabla por red (tarde o incompletas, lo que más falta, tendencia).
      Elija una red: se ven las semanas como prueba y lo que le falta por tipo. Marque una semana como **justificada**
      y pulse Actualizar: deja de contar.
- [ ] **11g. Recordatorio formal.** Corra «Seguimiento» y abra una propuesta en la **Bandeja**: debe mostrar «Lo que falta,
      por tipo de reporte», el recuadro «Solo para usted · no va en el correo», el responsable en «Para» y otros en copia.
      Abra **Vista previa del correo**. Ponga **su correo** en «Para», borre las copias y apruebe: el correo debe traer
      «Reportes pendientes por centro» y el párrafo formal.
- [ ] **11h. Informe semanal.** Pestaña **Informe semanal** → Preparar borrador → **Descargar borrador en PDF** (debe salir
      con logos, marca de agua de la OIIS y «BORRADOR») → elegir redacción (IA o sistema) → Aprobar → **Descargar PDF** (sin
      «BORRADOR», con quién lo validó) → Word → Enviar a su correo.
- [ ] **11i. Quipu.** En cualquier pantalla pulse **Quipu** (abajo a la derecha). Pruebe una pregunta sugerida, luego
      «¿Qué le falta a la red X?» y «¿Qué redes suelen atrasarse?». Pulse **Ampliar** y vuelva a achicar. Pregunte algo fuera
      de tema: debe negarse. Lo de atrás (filtros, texto escrito) no debe perderse.
- [ ] **11j. Filtros y refresco.** En **Panel de control** elija otra semana y una red; pase a **Seguimiento**: debe seguir
      la misma elección. Pulse **F5**: debe seguir dentro del panel, en la misma sección y semana. **Semana activa** la deshace.
- [ ] **11k. Notificaciones.** Elija una red: aparecen sus responsables del envío; al elegir uno se llenan nombre, apellido,
      correo y las copias.
- [ ] **12. Detención.** Gobernanza de IA → Encender y apagar → **Detener la IA**. Corridas y Bandeja deben quedar bloqueadas. Reactivar.
- [ ] **13. Historial de IA.** Gobernanza de IA → **Historial de IA** (filtre por función y descargue en Excel): deben verse BORRADOR (propuesta), APROBACION, ENVIO, RECHAZO y
      CAMBIO_ESTADO con la referencia `ACC‑n`.

## Seguridad (5 min)

- [ ] **14.** Cerrar sesión e intentar entrar 5 veces con una contraseña incorrecta: a la sexta debe bloquear aunque la
      contraseña sea correcta (tabla `intentos_login` con filas).

Si algo falla: el detalle técnico está en `storage/logs/` (nunca en pantalla). Anote el paso y el mensaje y envíelos
todos juntos en una sola lista.
