# tests/smoke_browser.py
"""
Recorre SIREA en un navegador automatizado (Playwright) contra la app
levantada con tests/smoke_app.py y reporta excepciones y fragmentos de HTML
visibles en cada pantalla del panel. Uso:

    python -m streamlit run tests/smoke_app.py --server.port 8599 --server.headless true &
    python tests/smoke_browser.py http://localhost:8599 [carpeta_capturas]
"""
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8599"
CAPS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
if CAPS:
    CAPS.mkdir(parents=True, exist_ok=True)

SECCIONES = ["Panel de control", "Seguimiento semanal", "Progreso por red", "Control de atrasos", "Control de duplicados",
             "Observaciones", "Informe por semana", "Descarga y limpieza", "Notificaciones", "Exclusión de centros", "Configuración",
             "Almacenamiento (Drive)", "Respaldos", "Administradores", "Solicitudes de contraseña", "Cuentas del panel",
             "Credenciales de red", "Historial y logs", "Control de actividad", "Permisos de operación"]
# SIREA 3.3: el orden importa (las rondas crean las propuestas de la Bandeja; los rechazos alimentan la mejora de procedimientos)
PASOS_IA = [("Gobernanza de IA", "Cómo funciona"), ("Gobernanza de IA", "Encender y apagar"), ("Gobernanza de IA", "Evaluaciones"),
            ("Gobernanza de IA", "Rondas del agente"),
            ("Agente de IA", "Pendientes"), ("Agente de IA", "Bandeja"), ("Agente de IA", "Patrones"), ("Agente de IA", "Informe semanal"),
            ("Gobernanza de IA", "Memoria"), ("Gobernanza de IA", "Procedimientos"), ("Gobernanza de IA", "Historial de IA")]

HTML_CRUDO = re.compile(r"</?(div|span|td|tr|table|ul|li|b|small|svg|p)\b[^>]*>")


def esperar(page, s=1.2):
    time.sleep(s)
    try:
        page.wait_for_selector("[data-testid='stStatusWidget']", state="detached", timeout=15000)
    except Exception:
        pass
    time.sleep(0.4)


def revisar(page, nombre, problemas):
    exc = page.locator("[data-testid='stException']").count()
    texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
    crudo = HTML_CRUDO.search(texto)
    if exc:
        problemas.append(f"{nombre}: {exc} excepción(es) de Streamlit")
    if "Oh no." in texto or "Error running app" in texto:
        problemas.append(f"{nombre}: error de ejecución")
    if "Ocurrió un error inesperado" in texto or "error inesperado" in texto.lower():
        problemas.append(f"{nombre}: la app mostró su mensaje de error controlado (ver storage/logs)")
    if crudo:
        problemas.append(f"{nombre}: HTML visible → {crudo.group(0)[:60]}")
    if CAPS:
        page.screenshot(path=str(CAPS / (re.sub(r'[^a-z0-9]+', '_', nombre.lower()) + ".png")), full_page=True)
    return not exc


def _clic(page, nombre_re, problemas, etiqueta, visitadas, espera=3):
    b = page.get_by_role("button", name=re.compile(nombre_re, re.I))
    habilitados = [b.nth(i) for i in range(b.count()) if b.nth(i).is_visible() and b.nth(i).is_enabled()]
    if habilitados:
        habilitados[0].click(); esperar(page, espera)
        revisar(page, etiqueta, problemas); visitadas.append(etiqueta)
        return True
    problemas.append(f"{etiqueta}: no se encontró el botón «{nombre_re}» habilitado")
    return False


def flujo_ia(page, tab, problemas, visitadas):
    try:
        if tab == "Encender y apagar":
            _clic(page, "Probar los proveedores", problemas, "IA · Estado · prueba de proveedores", visitadas)
        elif tab == "Pendientes":
            texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
            for t in ("Redes atrasadas", "Almacenamiento (Drive)", "Cierre de semana", "Respaldos"):
                if t.lower() not in texto.lower():
                    problemas.append(f"Pendientes: falta la sección {t}")
        elif tab == "Procedimientos":
            if _clic(page, "Proponer mejoras ahora", problemas, "IA · Skills · mejora propuesta", visitadas, 4):
                _clic(page, "Aprobar mejora", problemas, "IA · Skills · mejora aprobada", visitadas, 4)
                texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
                if "versión aprendida" not in texto.lower():
                    problemas.append("Skills: no se ve la versión aprendida tras aprobar")
        elif tab == "Evaluaciones":
            _clic(page, "Correr las evaluaciones", problemas, "IA · Evaluaciones · corridas", visitadas, 5)
            texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
            if "sin ia (reglas)" not in texto.lower() or "1/8" not in texto:
                problemas.append("Evaluaciones: no se ve la comparación con IA / sin IA")
        elif tab == "Rondas del agente":
            _clic(page, "Correr «Seguimiento", problemas, "IA · Corridas · seguimiento", visitadas, 5)
            _clic(page, "Correr «Revisión", problemas, "IA · Corridas · revisión", visitadas, 5)
            exp = page.locator("[data-testid='stExpander']:visible")
            if exp.count():
                exp.first.click(); esperar(page, 1)
                revisar(page, "IA · Corridas · traza", problemas); visitadas.append("IA · Corridas · traza")
        elif tab == "Bandeja":
            # solo los recordatorios: las propuestas sobre observaciones se revisan después en «Observaciones»
            page.get_by_text("Seguimiento de redes con centros pendientes", exact=True).first.click(); esperar(page, 1.5)
            texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
            if "Recordatorio a la red" not in texto:
                problemas.append("Bandeja: no aparecen los recordatorios propuestos")
            if "Lo que falta, por tipo de reporte" not in texto or "no va en el correo" not in texto.lower():
                problemas.append("Bandeja: falta el detalle por tipo o la información interna")
            vp = page.locator("[data-testid='stExpander']:visible").filter(has_text="Vista previa del correo")
            if vp.count():
                vp.first.click(); esperar(page, 1.5)
                if "Asunto:" not in page.locator("[data-testid='stAppViewContainer']").inner_text():
                    problemas.append("Bandeja: la vista previa del correo no muestra el asunto")
                revisar(page, "IA · Bandeja · vista previa", problemas); visitadas.append("IA · Bandeja · vista previa")
            else:
                problemas.append("Bandeja: no está la vista previa del correo")
            _clic(page, "Aprobar y enviar", problemas, "IA · Bandeja · aprobado", visitadas, 4)
            motivo = page.get_by_placeholder(re.compile("Por qué no", re.I))
            if motivo.count():
                motivo.first.fill("La red ya avisó por teléfono"); esperar(page, 1)
                _clic(page, "Rechazar$", problemas, "IA · Bandeja · rechazado", visitadas, 3)
            page.get_by_text("Todas", exact=True).last.click(); esperar(page, 1)
        elif tab == "Memoria":
            area = page.get_by_label("Nota", exact=True)
            if area.count():
                area.last.fill("La red avisó que envía los jueves por falta de internet en la sede.")
                _clic(page, "Agregar nota", problemas, "IA · Memoria · nota agregada", visitadas, 3)
        elif tab == "Patrones":
            texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
            for t in ("Suelen atrasarse", "Lo que más falta", "Tendencia"):
                if t.lower() not in texto.lower():
                    problemas.append(f"Patrones: falta «{t}»")
        elif tab == "Informe semanal":
            if _clic(page, "Preparar borrador", problemas, "IA · Informe · borrador", visitadas, 5):
                texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
                if "Borrador del informe" not in texto:
                    problemas.append("Informe: no aparece el borrador")
                _descargar_pdf(page, "Descargar borrador en PDF", problemas)
                if _clic(page, "Aprobar informe", problemas, "IA · Informe · aprobado", visitadas, 4):
                    texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
                    if "Informe aprobado" not in texto or "Descargar en Word" not in texto:
                        problemas.append("Informe: no se ve el informe aprobado con su descarga")
                    _descargar_pdf(page, "Descargar PDF$", problemas)
        elif tab == "Historial de IA":
            texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
            for t in ("Consultas", "Propuestas y borradores", "Qué pasó", "Descargar CSV"):
                if t.lower() not in texto.lower():
                    problemas.append(f"Historial de IA: falta «{t}»")
        elif tab == "Cómo funciona":
            texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
            if "Usted decide" not in texto:
                problemas.append("Gobernanza: no se ven los pasos de «Cómo funciona»")
    except Exception as e:  # noqa: BLE001
        problemas.append(f"flujo {tab}: {type(e).__name__}: {str(e)[:120]}")


def _descargar_pdf(page, nombre_re, problemas):
    b = page.get_by_role("button", name=re.compile(nombre_re, re.I))
    if not b.count():
        problemas.append(f"Informe: falta el botón «{nombre_re}»")
        return
    with page.expect_download(timeout=15000) as d:
        b.first.click()
    ruta = d.value.path()
    if not ruta or Path(ruta).read_bytes()[:5] != b"%PDF-":
        problemas.append("Informe: la descarga no es un PDF")
    elif CAPS:
        d.value.save_as(str(CAPS / d.value.suggested_filename))


def ir_a(page, s):
    loc = page.locator("[data-testid='stSidebar']").get_by_text(s, exact=True)
    if loc.count() == 0:
        loc = page.locator("[data-testid='stSidebar']").get_by_text(re.compile(re.escape(s), re.I))
    try:
        loc.first.scroll_into_view_if_needed(timeout=5000)
        loc.first.click(timeout=10000)
    except Exception:
        page.locator("[data-testid='stSidebar']").hover()
        page.mouse.wheel(0, 600); time.sleep(0.5)
        loc.first.click(timeout=15000)
    esperar(page, 2)


def elegir(page, contenedor, etiqueta, texto):
    """Elige una opción de un selectbox de Streamlit (por el inicio de su etiqueta) escribiendo y confirmando con Enter."""
    inp = contenedor.locator(f"input[role='combobox'][aria-label^='{etiqueta}']").first
    inp.click(); time.sleep(0.4)
    inp.fill(texto); time.sleep(0.6)
    opcion = page.get_by_role("option").filter(has_text=texto)
    if opcion.count():
        opcion.first.click()
    else:
        page.keyboard.press("Enter")
    esperar(page, 2)


def flujo_quipu(page, problemas, visitadas):
    try:
        fab = page.locator(".st-key-quipu_fab button")
        if not fab.count():
            problemas.append("Quipu: no está el botón flotante")
            return
        caja = fab.first.bounding_box() or {}
        if caja and (caja["x"] < 1100 or caja["y"] < 850):
            problemas.append(f"Quipu: el botón no está abajo a la derecha ({caja})")
        fab.first.click(); esperar(page, 1.5)
        panel = page.locator(".st-key-quipu_caja")
        if not panel.count():
            problemas.append("Quipu: no se abrió la cajita")
            return
        revisar(page, "Quipu · abierto", problemas); visitadas.append("Quipu · abierto")
        panel.get_by_role("button", name=re.compile("Qué redes faltan", re.I)).first.click(); esperar(page, 4)
        if "Situación" not in page.locator(".st-key-quipu_caja").inner_text():
            problemas.append("Quipu: no se ve la respuesta a la sugerencia")
        page.locator(".st-key-quipu_caja textarea").first.fill("¿Qué le falta a la red ANCASH?")
        page.locator(".st-key-quipu_caja").get_by_role("button", name=re.compile("Preguntar", re.I)).first.click(); esperar(page, 4)
        if page.locator(".st-key-quipu_caja .sirea-chat-u").count() < 2:
            problemas.append("Quipu: no se registró la segunda pregunta")
        revisar(page, "Quipu · respuesta", problemas); visitadas.append("Quipu · respuesta")
        page.locator(".st-key-quipu_tam button").first.click(); esperar(page, 1.5)
        grande = page.locator(".st-key-quipu_caja_grande")
        if not grande.count():
            problemas.append("Quipu: no se amplía")
        else:
            bb = grande.first.bounding_box() or {}
            if bb and bb.get("width", 0) < 600:
                problemas.append(f"Quipu: ampliado mide solo {bb.get('width')} px")
            revisar(page, "Quipu · ampliado", problemas); visitadas.append("Quipu · ampliado")
            page.locator(".st-key-quipu_tam button").first.click(); esperar(page, 1)
        page.locator(".st-key-quipu_fab button").first.click(); esperar(page, 1)
        if page.locator(".st-key-quipu_caja").count():
            problemas.append("Quipu: no se cierra")
    except Exception as e:  # noqa: BLE001
        problemas.append(f"Quipu: {type(e).__name__}: {str(e)[:120]}")


def flujo_filtro_y_f5(page, problemas, visitadas):
    """El filtro Año/Semana/Red se comparte entre módulos y sobrevive al refresco (F5), igual que la sesión y la sección."""
    try:
        ir_a(page, "Panel de control")
        main = page.locator("[data-testid='stMain']")
        elegir(page, main, "Semana", "Semana 37")
        texto = main.inner_text()
        if "Está viendo la semana 37/" not in texto:
            problemas.append("Filtro: el panel de control no cambió a la semana 37")
        revisar(page, "Filtro · panel en semana 37", problemas); visitadas.append("Filtro · panel semana 37")
        ir_a(page, "Seguimiento semanal")
        if "Está viendo la semana 37/" not in page.locator("[data-testid='stMain']").inner_text():
            problemas.append("Filtro: la semana elegida no se mantuvo en Seguimiento")
        page.reload(); esperar(page, 4)
        if page.get_by_text("Cerrar sesión").count() == 0:
            problemas.append("F5: el refresco sacó al usuario del panel")
        else:
            texto = page.locator("[data-testid='stMain']").inner_text()
            if "Seguimiento" not in texto:
                problemas.append("F5: no volvió a la misma sección")
            if "Está viendo la semana 37/" not in texto:
                problemas.append("F5: se perdió la semana elegida")
        revisar(page, "F5 · tras refrescar", problemas); visitadas.append("F5 · sesión y sección")
        b = page.get_by_role("button", name=re.compile("Semana activa$"))
        if b.count():
            b.first.click(); esperar(page, 2)
        if "Está viendo la semana 37/" in page.locator("[data-testid='stMain']").inner_text():
            problemas.append("Filtro: «Semana activa» no volvió a la semana activa")
    except Exception as e:  # noqa: BLE001
        problemas.append(f"Filtro/F5: {type(e).__name__}: {str(e)[:120]}")


def flujo_notificaciones(page, problemas, visitadas):
    """SIREA 3.3: al elegir una red, el sistema sugiere a sus responsables y llena el formulario."""
    try:
        ir_a(page, "Notificaciones")
        main = page.locator("[data-testid='stMain']")
        elegir(page, main, "Red", "ANCASH")
        elegir(page, main, "Responsables del envío", "example.org")
        correo = page.get_by_label("Correo electrónico").first.input_value()
        if "@example.org" not in correo:
            problemas.append(f"Notificaciones: no se llenó el correo del responsable ({correo!r})")
        revisar(page, "Notificaciones · responsable sugerido", problemas); visitadas.append("Notificaciones · autollenado")
        b = page.get_by_role("button", name=re.compile("Semana activa$"))
        if b.count():
            b.first.click(); esperar(page, 1)
        elegir(page, main, "Red", "Todas las redes")
    except Exception as e:  # noqa: BLE001
        problemas.append(f"Notificaciones (autollenado): {type(e).__name__}: {str(e)[:120]}")


def main():
    problemas, visitadas = [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(URL)
        esperar(page, 3)
        revisar(page, "Inicio", problemas); visitadas.append("Inicio")

        # Enviar reporte
        page.get_by_role("button", name=re.compile("Enviar reporte", re.I)).first.click()
        esperar(page, 2)
        revisar(page, "Enviar reporte", problemas); visitadas.append("Enviar reporte")
        page.get_by_role("button", name=re.compile("Volver al inicio|Inicio", re.I)).first.click()
        esperar(page, 2)

        # Portal de la red
        page.get_by_role("button", name=re.compile("progreso", re.I)).first.click()
        esperar(page, 2)
        revisar(page, "Portal de la red (acceso)", problemas); visitadas.append("Portal red")
        page.goto(URL); esperar(page, 2)

        # Panel de administración
        page.get_by_role("button", name=re.compile("Panel", re.I)).first.click()
        esperar(page, 2)
        revisar(page, "Acceso al panel", problemas); visitadas.append("Acceso panel")
        page.locator("input[type='text']").first.fill("oiis.winepi")
        page.locator("input[type='password']").first.fill("Sirea-Demo-2026!")
        page.keyboard.press("Enter")
        esperar(page, 3)
        if page.get_by_text("Cerrar sesión").count() == 0 and page.locator("input[type='password']").count():
            page.get_by_role("button", name=re.compile("Ingresar|Entrar|Iniciar", re.I)).first.click()
            esperar(page, 3)

        # SIREA 3.3: Quipu, el asistente de bolsillo flotante
        flujo_quipu(page, problemas, visitadas)

        for s in SECCIONES:
            try:
                ir_a(page, s)
                revisar(page, s, problemas); visitadas.append(s)
            except Exception as e:  # noqa: BLE001
                problemas.append(f"{s}: no se pudo abrir ({type(e).__name__}: {str(e)[:80]})")

        seccion_actual = None
        for sec, t in PASOS_IA:
            try:
                if sec != seccion_actual:
                    ir_a(page, sec); seccion_actual = sec
                    revisar(page, sec, problemas); visitadas.append(sec)
                tab = page.get_by_role("tab", name=re.compile(f"^{re.escape(t)}$"))
                if not tab.count():
                    problemas.append(f"{sec}: no se encontró la pestaña {t}")
                    continue
                tab.first.click(); esperar(page, 1.5)
                revisar(page, f"IA · {t}", problemas); visitadas.append(f"{sec} · {t}")
                flujo_ia(page, t, problemas, visitadas)
            except Exception as e:  # noqa: BLE001
                problemas.append(f"{sec} · {t}: {type(e).__name__}: {str(e)[:80]}")
        # Las sugerencias del agente aparecen en su sección (recordatorios → Notificaciones; observaciones → Observaciones)
        for sec in ("Notificaciones", "Observaciones"):
            try:
                ir_a(page, sec)
                revisar(page, f"{sec} · con sugerencias del agente", problemas); visitadas.append(f"{sec} · sugerencias")
                texto = page.locator("[data-testid='stAppViewContainer']").inner_text()
                if "Sugerencias del agente" not in texto:
                    problemas.append(f"{sec}: no aparecen las sugerencias del agente")
            except Exception as e:  # noqa: BLE001
                problemas.append(f"{sec}: {type(e).__name__}: {str(e)[:80]}")
        flujo_notificaciones(page, problemas, visitadas)
        flujo_filtro_y_f5(page, problemas, visitadas)
        b.close()
    print(f"Pantallas visitadas: {len(visitadas)}")
    for v in visitadas:
        print("  ·", v)
    print(f"Problemas: {len(problemas)}")
    for pr in problemas:
        print("  !!", pr)
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
