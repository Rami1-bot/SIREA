# src/agentes/__init__.py
"""
IA de SIREA 3.0 (Sistema de Recepción de Reportes Epidemiológicos con
Agentes · OIIS · EsSalud). Gemini como proveedor principal y Groq como
respaldo, detrás de una misma capa (`proveedores`), con los mismos
guardrails, auditoría y supervisión humana.

Agentes (ver `estado.CATALOGO`, semáforo de usos):
- agente_investigador   🟢 diagnóstico de cumplimiento, solo lectura, tool-use multipaso.
- agente_operativo      🟢/🟡 harness con skills: propone acciones, una persona aprueba, el sistema ejecuta.
- soporte_redes         🔴 evaluado y no construido.
- resumen, control, solicitudes  ⚪ retirados por proporcionalidad (solo catálogo y auditoría histórica).

Piezas del Agente Operativo:
- skills/*.md   procedimientos aprobados por la OIIS (versión + huella SHA-256).
- skills        carga y valida las skills.
- acciones      catálogo de acciones con esquema fijo, validación y ejecución.
- memoria       notas por red que el agente lee en cada corrida.
- evals         casos de prueba (casos_eval/*.json), modo IA vs sin IA, compuerta de activación.

Módulos transversales:
- proveedores   Gemini → Groq, herramientas en formato neutro, registro de quién respondió.
- guardrails    filtros determinísticos de entrada/salida, PII, inyección.
- auditoria     registro inmutable de cada interacción y decisión humana.
- estado        catálogo, clasificación, ciclo de vida y kill-switch (fail-closed).
- herramientas  funciones de SOLO LECTURA sobre datos agregados (sin PII).
- cliente_ia    cliente Gemini con reintentos y cadena de modelos de respaldo.
"""
