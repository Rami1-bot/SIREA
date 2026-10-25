# src/email_sender.py
"""
Gestión de envío de correos electrónicos vía SMTP.
Permite enviar acuses de recibo, notificaciones y alertas.
"""

import smtplib
import ssl
import html
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.utils import formatdate
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

from src.config import Config
from utils.helpers import formatear_fecha
from src import email_plantillas as P


# Caracteres de fin de línea (CR / LF). Un valor que termine en manos
# de un encabezado de correo (To/Cc/Bcc/Subject/From) NUNCA debe
# contener uno de estos: es la técnica clásica de "email header
# injection" para inyectar encabezados o destinatarios adicionales
# (incluido Bcc) que el remitente no autorizó. La librería estándar
# `email` no lo bloquea por sí sola al hacer `msg['Header'] = valor`.
_PATRON_CRLF = re.compile(r'[\r\n]')


def _sanitizar_valor_header(valor: str) -> str:
    """Elimina CR/LF de un valor antes de usarlo como encabezado de correo."""
    if not valor:
        return valor
    return _PATRON_CRLF.sub(' ', str(valor)).strip()


def _escapar_html(valor) -> str:
    """
    Escapa un valor para insertarlo de forma segura dentro del cuerpo
    HTML de un correo. Los datos que arman estos correos (nombre,
    correo, red, centros, observaciones) se originan -directa o
    indirectamente- en formularios que llena el usuario o el
    administrador, así que nunca se insertan crudos en el HTML.
    """
    if valor is None:
        return ""
    return html.escape(str(valor), quote=True)


class EmailSender:
    """
    Gestor de envío de correos electrónicos.
    """
    
    def __init__(self):
        """Inicializa el gestor de correos con configuración SMTP."""
        self.smtp_server = Config.SMTP_SERVER
        self.smtp_port = Config.SMTP_PORT
        self.remitente = Config.EMAIL_REMITENTE
        self.password = Config.EMAIL_PASSWORD
        self.nombre_mostrar = Config.EMAIL_NOMBRE_MOSTRAR
        self.reply_to = getattr(Config, 'EMAIL_REPLY_TO', '')
        self.use_tls = Config.SMTP_USE_TLS
        self.use_ssl = Config.SMTP_USE_SSL
    
    def _crear_servidor_smtp(self):
        """
        Crea la conexión SMTP según la configuración.
        """
        if self.use_ssl:
            context = ssl.create_default_context()
            server = smtplib.SMTP_SSL(
                self.smtp_server,
                self.smtp_port,
                context=context,
                timeout=30
            )
        else:
            server = smtplib.SMTP(
                self.smtp_server,
                self.smtp_port,
                timeout=30
            )
            
            if self.use_tls:
                server.starttls()
        
        return server
    
    def _iniciar_sesion(self, server):
        """
        Inicia sesion en el servidor SMTP.

        Gmail responde 535 (credenciales rechazadas) a AUTH PLAIN y luego
        CIERRA la conexion cuando smtplib reintenta con AUTH LOGIN, lo que
        terminaba mostrandose como "Connection unexpectedly closed" y
        ocultaba la causa real. Limitando el intento a PLAIN, el rechazo
        llega como SMTPAuthenticationError y se informa correctamente.
        """
        server.ehlo_or_helo_if_needed()
        metodos = server.esmtp_features.get('auth', '').split()
        if 'PLAIN' in metodos:
            server.esmtp_features['auth'] = 'PLAIN'
        server.login(self.remitente, self.password)

    def _enviar_correo(
        self,
        destinatario: str,
        asunto: str,
        cuerpo_html: str,
        cuerpo_plano: Optional[str] = None,
        adjuntos: Optional[List[Tuple[str, bytes, str]]] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """
        Envía un correo electrónico.
        """
        try:
            # Ningún valor que vaya a un encabezado (To/Cc/Bcc/Subject/From)
            # puede contener un salto de línea -- ver _sanitizar_valor_header.
            # Esto es defensa en profundidad: aunque los formularios que
            # alimentan estos correos ya validan su entrada, un encabezado
            # de correo nunca debería confiar únicamente en la validación
            # de la capa de arriba.
            destinatario = _sanitizar_valor_header(destinatario)
            asunto = _sanitizar_valor_header(asunto)
            nombre_mostrar = _sanitizar_valor_header(self.nombre_mostrar)
            cc = [_sanitizar_valor_header(c) for c in cc] if cc else None
            bcc = [_sanitizar_valor_header(b) for b in bcc] if bcc else None

            if not destinatario or '@' not in destinatario:
                return False, f"Destinatario inválido: {destinatario}"

            if cuerpo_plano is None:
                cuerpo_plano = "Por favor, active HTML para ver este correo."

            # Estructura MIME: related( alternative(texto, html) + imagenes
            # CID ). Solo si hay adjuntos se envuelve en 'mixed'.
            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText(cuerpo_plano, 'plain', 'utf-8'))
            alt.attach(MIMEText(cuerpo_html, 'html', 'utf-8'))

            msg = MIMEMultipart('related')
            msg.attach(alt)
            for cid, ruta in P.imagenes_usadas(cuerpo_html):
                try:
                    with open(ruta, 'rb') as f:
                        img = MIMEImage(f.read(), _subtype='png')
                except OSError:
                    continue
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline', filename=ruta.name)
                msg.attach(img)

            if adjuntos:
                raiz = MIMEMultipart('mixed')
                raiz.attach(msg)
                for nombre_archivo, contenido, mimetype in adjuntos:
                    adjunto = MIMEApplication(contenido, _subtype=mimetype.split('/')[-1])
                    adjunto.add_header(
                        'Content-Disposition',
                        'attachment',
                        filename=nombre_archivo
                    )
                    raiz.attach(adjunto)
                msg = raiz

            msg['From'] = f"{nombre_mostrar} <{self.remitente}>"
            msg['To'] = destinatario
            msg['Subject'] = asunto
            reply_to = _sanitizar_valor_header(self.reply_to or '')
            if reply_to and '@' in reply_to:
                msg['Reply-To'] = reply_to
            # Cabecera Date valida (RFC 5322, con zona). Antes salia sin zona
            # horaria, algo que los filtros anti-spam penalizan.
            msg['Date'] = formatdate(localtime=True)

            if cc:
                msg['Cc'] = ', '.join(cc)
            if bcc:
                msg['Bcc'] = ', '.join(bcc)

            server = self._crear_servidor_smtp()
            
            try:
                self._iniciar_sesion(server)
                
                destinatarios = [destinatario]
                if cc:
                    destinatarios.extend(cc)
                if bcc:
                    destinatarios.extend(bcc)
                
                server.send_message(msg, from_addr=self.remitente, to_addrs=destinatarios)
                
                return True, "Correo enviado exitosamente"
            finally:
                # Si la conexion ya se cayo, quit() lanza otra excepcion
                # ("please run connect() first") que ocultaba el error real.
                try:
                    server.quit()
                except Exception:
                    server.close()
            
        except smtplib.SMTPAuthenticationError:
            return False, "Error de autenticación SMTP. Verifique credenciales."
        except smtplib.SMTPException as e:
            return False, f"Error SMTP: {str(e)}"
        except Exception as e:
            return False, f"Error al enviar correo: {str(e)}"
    
    def _obtener_info_anio_epidemiologico(self, anio: int) -> Dict:
        """
        Obtiene información del año epidemiológico desde la base de datos.
        """
        try:
            from src.db_manager import get_db_manager
            db_manager = get_db_manager()
            anio_data = db_manager.obtener_anio_epidemiologico(anio)
            if anio_data:
                return {
                    'semanas': anio_data.get('semanas', 52),
                    'fecha_inicio': anio_data.get('fecha_inicio', ''),
                    'fecha_fin': anio_data.get('fecha_fin', ''),
                    'activo': anio_data.get('activo', 0) == 1
                }
        except:
            pass
        
        # Fallback: calcular datos básicos
        semanas = 52
        primer_dia = datetime(anio, 1, 1)
        if primer_dia.weekday() == 3 or (primer_dia.weekday() == 2 and (anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0))):
            semanas = 53
        
        fecha_inicio = datetime(anio, 1, 1)
        while fecha_inicio.weekday() != 6:
            fecha_inicio = fecha_inicio + timedelta(days=1)
        
        fecha_fin = fecha_inicio + timedelta(days=(semanas - 1) * 7)
        
        return {
            'semanas': semanas,
            'fecha_inicio': fecha_inicio.strftime('%Y-%m-%d'),
            'fecha_fin': fecha_fin.strftime('%Y-%m-%d'),
            'activo': False
        }
    
    def _capitalizar_nombre(self, nombre: str) -> str:
        """
        Capitaliza correctamente un nombre o apellido.
        Ejemplo: "CArol" -> "Carol", "TtITo" -> "Ttito"
        """
        if not nombre or not isinstance(nombre, str):
            return ""
        
        nombre = nombre.strip()
        if not nombre:
            return ""
        
        # Capitalizar cada palabra (también cuando todo viene en mayúsculas:
        # antes "MARIA QUISPE" quedaba como "Maria quispe").
        palabras = nombre.split()
        palabras_capitalizadas = []
        for palabra in palabras:
            if palabra:
                # Capitalizar primera letra, el resto en minúsculas
                palabras_capitalizadas.append(palabra[0].upper() + palabra[1:].lower())
        
        return " ".join(palabras_capitalizadas)
    
    # ============================================================
    # MÉTODOS PÚBLICOS - TIPOS DE CORREO
    # ============================================================
    #
    # El color de la cabecera indica el estado: azul (normal o
    # preventivo), rojo (envío tardío) y ámbar (solicitud de corrección
    # u observación). Las piezas HTML viven en src/email_plantillas.py.

    def enviar_acuse_recibo(
        self,
        destinatario: str,
        nombre_usuario: str,
        red: str,
        centros: List[str],
        semana: int,
        tipos_reporte: List[str],
        cantidad_archivos: int,
        codigo_seguimiento: str,
        estado: str = "APROBADO",
        observacion: Optional[str] = None,
        anio: Optional[int] = None,
        fecha_envio: Optional[datetime] = None,
        semana_actual: Optional[int] = None,
        anio_actual: Optional[int] = None,
        fecha_corte: Optional[datetime] = None,
        dias_atraso: int = 0,
        es_duplicado: bool = False,
        codigos_previos: Optional[List[str]] = None,
        sustento: str = ""
    ) -> Tuple[bool, str]:
        """
        Envía el acuse de recibo al usuario: azul si llegó a tiempo, rojo si
        fue tardío, ámbar si quedó con observaciones y naranja si el envío
        repite un centro ya enviado esa semana (duplicado).
        """
        if fecha_envio is None:
            fecha_envio = Config.obtener_fecha_actual()

        if semana_actual is None:
            semana_actual = Config.get_semana_actual()

        if anio_actual is None:
            anio_actual = Config.get_anio_actual()

        if anio is None:
            anio = datetime.now().year

        nombre_usuario_capitalizado = self._capitalizar_nombre(nombre_usuario)
        nombre_html = _escapar_html(nombre_usuario_capitalizado)

        if fecha_corte is None:
            fecha_corte = Config.get_fecha_corte_datetime(anio, semana)

        fecha_envio_str = fecha_envio.strftime('%d/%m/%Y %H:%M:%S')
        fecha_corte_str = fecha_corte.strftime('%d/%m/%Y %H:%M:%S')

        codigos_previos = [str(x) for x in (codigos_previos or []) if x]
        extra_obs = ""
        if es_duplicado and observacion and " | " in observacion:
            extra_obs = observacion.split(" | ", 1)[1].strip()

        # Asunto según estado
        if es_duplicado:
            asunto = f"Acuse de recibo – Envío duplicado, semana {semana}/{anio} – EsSalud"
        elif estado == "ATRASADO":
            if anio < anio_actual:
                asunto = f"Acuse de recibo – Envío tardío, semana {semana}/{anio} (año actual: {anio_actual}) – EsSalud"
            elif semana < semana_actual:
                asunto = f"Acuse de recibo – Envío tardío, semana {semana}/{anio} (semana actual: {semana_actual}/{anio_actual}) – EsSalud"
            else:
                asunto = f"Acuse de recibo – Envío tardío, semana {semana}/{anio} – EsSalud"
        else:
            asunto = f"Acuse de recibo – Envío de la semana {semana}/{anio} – EsSalud"

        # Estado visual (siempre con texto, no solo con color)
        if estado == "APROBADO":
            estado_plano = "Recibido a tiempo"
            chip_estado = P.chip(estado_plano, "ok")
            banda = "azul"
        elif estado == "ATRASADO":
            estado_plano = "Envío tardío"
            chip_estado = P.chip(estado_plano, "bad")
            banda = "rojo"
        elif estado == "OBSERVADO":
            estado_plano = "Recibido con observaciones"
            chip_estado = P.chip(estado_plano, "warn")
            banda = "ambar"
        else:
            estado_plano = str(estado)
            chip_estado = _escapar_html(estado)
            banda = "azul"

        if es_duplicado:
            estado_plano = "Envío duplicado"
            chip_estado = P.chip(estado_plano, "dup")
            banda = "naranja"

        centros_texto = ", ".join(centros)
        tipos_texto = ", ".join(
            "Hospitalización" if t == "Hospitalizacion" else t for t in tipos_reporte
        )

        # Aviso de atraso (solo si fue tardío)
        mensaje_estado = ""
        alerta_titulo = ""
        if estado == "ATRASADO":
            if anio < anio_actual:
                mensaje_estado = f"Este reporte corresponde al año {anio}, el cual ya venció. El año actual es {anio_actual}."
                alerta_titulo = "Envío tardío · Año anterior"
            elif semana < semana_actual:
                mensaje_estado = f"Este reporte corresponde a la Semana {semana}, que ya venció. La semana actual es la Semana {semana_actual}."
                alerta_titulo = "Envío tardío · Semana anterior"
            else:
                mensaje_estado = "Este reporte fue enviado después de la fecha de corte establecida."
                alerta_titulo = "Envío tardío · Fuera de plazo"
            if dias_atraso > 0:
                alerta_titulo += f" ({dias_atraso} días de atraso)"

        pares = [
            ("Red asistencial", _escapar_html(red)),
            ("Centros", _escapar_html(centros_texto)),
            ("Año y semana", f"{anio} · Semana epidemiológica {semana}"),
            ("Tipos de reporte", _escapar_html(tipos_texto)),
            ("Archivos incluidos", _escapar_html(cantidad_archivos)),
            ("Fecha de envío", fecha_envio_str),
            ("Fecha de corte", fecha_corte_str),
        ]
        if estado == "ATRASADO":
            if dias_atraso > 0:
                pares.append(("Días de atraso", f'<span style="color:{P.ROJO}">{dias_atraso} días</span>'))
            pares.append(("Semana actual", f"{semana_actual} (activa)"))
        pares.append(("Estado", chip_estado))

        texto_duplicado = (
            "Ya existía un envío registrado para este mismo centro en la semana indicada"
            + (f" (código {', '.join(codigos_previos)})" if codigos_previos else "")
            + ". Su archivo <strong>no reemplaza</strong> al anterior: se guardó en una carpeta aparte "
            "para que la OIIS lo revise."
        )
        cuerpo = ""
        if es_duplicado:
            cuerpo += P.caja_aviso("dup", "Envío duplicado · archivo guardado aparte", texto_duplicado)
            if extra_obs:
                cuerpo += P.caja_aviso("warn", "Observación", _escapar_html(extra_obs))
        else:
            if estado == "ATRASADO":
                cuerpo += P.caja_aviso("bad", alerta_titulo, _escapar_html(mensaje_estado))
            if observacion:
                cuerpo += P.caja_aviso("warn", "Observación", _escapar_html(observacion))
        if sustento:
            # Lo que escribió quien envía: se le devuelve como constancia (no se manda a nadie más).
            cuerpo += P.caja_aviso("info", "Su observación", _escapar_html(sustento).replace("\n", "<br>"))
        cuerpo += P.caja_codigo(_escapar_html(codigo_seguimiento))
        cuerpo += P.tabla_desde_pares(pares)
        if es_duplicado:
            cuerpo += P.nota(
                "Este correo es un <strong>acuse de recibo</strong>: certifica que su envío quedó "
                "registrado <strong>como duplicado</strong>, con el código de seguimiento indicado. "
                "Si desea que este archivo reemplace al anterior, responda a este mensaje indicando ambos códigos."
            )
        elif estado == "ATRASADO":
            cuerpo += P.nota(
                "Este correo es un <strong>acuse de recibo</strong>: certifica que su envío quedó "
                "registrado <strong>fuera de plazo</strong>, con el código de seguimiento indicado."
            )
        else:
            cuerpo += P.nota(
                "Este correo es un <strong>acuse de recibo</strong>: certifica que su envío quedó "
                "registrado con el código de seguimiento indicado. Si algún dato no corresponde, "
                "responda a este mensaje indicando el código de seguimiento."
            )

        if es_duplicado:
            eyebrow, titulo = "Acuse de recibo · Envío duplicado", "Su reporte fue recibido como duplicado"
            intro = P.saludo(nombre_html,
                f"Por medio del presente, la OIIS le comunica que recibió nuevamente el reporte de la "
                f"<strong>Semana Epidemiológica {semana}</strong> del año <strong>{anio}</strong> para un centro "
                f"que ya había sido enviado. El archivo se conservó aparte y será revisado."
            )
        elif estado == "ATRASADO":
            eyebrow, titulo = "Acuse de recibo · Envío tardío", "Su reporte fue recibido fuera de plazo"
            intro = P.saludo(nombre_html,
                f"Por medio del presente, la OIIS le comunica que registró el reporte de la "
                f"<strong>Semana Epidemiológica {semana}</strong> del año <strong>{anio}</strong>. "
                f"El envío se consignó como tardío."
            )
        elif estado == "OBSERVADO":
            eyebrow, titulo = "Acuse de recibo · Con observaciones", "Su reporte fue recibido con observaciones"
            intro = P.saludo(nombre_html,
                f"Por medio del presente, la OIIS le comunica que recibió el reporte de la "
                f"<strong>Semana Epidemiológica {semana}</strong> del año <strong>{anio}</strong>. "
                f"Le solicitamos revisar la observación indicada a continuación."
            )
        else:
            eyebrow, titulo = "Acuse de recibo", "Su reporte fue recibido correctamente"
            intro = P.saludo(nombre_html,
                f"Por medio del presente, la OIIS confirma la recepción del reporte de la "
                f"<strong>Semana Epidemiológica {semana}</strong> del año <strong>{anio}</strong>. "
                f"Le agradecemos su envío; conserve este mensaje como constancia."
            )

        cuerpo_html = P.envolver(banda, eyebrow, titulo, intro, cuerpo)

        cuerpo_plano = f"""
ACUSE DE RECIBO – Envío de la semana {semana}/{anio} – EsSalud | OIIS
{'=' * 60}

Estimado/a {nombre_usuario_capitalizado}:

"""
        if es_duplicado:
            cuerpo_plano += (
                "Por medio del presente, la OIIS le comunica que recibió nuevamente su reporte de la Semana "
                f"Epidemiológica {semana} del año {anio} para un centro que ya había sido enviado. "
                "Su archivo NO reemplaza al anterior: se guardó en una carpeta aparte para revisión de la OIIS."
                + (f" Códigos previos: {', '.join(codigos_previos)}." if codigos_previos else "") + "\n"
            )
        elif estado == "ATRASADO":
            cuerpo_plano += (
                "Por medio del presente, la OIIS le comunica que registró su reporte de la Semana Epidemiológica "
                f"{semana} del año {anio}. El envío se consignó como TARDÍO.\n"
            )
        else:
            cuerpo_plano += (
                "Por medio del presente, la OIIS confirma la recepción de su reporte de la Semana Epidemiológica "
                f"{semana} del año {anio}. Le agradecemos su envío.\n"
            )

        if estado == "ATRASADO":
            cuerpo_plano += f"""
{'-' * 60}
AVISO: {alerta_titulo}
{'-' * 60}
{mensaje_estado}
"""

        cuerpo_plano += f"""
{'-' * 60}
DETALLES DEL ENVÍO
{'-' * 60}
Código de seguimiento: {codigo_seguimiento}
Red asistencial:       {red}
Centros:               {centros_texto}
Tipos de reporte:      {tipos_texto}
Archivos incluidos:    {cantidad_archivos}
Fecha de envío:        {fecha_envio_str}
Fecha de corte:        {fecha_corte_str}
"""
        if estado == "ATRASADO":
            if dias_atraso > 0:
                cuerpo_plano += f"Días de atraso:        {dias_atraso} días\n"
            cuerpo_plano += f"Semana actual:         {semana_actual} (activa)\n"
        cuerpo_plano += f"Estado:                {estado_plano}\n"

        if observacion:
            cuerpo_plano += f"""
{'-' * 60}
OBSERVACIÓN
{'-' * 60}
{observacion}
"""

        if sustento:
            cuerpo_plano += f"""
{'-' * 60}
SU OBSERVACIÓN
{'-' * 60}
{sustento}
"""

        cuerpo_plano += f"""
{'-' * 60}
Este correo es un acuse de recibo: certifica que su envío quedó registrado
con el código de seguimiento {codigo_seguimiento}.

Atentamente,
Oficina de Inteligencia e Información Sanitaria (OIIS)
EsSalud
{self._linea_contacto()}"""

        return self._enviar_correo(destinatario, asunto, cuerpo_html, cuerpo_plano)

    def enviar_aviso_reemplazo(
        self,
        destinatario: str,
        nombre_usuario: str,
        red: str,
        semana: int,
        anio: int,
        codigo_anterior: str,
        codigo_nuevo: str,
        detalle: List[str],
        reemplazado_por: str,
        fecha_envio: Optional[datetime] = None,
    ) -> Tuple[bool, str]:
        """
        Avisa a quien envió los archivos anteriores que otro envío los reemplazó. Los archivos
        originales no se borran: quedan en la carpeta REEMPLAZADOS.
        """
        if fecha_envio is None:
            fecha_envio = Config.obtener_fecha_actual()
        nombre = self._capitalizar_nombre(nombre_usuario)
        asunto = f"Aviso – Sus archivos de la semana {semana}/{anio} fueron reemplazados – EsSalud"
        lista_html = "<br>".join(_escapar_html(d) for d in detalle) or "—"
        pares = [
            ("Red asistencial", _escapar_html(red)),
            ("Año y semana", f"{anio} · Semana epidemiológica {semana}"),
            ("Su envío (reemplazado)", _escapar_html(codigo_anterior)),
            ("Nuevo envío", _escapar_html(codigo_nuevo)),
            ("Enviado por", _escapar_html(reemplazado_por)),
            ("Fecha del reemplazo", fecha_envio.strftime('%d/%m/%Y %H:%M:%S')),
            ("Centros y tipos reemplazados", lista_html),
        ]
        cuerpo = P.caja_aviso(
            "warn", "Sus archivos fueron reemplazados",
            "Un envío posterior de su red reemplazó estos archivos. <strong>Sus archivos originales no se borraron</strong>: "
            "quedaron guardados en la carpeta de reemplazados."
        )
        cuerpo += P.tabla_desde_pares(pares)
        cuerpo += P.nota("Si no reconoce este cambio, responda a este mensaje indicando ambos códigos de seguimiento.")
        cuerpo_html = P.envolver(
            "ambar", "Aviso de reemplazo", "Sus archivos fueron reemplazados",
            P.saludo(_escapar_html(nombre), f"La OIIS le informa un cambio en el reporte de la Semana Epidemiológica {semana} del año {anio}."),
            cuerpo
        )
        cuerpo_plano = f"""
AVISO DE REEMPLAZO – Semana {semana}/{anio} – EsSalud | OIIS
{'=' * 60}

Estimado/a {nombre}:

Un envío posterior de su red reemplazó archivos de la Semana Epidemiológica {semana} del año {anio}.
Sus archivos originales no se borraron: quedaron guardados en la carpeta de reemplazados.

Red asistencial:        {red}
Su envío (reemplazado): {codigo_anterior}
Nuevo envío:            {codigo_nuevo}
Enviado por:            {reemplazado_por}
Fecha del reemplazo:    {fecha_envio.strftime('%d/%m/%Y %H:%M:%S')}
Reemplazado:            {'; '.join(detalle) or '—'}

Si no reconoce este cambio, responda a este mensaje indicando ambos códigos.

Atentamente,
Oficina de Inteligencia e Información Sanitaria (OIIS)
EsSalud
{self._linea_contacto()}"""
        return self._enviar_correo(destinatario, asunto, cuerpo_html, cuerpo_plano)

    @staticmethod
    def _linea_contacto() -> str:
        contacto = str(getattr(Config, "CONTACTO_EMAIL", "") or "").strip()
        return f"Para consultas, escriba a {contacto}.\n" if contacto else ""

    def enviar_alerta_admin(
        self,
        nombre_usuario: str,
        correo_usuario: str,
        red: str,
        centros: List[str],
        semana: int,
        observacion: str,
        admin_destino: Optional[str] = None,
        es_atrasado: bool = False,
        semana_actual: Optional[int] = None,
        anio_actual: Optional[int] = None,
        anio: Optional[int] = None,
        es_duplicado: bool = False,
        codigos_previos: Optional[List[str]] = None,
        codigo_seguimiento: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Envía alerta al administrador cuando hay un envío con observaciones,
        tardío o duplicado (este último en naranja).
        """
        if admin_destino is None:
            admin_destino = Config.ADMIN_EMAIL

        if semana_actual is None:
            semana_actual = Config.get_semana_actual()

        if anio_actual is None:
            anio_actual = Config.get_anio_actual()

        if anio is None:
            anio = datetime.now().year

        destinatarios = [admin_destino]
        if Config.EMAIL_ADMINS:
            destinatarios = Config.EMAIL_ADMINS

        centros_texto = ", ".join(centros)
        nombre_usuario_capitalizado = self._capitalizar_nombre(nombre_usuario)

        codigos_previos = [str(x) for x in (codigos_previos or []) if x]
        if es_duplicado:
            asunto = f"Alerta: envío duplicado – {nombre_usuario_capitalizado} – semana {semana}/{anio}"
            banda, titulo, header_title = "naranja", "Envío duplicado", "ALERTA DE ENVÍO DUPLICADO"
        elif es_atrasado:
            if anio < anio_actual:
                asunto = f"Alerta: envío tardío, semana {semana}/{anio} (año actual: {anio_actual}) – {nombre_usuario_capitalizado}"
            elif semana < semana_actual:
                asunto = f"Alerta: envío tardío, semana {semana}/{anio} (semana actual: {semana_actual}/{anio_actual}) – {nombre_usuario_capitalizado}"
            else:
                asunto = f"Alerta: envío tardío – {nombre_usuario_capitalizado} – semana {semana}/{anio}"
            banda, titulo, header_title = "rojo", "Envío tardío", "ALERTA DE ENVÍO TARDÍO"
        else:
            asunto = f"Alerta: envío con observaciones – {nombre_usuario_capitalizado} – semana {semana}/{anio}"
            banda, titulo, header_title = "ambar", "Envío con observaciones", "ALERTA DE ENVÍO CON OBSERVACIONES"

        mensaje_atraso = ""
        if es_atrasado:
            if anio < anio_actual:
                mensaje_atraso = f"El envío corresponde al año {anio}, el cual ya venció. El año actual configurado es {anio_actual}."
            elif semana < semana_actual:
                mensaje_atraso = f"El envío corresponde a la Semana {semana}, que ya venció. La semana actual configurada es la Semana {semana_actual}."
            else:
                mensaje_atraso = "Este envío fue registrado después de la fecha de corte establecida."

        cuerpo = ""
        if es_duplicado:
            cuerpo += P.caja_aviso(
                "dup", "Archivo guardado en la carpeta de duplicados",
                "La red volvió a enviar un centro que ya había enviado esta semana"
                + (f" (envío previo: {_escapar_html(', '.join(codigos_previos))})" if codigos_previos else "")
                + ". No reemplaza al original. Revíselo en <strong>Control de duplicados</strong> del panel "
                "y decida si se conserva o se elimina."
            )
        elif es_atrasado:
            cuerpo += P.caja_aviso("bad", "Envío fuera de plazo", _escapar_html(mensaje_atraso))
        cuerpo += P.bloque_titulo("Datos del envío")
        pares_alerta = [
            ("Usuario", _escapar_html(nombre_usuario_capitalizado)),
            ("Correo", _escapar_html(correo_usuario)),
            ("Red", _escapar_html(red)),
            ("Centros", _escapar_html(centros_texto)),
            ("Semana", f"{semana}/{anio}"),
        ]
        if codigo_seguimiento:
            pares_alerta.append(("Código de seguimiento", _escapar_html(codigo_seguimiento)))
        cuerpo += P.tabla_desde_pares(pares_alerta)
        if observacion and not es_duplicado:
            cuerpo += P.caja_aviso("warn", "Detalle de la observación", _escapar_html(observacion))
        cuerpo += P.nota("<strong>Acción requerida:</strong> revise el envío y adopte las medidas que correspondan.")

        cuerpo_html = P.envolver(
            banda, "Alerta para administración", titulo,
            P.saludo("administrador/a", "Se registró un nuevo envío en el sistema que requiere su atención."), cuerpo
        )

        cuerpo_plano = f"""
{header_title}
{'=' * 50}

Estimado/a administrador/a:

Se registró un nuevo envío en el sistema que requiere su atención.
"""

        if es_duplicado:
            cuerpo_plano += f"""
{'-' * 50}
ATENCIÓN: ENVÍO DUPLICADO
{'-' * 50}
La red volvió a enviar un centro que ya había enviado esta semana{(' (envío previo: ' + ', '.join(codigos_previos) + ')') if codigos_previos else ''}.
El archivo se guardó en la carpeta de duplicados. Revíselo en «Control de duplicados».
"""
        elif es_atrasado:
            cuerpo_plano += f"""
{'-' * 50}
ATENCIÓN: ENVÍO FUERA DE PLAZO
{'-' * 50}
{mensaje_atraso}
"""

        cuerpo_plano += f"""
{'-' * 50}
DATOS DEL ENVÍO
{'-' * 50}
Usuario: {nombre_usuario_capitalizado}
Correo:  {correo_usuario}
Red:     {red}
Centros: {centros_texto}
Semana:  {semana}/{anio}
{('Código:  ' + codigo_seguimiento) if codigo_seguimiento else ''}
"""

        if observacion and not es_duplicado:
            cuerpo_plano += f"""
{'-' * 50}
DETALLE DE LA OBSERVACIÓN
{'-' * 50}
{observacion}
"""

        cuerpo_plano += f"""
{'=' * 50}
Acción requerida: revise el envío y adopte las medidas que correspondan.
"""

        resultados = []
        for admin in destinatarios:
            exito, mensaje = self._enviar_correo(admin, asunto, cuerpo_html, cuerpo_plano)
            resultados.append((admin, exito, mensaje))

        return any(r[1] for r in resultados), f"Enviado a {sum(1 for r in resultados if r[1])} de {len(resultados)} administradores"

    def enviar_solicitud_correccion(
        self,
        destinatario: str,
        nombre_usuario: str,
        semana: int,
        observacion_admin: str,
        codigo_seguimiento: str,
        fecha_limite: Optional[str] = None,
        anio: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Envía solicitud de corrección al usuario (cabecera ámbar).
        """
        if fecha_limite is None:
            fecha_limite = Config.get_fecha_corte()

        if anio is None:
            anio = datetime.now().year

        nombre_usuario_capitalizado = self._capitalizar_nombre(nombre_usuario)
        nombre_html = _escapar_html(nombre_usuario_capitalizado)
        fecha_limite_str = P.fecha_legible(fecha_limite)

        asunto = f"Solicitud de corrección – Envío de la semana {semana}/{anio} – EsSalud"

        cuerpo = P.caja_aviso("warn", "Observación del administrador", _escapar_html(observacion_admin))
        cuerpo += P.bloque_titulo("Qué debe hacer")
        cuerpo += P.lista([
            "Verifique el archivo ZIP enviado.",
            "Realice las correcciones indicadas.",
            "Ingrese al sistema y cargue la versión corregida.",
        ], ordenada=True)
        cuerpo += '<div style="margin-top:20px"></div>'
        cuerpo += P.tabla_desde_pares([
            ("Código de envío", _escapar_html(codigo_seguimiento)),
            ("Año y semana", f"{anio} · Semana epidemiológica {semana}"),
            ("Fecha límite", _escapar_html(fecha_limite_str)),
        ])
        cuerpo += P.caja_aviso(
            "bad", "Importante",
            "Si no corrige antes de la fecha límite, el envío se marcará como «Envío tardío»."
        )

        cuerpo_html = P.envolver(
            "ambar", "Solicitud de corrección", "Su envío requiere una corrección",
            P.saludo(nombre_html,
                f"Por medio del presente, le informamos que el administrador revisó su envío de la "
                f"<strong>Semana Epidemiológica {semana}</strong> del año <strong>{anio}</strong> "
                f"y detectó lo siguiente."),
            cuerpo
        )

        cuerpo_plano = f"""
SOLICITUD DE CORRECCIÓN – Envío de la semana {semana}/{anio} – EsSalud | OIIS
{'=' * 50}

Estimado/a {nombre_usuario_capitalizado}:

Por medio del presente, le informamos que el administrador revisó su envío correspondiente a la Semana Epidemiológica {semana} del año {anio} y detectó lo siguiente:

{'=' * 50}
OBSERVACIÓN DEL ADMINISTRADOR
{'-' * 50}
{observacion_admin}

{'=' * 50}
QUÉ DEBE HACER
{'-' * 50}
1. Verifique el archivo ZIP enviado.
2. Realice las correcciones indicadas.
3. Ingrese al sistema y cargue la versión corregida.

Código de envío: {codigo_seguimiento}
Fecha límite:    {fecha_limite_str}

Importante: si no corrige antes de la fecha límite, el envío se marcará como "Envío tardío".
"""

        return self._enviar_correo(destinatario, asunto, cuerpo_html, cuerpo_plano)

    def enviar_recordatorio(
        self,
        destinatario: str,
        nombre_usuario: str,
        red: str,
        semana: int,
        fecha_limite: str,
        centros_pendientes: Optional[List[str]] = None,
        anio: Optional[int] = None,
        semana_actual: Optional[int] = None,
        anio_actual: Optional[int] = None,
        tipo: str = "PREVENTIVO",
        mensaje_adicional: Optional[str] = None,
        pendientes_por_tipo: Optional[List[Dict]] = None,
        cc: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """
        Envía recordatorio de envío pendiente (ver `componer_recordatorio`).
        `cc` (SIREA 3.2): otros responsables del envío de la red, en copia.
        """
        asunto, cuerpo_html, cuerpo_plano = self.componer_recordatorio(
            nombre_usuario, red, semana, fecha_limite, centros_pendientes=centros_pendientes, anio=anio,
            semana_actual=semana_actual, anio_actual=anio_actual, tipo=tipo, mensaje_adicional=mensaje_adicional,
            pendientes_por_tipo=pendientes_por_tipo)
        return self._enviar_correo(destinatario, asunto, cuerpo_html, cuerpo_plano, cc=cc or None)

    def componer_recordatorio(
        self,
        nombre_usuario: str,
        red: str,
        semana: int,
        fecha_limite: str,
        centros_pendientes: Optional[List[str]] = None,
        anio: Optional[int] = None,
        semana_actual: Optional[int] = None,
        anio_actual: Optional[int] = None,
        tipo: str = "PREVENTIVO",
        mensaje_adicional: Optional[str] = None,
        pendientes_por_tipo: Optional[List[Dict]] = None
    ) -> Tuple[str, str, str]:
        """
        Arma el recordatorio (asunto, HTML, texto plano) SIN enviarlo: lo usa
        el envío y la vista previa que revisa la persona antes de aprobar.
        `mensaje_adicional` (SIREA): párrafo propuesto por el Agente Operativo y aprobado
        por una persona; se escapa y se muestra en un recuadro «Mensaje de la OIIS».
        `pendientes_por_tipo` (SIREA 3.2): [{'centro', 'faltan': [...], 'recibidos': [...]}]
        con los datos exactos del sistema: qué reporte (Consulta Externa,
        Hospitalización, Emergencia) le falta a cada centro.

        Args:
            tipo: "PREVENTIVO" (plazo por vencer, cabecera azul) o
                  "ATRASADO" (plazo vencido, cabecera roja)
        """
        if anio is None:
            anio = datetime.now().year

        if anio_actual is None:
            anio_actual = datetime.now().year

        if semana_actual is None:
            try:
                from src.db_manager import get_db_manager
                db = get_db_manager()
                semana_actual = int(db.obtener_configuracion('semana_activa') or 1)
            except Exception:
                semana_actual = 1

        nombre_usuario_capitalizado = self._capitalizar_nombre(nombre_usuario)
        nombre_html = _escapar_html(nombre_usuario_capitalizado)

        # La fecha de corte es la que ya llega en el parámetro fecha_limite
        # (viene de Config.get_fecha_corte(), la fecha única configurada
        # por el administrador).
        fecha_limite_str = P.fecha_legible(fecha_limite)
        pendientes = list(centros_pendientes or [])
        bloque_pendientes = ""
        if pendientes:
            tono_chips = "bad" if tipo == "ATRASADO" else "info"
            bloque_pendientes = (
                P.bloque_titulo(f"Centros pendientes de envío ({len(pendientes)})")
                + P.chips_centros(pendientes, tono_chips)
            )
        por_tipo = [x for x in (pendientes_por_tipo or []) if isinstance(x, dict) and x.get("centro")]
        if por_tipo:   # el detalle por tipo reemplaza a la lista simple de centros
            bloque_pendientes = (
                P.bloque_titulo(f"Reportes pendientes por centro ({len(por_tipo)})")
                + P.tabla_desde_pares([(_escapar_html(x["centro"]), _escapar_html(", ".join(x.get("faltan") or []) or "—"))
                                       for x in por_tipo[:200]])
            )
        mensaje_adicional = (mensaje_adicional or "").strip()[:900]
        if mensaje_adicional:
            bloque_pendientes = (P.caja_aviso("info", "Mensaje de la OIIS",
                                              _escapar_html(mensaje_adicional).replace("\n", "<br>"))
                                 + bloque_pendientes)

        if tipo == "ATRASADO":
            asunto = f"Recordatorio de envío tardío – Semana {semana}/{anio} – EsSalud | OIIS"
            titulo_plano = "Recordatorio de envío tardío"
            cuerpo = P.caja_aviso(
                "bad", "Envío tardío",
                "El plazo para este envío ya venció. Le solicitamos regularizarlo a la brevedad."
            )
            cuerpo += '<div style="margin-top:20px"></div>'
            cuerpo += P.tabla_desde_pares([
                ("Red asistencial", _escapar_html(red)),
                ("Año y semana", f"{anio} · Semana epidemiológica {semana}"),
                ("Plazo máximo", f'<span style="color:{P.ROJO}">{_escapar_html(fecha_limite_str)}</span>'),
            ])
            cuerpo += bloque_pendientes
            cuerpo += (
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                'style="margin-top:16px"><tr><td style="background:#F4F6F8;border:1px solid '
                f'{P.LINEA};border-radius:6px;padding:14px 16px;font-size:14px;color:#33424F;'
                f'font-family:{P.FUENTE}">'
                '<div style="font-weight:600;color:#14202B;margin-bottom:6px">Si el envío sigue pendiente</div>'
                '<ul style="margin:0;padding-left:20px">'
                '<li>Se registrará como «Envío tardío».</li>'
                '<li>El administrador será notificado automáticamente.</li>'
                '<li>Puede afectar los indicadores de su red y centro.</li></ul></td></tr></table>'
            )
            cuerpo += P.base_normativa()
            cuerpo += P.nota("Si ya realizó su envío, le agradecemos ignorar este mensaje.")
            cuerpo_html = P.envolver(
                "rojo", "Recordatorio de envío tardío", "El plazo de envío ya venció",
                P.saludo(nombre_html,
                    f"Por medio del presente, le comunicamos que aún no recibimos el reporte de la "
                    f"<strong>Semana Epidemiológica {semana}</strong> del año <strong>{anio}</strong> de su red."),
                cuerpo
            )
            intro_plano = (
                f"Por medio del presente, le comunicamos que aún no recibimos el reporte de la Semana Epidemiológica {semana} del año {anio} de su red.\n\n"
                "ENVÍO TARDÍO: el plazo para este envío ya venció. Le solicitamos regularizarlo a la brevedad.\n"
                f"Plazo máximo: {fecha_limite_str}"
            )
            consecuencias_plano = """
SI EL ENVÍO SIGUE PENDIENTE
- Se registrará como "Envío tardío".
- El administrador será notificado automáticamente.
- Puede afectar los indicadores de su red y centro.
"""
        else:  # PREVENTIVO
            asunto = f"Recordatorio preventivo – Semana {semana}/{anio} – EsSalud | OIIS"
            titulo_plano = "Recordatorio preventivo"
            cuerpo = P.caja_aviso(
                "warn", "Plazo por vencer",
                "Le recomendamos realizar el envío a la brevedad, antes de la fecha límite, "
                "para que no se registre como tardío."
            )
            cuerpo += '<div style="margin-top:20px"></div>'
            cuerpo += P.tabla_desde_pares([
                ("Red asistencial", _escapar_html(red)),
                ("Año y semana", f"{anio} · Semana epidemiológica {semana}"),
                ("Fecha límite", f'<span style="color:#1E6B3A">{_escapar_html(fecha_limite_str)}</span>'),
            ])
            cuerpo += bloque_pendientes
            cuerpo += P.base_normativa()
            cuerpo += P.nota("Si ya realizó su envío, le agradecemos ignorar este mensaje.")
            cuerpo_html = P.envolver(
                "azul", "Recordatorio preventivo", "El plazo de envío está por vencer",
                P.saludo(nombre_html,
                    f"Por medio del presente, le recordamos que el plazo para el envío de la "
                    f"<strong>Semana Epidemiológica {semana}</strong> del año <strong>{anio}</strong> vence pronto."),
                cuerpo
            )
            intro_plano = (
                f"Por medio del presente, le recordamos que el plazo para el envío de la Semana Epidemiológica {semana} del año {anio} vence pronto.\n\n"
                "Le recomendamos realizar el envío a la brevedad, antes de la fecha límite, "
                "para que no se registre como tardío.\n"
                f"Fecha límite: {fecha_limite_str}"
            )
            consecuencias_plano = ""

        cuerpo_plano = f"""
{titulo_plano.upper()} – Semana {semana}/{anio} – EsSalud | OIIS
{'=' * 50}

Estimado/a {nombre_usuario_capitalizado}:

{intro_plano}

Red: {red}
"""
        if por_tipo:
            cuerpo_plano += "Reportes pendientes por centro:\n" + "".join(
                f"  - {x['centro']}: {', '.join(x.get('faltan') or []) or '—'}\n" for x in por_tipo[:200])
        elif pendientes:
            cuerpo_plano += f"Centros pendientes ({len(pendientes)}): {', '.join(pendientes)}\n"

        if mensaje_adicional:
            cuerpo_plano += f"\nMENSAJE DE LA OIIS\n{mensaje_adicional}\n"
        cuerpo_plano += consecuencias_plano
        cuerpo_plano += f"""
Base normativa: Directiva N°17-GG-ESSALUD-2023 (los reportes deben enviarse dentro del plazo establecido para cada semana epidemiológica).

Si ya realizó su envío, le agradecemos ignorar este mensaje.

Atentamente,
Oficina de Inteligencia e Información Sanitaria (OIIS)
EsSalud
{self._linea_contacto()}"""

        return asunto, cuerpo_html, cuerpo_plano

    def enviar_informe_semanal(self, destinatario: str, semana: int, anio: int, texto: str, leyenda: str) -> Tuple[bool, str]:
        """
        SIREA 3.2: informe semanal interno (ya APROBADO por una persona) para la
        Jefatura de la OIIS. Texto con títulos y viñetas «- »; todo se escapa.
        """
        titulos = ("Situación de la semana", "Lo destacado", "Patrones a vigilar", "Recomendaciones")
        partes, viñetas = [], []

        def _cerrar():
            if viñetas:
                partes.append(P.lista([_escapar_html(v) for v in viñetas]))
                viñetas.clear()

        for linea in str(texto or "").splitlines():
            t = linea.strip()
            if not t:
                continue
            if t in titulos:
                _cerrar()
                partes.append(P.bloque_titulo(t))
            elif t.startswith("- "):
                viñetas.append(t[2:])
            else:
                _cerrar()
                partes.append(f'<p style="margin:0 0 10px">{_escapar_html(t)}</p>')
        _cerrar()
        partes.append(P.nota(_escapar_html(leyenda)))
        asunto = f"Informe semanal SIREA – Semana {semana}/{anio} – OIIS | EsSalud"
        cuerpo_html = P.envolver("azul", "Informe semanal", f"Semana epidemiológica {semana}/{anio}",
                                 '<p style="margin:0 0 14px">Resumen interno de cumplimiento en la remisión de reportes '
                                 'epidemiológicos, preparado por SIREA y validado por la OIIS.</p>', "".join(partes), anio=anio)
        cuerpo_plano = f"INFORME SEMANAL SIREA – Semana {semana}/{anio}\n{'=' * 50}\n\n{texto}\n\n{leyenda}\n"
        return self._enviar_correo(destinatario, asunto, cuerpo_html, cuerpo_plano)

    # ============================================================
    # SOLICITUD DE CAMBIO DE CONTRASEÑA (red <-> OIIS)
    # ============================================================

    @staticmethod
    def _multilinea(texto: str) -> str:
        """Texto escrito por una persona: se escapa y se respetan los saltos de línea."""
        return _escapar_html(texto or "").replace("\r\n", "\n").replace("\n", "<br>")

    def enviar_acuse_solicitud_password(
        self,
        destinatario: str,
        nombre: str,
        red: str,
        codigo: str,
        sustento: str,
        fecha: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """Acuse de recibo para la red: su solicitud de cambio de contraseña quedó registrada."""
        fecha = fecha or Config.obtener_fecha_actual()
        nombre_c = self._capitalizar_nombre(nombre)
        asunto = f"Acuse de recibo – Solicitud de cambio de contraseña {codigo} – EsSalud"

        cuerpo = P.caja_codigo(_escapar_html(codigo), "Código de la solicitud")
        cuerpo += P.tabla_desde_pares([
            ("Red asistencial", _escapar_html(red)),
            ("Solicitante", _escapar_html(nombre_c)),
            ("Fecha de registro", _escapar_html(P.fecha_legible(fecha, con_segundos=True))),
            ("Estado", P.chip("Pendiente de revisión", "info")),
        ])
        cuerpo += P.bloque_titulo("Sustento enviado")
        cuerpo += P.caja_aviso("info", "Su mensaje", self._multilinea(sustento))
        cuerpo += P.bloque_titulo("Qué sigue")
        cuerpo += P.lista([
            "La OIIS revisará su sustento. Puede pedirle información adicional.",
            "Podrá ver las respuestas y continuar el intercambio en el módulo «Mi progreso» del sistema.",
            "Si la solicitud se aprueba, se habilitará el cambio de contraseña y se le avisará por este correo.",
        ], ordenada=True)
        cuerpo += P.caja_aviso(
            "warn", "Su contraseña actual sigue vigente",
            "Mientras la solicitud no sea aprobada, la red debe seguir ingresando con su contraseña actual."
        )

        html_ = P.envolver(
            "azul", "Acuse de recibo · Cambio de contraseña", "Recibimos su solicitud",
            P.saludo(_escapar_html(nombre_c),
                     f"Por medio del presente, la OIIS le comunica que recibió la solicitud de cambio de "
                     f"contraseña de la red <strong>{_escapar_html(red)}</strong>."),
            cuerpo
        )
        plano = f"""
ACUSE DE RECIBO – SOLICITUD DE CAMBIO DE CONTRASEÑA
{'=' * 50}

Estimado/a {nombre_c}:

Por medio del presente, la OIIS le comunica que recibió la solicitud de cambio de contraseña de la red {red}.

Código de la solicitud: {codigo}
Fecha de registro:      {P.fecha_legible(fecha, con_segundos=True)}
Estado:                 Pendiente de revisión

SUSTENTO ENVIADO
{'-' * 50}
{sustento}

QUÉ SIGUE
{'-' * 50}
1. La OIIS revisará su sustento y puede pedirle información adicional.
2. Podrá ver las respuestas en el módulo «Mi progreso» del sistema.
3. Si se aprueba, se habilitará el cambio y se le avisará por este correo.

Mientras tanto, su contraseña actual sigue vigente.
"""
        return self._enviar_correo(destinatario, asunto, html_, plano)

    def enviar_alerta_solicitud_password(
        self,
        red: str,
        nombre: str,
        correo: str,
        codigo: str,
        sustento: str,
        admin_destino: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Aviso a los administradores: una red pidió cambiar su contraseña."""
        destinatarios = list(Config.EMAIL_ADMINS) if Config.EMAIL_ADMINS else [admin_destino or Config.ADMIN_EMAIL]
        nombre_c = self._capitalizar_nombre(nombre)
        asunto = f"Solicitud de cambio de contraseña – Red {red} – {codigo}"

        cuerpo = P.caja_aviso(
            "warn", "Requiere su revisión",
            "Revise el sustento en el panel de administración, sección <strong>Solicitudes de contraseña</strong>. "
            "Desde allí puede responder, pedir más información, aprobar o rechazar."
        )
        cuerpo += P.bloque_titulo("Datos de la solicitud")
        cuerpo += P.tabla_desde_pares([
            ("Código", _escapar_html(codigo)),
            ("Red", _escapar_html(red)),
            ("Solicitante", _escapar_html(nombre_c)),
            ("Correo", _escapar_html(correo)),
        ])
        cuerpo += P.caja_aviso("info", "Sustento de la red", self._multilinea(sustento))

        html_ = P.envolver(
            "ambar", "Alerta para administración", "Una red solicita cambiar su contraseña",
            P.saludo("administrador/a", f"La red <strong>{_escapar_html(red)}</strong> envió el sustento para cambiar su contraseña de acceso."),
            cuerpo
        )
        plano = f"""
SOLICITUD DE CAMBIO DE CONTRASEÑA – RED {red}
{'=' * 50}

Estimado/a administrador/a:

La red {red} envió el sustento para cambiar su contraseña de acceso. Revíselo en el panel, sección «Solicitudes de contraseña».

Código:      {codigo}
Red:         {red}
Solicitante: {nombre_c}
Correo:      {correo}

SUSTENTO
{'-' * 50}
{sustento}
"""
        resultados = [self._enviar_correo(d, asunto, html_, plano) for d in destinatarios]
        return any(r[0] for r in resultados), f"Enviado a {sum(1 for r in resultados if r[0])} de {len(resultados)} administradores"

    def enviar_respuesta_solicitud_password(
        self,
        destinatario: str,
        nombre: str,
        red: str,
        codigo: str,
        tipo: str,
        mensaje: str,
        responsable: str,
        horas_validez: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Respuesta de la OIIS a la red. tipo: 'RESPUESTA' (pide o da información),
        'APROBADA' (se habilita el cambio) o 'RECHAZADA'.
        """
        nombre_c = self._capitalizar_nombre(nombre)
        responsable_c = (responsable or "").strip() or "OIIS"

        if tipo == "APROBADA":
            asunto = f"Solicitud aprobada – Cambio de contraseña {codigo} – EsSalud"
            banda, eyebrow, titulo = "azul", "Solicitud aprobada", "Ya puede cambiar su contraseña"
            estado = P.chip("Aprobada", "ok")
            caja = P.caja_aviso(
                "ok", "Cambio de contraseña habilitado",
                "Ingrese al portal de redes, sección <strong>Mi progreso</strong>, y elija su nueva contraseña."
                + (f" La autorización es válida por <strong>{horas_validez} horas</strong>." if horas_validez else "")
            )
            intro = "Por medio del presente, la OIIS le comunica que revisó su sustento y <strong>aprobó</strong> la solicitud."
        elif tipo == "RECHAZADA":
            asunto = f"Solicitud no aprobada – Cambio de contraseña {codigo} – EsSalud"
            banda, eyebrow, titulo = "ambar", "Solicitud no aprobada", "Su solicitud no fue aprobada"
            estado = P.chip("No aprobada", "warn")
            caja = P.caja_aviso(
                "warn", "Su contraseña actual sigue vigente",
                "Si considera que existen razones adicionales, puede enviar una nueva solicitud con un mayor sustento."
            )
            intro = "Por medio del presente, la OIIS le comunica que revisó su sustento y <strong>no aprobó</strong> la solicitud."
        else:
            asunto = f"Respuesta a su solicitud de cambio de contraseña {codigo} – EsSalud"
            banda, eyebrow, titulo = "azul", "Respuesta de la OIIS", "La OIIS respondió a su solicitud"
            estado = P.chip("En revisión", "info")
            caja = P.caja_aviso(
                "info", "Puede responder",
                "Ingrese al portal de redes, sección <strong>Mi progreso</strong>, para continuar el intercambio de información."
            )
            intro = "Por medio del presente, la OIIS le comunica que respondió a su solicitud de cambio de contraseña."

        cuerpo = P.tabla_desde_pares([
            ("Código", _escapar_html(codigo)),
            ("Red asistencial", _escapar_html(red)),
            ("Estado", estado),
            ("Responde", _escapar_html(responsable_c)),
        ])
        if mensaje:
            cuerpo += P.caja_aviso("info", "Mensaje de la OIIS", self._multilinea(mensaje))
        cuerpo += caja

        html_ = P.envolver(banda, eyebrow, titulo, P.saludo(_escapar_html(nombre_c), intro), cuerpo)
        plano = f"""
{eyebrow.upper()} – CAMBIO DE CONTRASEÑA {codigo}
{'=' * 50}

Estimado/a {nombre_c}:

{re.sub('<[^>]+>', '', intro)}

Red:     {red}
Código:  {codigo}
Responde: {responsable_c}

MENSAJE DE LA OIIS
{'-' * 50}
{mensaje or '(sin mensaje adicional)'}
"""
        if tipo == "APROBADA":
            plano += f"\nSe habilitó el cambio de contraseña. Ingrese a «Mi progreso» y elija su nueva contraseña.{(' Válido por ' + str(horas_validez) + ' horas.') if horas_validez else ''}\n"
        elif tipo == "RECHAZADA":
            plano += "\nSu contraseña actual sigue vigente. Puede enviar una nueva solicitud con mayor sustento.\n"
        else:
            plano += "\nIngrese a «Mi progreso» para continuar el intercambio de información.\n"
        return self._enviar_correo(destinatario, asunto, html_, plano)

    def enviar_correo_prueba(self, destinatario: str) -> Tuple[bool, str]:
        """
        Envía un correo de prueba para verificar la configuración SMTP.
        """
        asunto = "Prueba de configuración del correo – SIREA – EsSalud"
        fecha_actual = formatear_fecha(Config.obtener_fecha_actual())

        cuerpo = '<div style="margin-top:20px"></div>' + P.tabla_desde_pares([
            ("Fecha", _escapar_html(fecha_actual)),
            ("Servidor", _escapar_html(f"{self.smtp_server}:{self.smtp_port}")),
            ("Estado", P.chip("Configuración correcta", "ok")),
        ])
        cuerpo_html = P.envolver(
            "azul", "Prueba de configuración", "El correo está configurado correctamente",
            P.saludo("usuario/a", "Este es un correo de prueba del Sistema de Recepción de Reportes Epidemiológicos con Agentes (SIREA). Si lo está leyendo, la configuración del correo funciona correctamente."),
            cuerpo
        )

        cuerpo_plano = f"""
PRUEBA DE CONFIGURACIÓN DEL CORREO
{'=' * 50}

Este es un correo de prueba del Sistema de Recepción de Reportes.
La configuración del correo funciona correctamente.

Fecha: {fecha_actual}
Servidor: {self.smtp_server}:{self.smtp_port}
"""

        return self._enviar_correo(destinatario, asunto, cuerpo_html, cuerpo_plano)
    
    def verificar_configuracion(self) -> Tuple[bool, str]:
        """
        Verifica que la configuración SMTP sea válida.
        """
        if not self.smtp_server:
            return False, "Servidor SMTP no configurado"
        
        if not self.remitente:
            return False, "Correo remitente no configurado"
        
        if not self.password:
            return False, "Contraseña no configurada"
        
        try:
            server = self._crear_servidor_smtp()
            self._iniciar_sesion(server)
            server.quit()
            return True, "Configuración SMTP válida"
        except Exception as e:
            return False, f"Error de configuración: {str(e)}"


# Instancia global
_email_sender = None

def get_email_sender() -> EmailSender:
    """
    Retorna la instancia única del EmailSender.
    """
    global _email_sender
    if _email_sender is None:
        _email_sender = EmailSender()
    return _email_sender


def limpiar_cache():
    """
    Limpia la instancia cacheada del EmailSender.
    """
    global _email_sender
    _email_sender = None