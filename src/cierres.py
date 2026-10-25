# src/cierres.py
"""
Cierre de corte, propuesta de la semana siguiente y validación entre administradores.

Qué hace (lo ejecuta el proceso programado cada minuto, ver src/programador.py):

  1. Cuando pasa la fecha de corte configurada, cierra la semana: propone la
     semana siguiente y el siguiente corte (+7 días, avisando si cae en feriado
     o fin de semana) y los APLICA de inmediato como valores PROVISIONALES.
  2. Envía UN correo a los administradores y SUPER_ADMIN para que validen o
     corrijan, con el resumen de cumplimiento en borrador.
  3. Si nadie valida, envía hasta 3 recordatorios (8:00, 12:00 y 16:00 del día
     hábil siguiente al corte). Se detienen en cuanto alguien valida.
  4. Cuando una persona valida, las demás ven «ya validado por X» en el panel
     y reciben UN correo corto.
  5. El resumen de cumplimiento solo se envía a la entidad externa después de
     que una persona de la OIIS lo valide.

Todo es idempotente: un corte se procesa una sola vez (clave única en la base) y
cada envío se «reserva» antes de mandarse, así que aunque se reinicie el
proceso o haya dos copias corriendo, no se duplican los correos.

La hora que usa todo este módulo es la de Lima, como datetime SIN zona.
"""

import re
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

from src import email_cierres as correos
from src.calendario_epi import parsear_corte
from src.config import Config
from src.feriados_pe import nombre_feriado, siguiente_habil
from src.validacion_correo import formato_valido, normalizar as normalizar_correo

LIMA = timezone(timedelta(hours=-5))
FORMATO = "%Y-%m-%d %H:%M:%S"
# Un corte vencido hace más de esto NO se procesa solo (evita cambios sorpresa con datos viejos).
VENTANA_HORAS = int(__import__("os").getenv("CIERRE_VENTANA_HORAS", "72") or "72")
MAX_TEXTO = 2000


def ahora_lima() -> datetime:
    """Hora actual de Lima, sin zona."""
    return datetime.now(LIMA).replace(tzinfo=None)


def _iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class Cierres:
    """Lógica del cierre de corte (la pantalla y el proceso programado solo la usan)."""

    def __init__(self, db=None, sender=None, avance_fn: Optional[Callable] = None,
                 limpiar_fn: Optional[Callable] = None, redes_fn: Optional[Callable] = None):
        if db is None:
            from src.db_manager import get_db_manager
            db = get_db_manager()
        self.db = db
        self._sender = sender
        self.avance_fn, self.limpiar_fn, self.redes_fn = avance_fn, limpiar_fn, redes_fn
        self._disp = None

    # ------------------------------------------------------------ utilidades

    @property
    def sender(self):
        if self._sender is None:
            from src.email_sender import get_email_sender
            self._sender = get_email_sender()
        return self._sender

    def _t(self, nombre: str):
        return self.db.supabase.table(nombre)

    def disponible(self) -> bool:
        """True si la migración 10 ya se ejecutó (se reintenta cada 30 s mientras falte)."""
        ahora = datetime.now().timestamp()
        if self._disp and (self._disp[0] or ahora - self._disp[1] < 30):
            return self._disp[0]
        try:
            self._t("cierres_corte").select("id").limit(1).execute()
            ok = True
        except Exception as e:
            print(f"Cierres de corte no disponibles (¿falta sql/10?): {e}")
            ok = False
        self._disp = (ok, ahora)
        return ok

    def destinatarios(self, excluir_usuario: Optional[str] = None) -> List[Dict]:
        """Administradores y SUPER_ADMIN activos con correo válido (+ EMAIL_ADMINS del .env)."""
        salida, vistos = [], set()
        for a in self.db.obtener_administradores(solo_activos=True) or []:
            correo = normalizar_correo(a.get("email"))
            if not formato_valido(correo) or correo in vistos:
                continue
            if excluir_usuario and str(a.get("usuario", "")).lower() == str(excluir_usuario).lower():
                continue
            vistos.add(correo)
            salida.append({"usuario": a.get("usuario", ""), "nombre": a.get("nombre") or a.get("usuario", ""),
                           "email": correo, "rol": a.get("rol", "")})
        for e in Config.EMAIL_ADMINS:
            correo = normalizar_correo(e)
            if formato_valido(correo) and correo not in vistos:
                vistos.add(correo)
                salida.append({"usuario": "", "nombre": "administrador/a", "email": correo, "rol": ""})
        return salida

    def _hay(self, filtros: Dict) -> bool:
        q = self._t("cierres_corte").select("id")
        for k, v in filtros.items():
            q = q.eq(k, v)
        return bool(q.limit(1).execute().data)

    # ------------------------------------------------------------ consulta

    def listar(self, limite: int = 20) -> List[Dict]:
        if not self.disponible():
            return []
        return self._t("cierres_corte").select("*").order("id", desc=True).limit(limite).execute().data or []

    def obtener(self, cierre_id) -> Optional[Dict]:
        r = self._t("cierres_corte").select("*").eq("id", cierre_id).limit(1).execute().data
        return r[0] if r else None

    def ultimo(self) -> Optional[Dict]:
        """El cierre más reciente (provisional o validado) o None."""
        if not self.disponible():
            return None
        r = self.listar(1)
        return r[0] if r else None

    def pendiente(self) -> Optional[Dict]:
        """El cierre provisional que espera validación, si lo hay."""
        if not self.disponible():
            return None
        r = (self._t("cierres_corte").select("*").eq("estado", "PROVISIONAL")
             .order("id", desc=True).limit(1).execute().data)
        return r[0] if r else None

    # ------------------------------------------------------------ cierre

    def _config_actual(self) -> Tuple[Optional[int], Optional[datetime]]:
        s = self.db.obtener_configuracion("semana_activa")
        try:
            semana = int(s) if s else None
        except ValueError:
            semana = None
        return semana, parsear_corte(self.db.obtener_configuracion("fecha_corte"))

    def _propuesta(self, semana: int, corte: datetime, ahora: datetime) -> Dict:
        """Semana y corte propuestos, con las notas que la persona debe revisar."""
        info = self.db.obtener_anio_activo_epidemiologico() or {}
        semanas = int(info.get("semanas") or 52)
        notas: List[str] = []
        sig = corte + timedelta(days=7)
        while sig <= ahora:
            sig += timedelta(days=7)
        aplicar = True
        if semana + 1 > semanas:
            aplicar, prop = False, 1
            notas.append(f"Fin del año epidemiológico: la semana {semana} era la última. Registre y active el año "
                         f"siguiente en Configuración y defina la semana 1 y su fecha de corte. "
                         "El sistema no cambió la semana.")
        else:
            prop = semana + 1
        f = nombre_feriado(sig.date())
        if f:
            notas.append(f"El corte propuesto cae en feriado ({f}). Considere moverlo.")
        if sig.weekday() >= 5:
            notas.append("El corte propuesto cae en fin de semana.")
        return {"semana": prop, "corte": sig, "aplicar": aplicar, "notas": notas}

    def vencido_sin_cerrar(self, ahora: Optional[datetime] = None) -> Optional[Dict]:
        """
        El corte configurado ya venció y nadie lo cerró (el proceso programado está caído o se apagó).
        Devuelve {semana, corte, horas, fuera_ventana} o None si no hay nada pendiente.
        """
        try:
            if not self.disponible():
                return None
            ahora = ahora or ahora_lima()
            semana, corte = self._config_actual()
            if not semana or not corte or ahora < corte:
                return None
            anio = Config.get_anio_actual()
            if self._hay({"corte_cerrado": corte.strftime(FORMATO)}) or self._hay({"anio": anio, "semana_cerrada": semana}):
                return None
            horas = (ahora - corte).total_seconds() / 3600
            return {"semana": semana, "corte": corte, "horas": int(horas), "fuera_ventana": horas > VENTANA_HORAS}
        except Exception:
            return None

    def _detectar_cierre(self, ahora: datetime, acc: Dict, ignorar_ventana: bool = False):
        semana, corte = self._config_actual()
        if not semana or not corte or ahora < corte:
            return
        if not ignorar_ventana and ahora - corte > timedelta(hours=VENTANA_HORAS):
            acc.setdefault("avisos", []).append(
                f"El corte {corte:{FORMATO}} venció hace más de {VENTANA_HORAS} h: no se procesa solo; defínalo en Configuración.")
            return
        anio = Config.get_anio_actual()
        clave = corte.strftime(FORMATO)
        if self._hay({"corte_cerrado": clave}) or self._hay({"anio": anio, "semana_cerrada": semana}):
            return

        p = self._propuesta(semana, corte, ahora)
        fila = {
            "anio": anio, "semana_cerrada": semana, "corte_cerrado": clave,
            "semana_propuesta": p["semana"], "corte_propuesto": p["corte"].strftime(FORMATO),
            "semana_previa": semana, "corte_previo": clave, "aplicado": False,
            "nota": "\n".join(p["notas"]) or None, "estado": "PROVISIONAL",
        }
        try:
            r = self._t("cierres_corte").insert(fila).execute()
        except Exception as e:           # clave única: otra copia ya lo procesó
            print(f"Cierre {clave} ya procesado o no se pudo registrar: {e}")
            return
        cierre = r.data[0]
        # Los cierres anteriores sin validar quedan superados (ya no se les recuerda).
        for viejo in self._t("cierres_corte").select("id").eq("estado", "PROVISIONAL").execute().data or []:
            if viejo["id"] != cierre["id"]:
                self._t("cierres_corte").update({"estado": "SUPERADA"}).eq("id", viejo["id"]).execute()

        aplicado = False
        if p["aplicar"]:
            ok1, d1 = self.db.guardar_configuracion("semana_activa", str(p["semana"]))
            ok2, d2 = (self.db.guardar_configuracion("fecha_corte", p["corte"].strftime(FORMATO)) if ok1 else (False, d1))
            if ok1 and ok2:
                aplicado = True
            else:
                if ok1:
                    self.db.guardar_configuracion("semana_activa", str(semana))   # no dejar a medias
                nota = "\n".join(p["notas"] + [f"No se pudo aplicar el cambio: {d2 or d1}"])
                self._t("cierres_corte").update({"nota": nota}).eq("id", cierre["id"]).execute()
        if aplicado:
            self._t("cierres_corte").update({"aplicado": True}).eq("id", cierre["id"]).execute()
        self.db.registrar_log(
            usuario="SISTEMA", accion="CIERRE_CORTE",
            detalle=(f"Corte {clave} cerrado (semana {semana}). "
                     + (f"Aplicado provisionalmente: semana {p['semana']}, corte {p['corte']:{FORMATO}}."
                        if aplicado else "No se cambió la configuración.")))
        acc["cierre"] = {"semana_cerrada": semana, "semana_propuesta": p["semana"], "aplicado": aplicado}

    # ------------------------------------------------------------ aviso inicial

    def _excel_borrador(self, c: Dict) -> Optional[List[Tuple[str, bytes, str]]]:
        try:
            nombre, contenido = self.generar_excel(c["anio"], c["semana_cerrada"], parsear_corte(c["corte_cerrado"]), borrador=True)
            return [(nombre, contenido, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
        except Exception as e:
            print(f"No se pudo generar el resumen borrador: {e}")
            return None

    def generar_excel(self, anio: int, semana: int, corte: Optional[datetime], borrador: bool = False) -> Tuple[str, bytes]:
        from src.resumen_excel import generar_excel, nombre_archivo, recolectar
        redes = self.redes_fn() if self.redes_fn else __import__("src.data_loader", fromlist=["x"]).get_data_loader().obtener_redes()
        datos = recolectar(self.db, anio, semana, redes, corte, self.avance_fn, self.limpiar_fn)
        return nombre_archivo(anio, semana, borrador), generar_excel(datos)

    def _avisos_iniciales_pendientes(self, acc: Dict):
        pendientes = (self._t("cierres_corte").select("*").eq("estado", "PROVISIONAL")
                      .is_("aviso_inicial_at", "null").execute().data or [])
        for c in pendientes:
            ahora = _iso_utc()
            r = (self._t("cierres_corte").update({"aviso_inicial_at": ahora}).eq("id", c["id"])
                 .is_("aviso_inicial_at", "null").execute().data)
            if not r:
                continue       # otra copia lo reservó
            adj = self._excel_borrador(c)
            dest = self.destinatarios()
            enviados = 0
            for d in dest:
                ok, _ = correos.enviar_aviso_cierre(self.sender, d["email"], d["nombre"], c,
                                                    len(Config.RECORDATORIOS_CIERRE_HORAS), adj)
                enviados += 1 if ok else 0
            if enviados == 0:
                self._t("cierres_corte").update({"aviso_inicial_at": None}).eq("id", c["id"]).execute()
                acc.setdefault("avisos", []).append("No se pudo enviar el aviso de cierre; se reintentará.")
            elif adj:
                self._t("cierres_corte").update({"resumen_borrador_enviado_at": ahora}).eq("id", c["id"]).execute()
            acc["aviso_inicial"] = enviados

    # ------------------------------------------------------------ recordatorios

    def horarios_recordatorio(self, c: Dict) -> List[datetime]:
        """Las horas de los recordatorios: el día hábil siguiente al corte, en las horas configuradas."""
        corte = parsear_corte(c.get("corte_cerrado"))
        if not corte:
            return []
        dia = siguiente_habil(corte.date())
        horas = []
        for h in Config.RECORDATORIOS_CIERRE_HORAS:
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", h)
            if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
                horas.append(datetime.combine(dia, time(int(m.group(1)), int(m.group(2)))))
        return sorted(horas)

    def _recordatorios(self, ahora: datetime, acc: Dict):
        pendientes = (self._t("cierres_corte").select("*").eq("estado", "PROVISIONAL").execute().data or [])
        for c in pendientes:
            if not c.get("aviso_inicial_at"):
                continue
            slots = self.horarios_recordatorio(c)
            hechos = int(c.get("recordatorios_enviados") or 0)
            vencidos = [i for i, s in enumerate(slots) if s <= ahora]
            if not vencidos or vencidos[-1] < hechos:
                continue
            numero = vencidos[-1] + 1       # si hubo varios vencidos (proceso detenido), se manda solo el último
            r = (self._t("cierres_corte").update({"recordatorios_enviados": numero, "ultimo_recordatorio_at": _iso_utc()})
                 .eq("id", c["id"]).eq("estado", "PROVISIONAL").eq("recordatorios_enviados", hechos).execute().data)
            if not r:
                continue
            enviados = 0
            for d in self.destinatarios():
                ok, _ = correos.enviar_recordatorio_validacion(self.sender, d["email"], d["nombre"], c, numero, len(slots))
                enviados += 1 if ok else 0
            if enviados == 0:
                self._t("cierres_corte").update({"recordatorios_enviados": hechos}).eq("id", c["id"]).execute()
            acc["recordatorios"] = acc.get("recordatorios", 0) + (1 if enviados else 0)

    # ------------------------------------------------------------ validación

    def validar(self, cierre_id, usuario: str, nombre: str, semana: int, corte: datetime,
                ahora: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Una persona confirma (o corrige) la semana activa y la fecha de corte.
        Solo la primera validación cuenta; las demás ven quién validó.
        """
        ahora = ahora or ahora_lima()
        c = self.obtener(cierre_id)
        if not c:
            return False, "No se encontró el cierre."
        if c.get("estado") != "PROVISIONAL":
            return False, self.texto_ya_validado(c) if c.get("estado") == "VALIDADA" else "Este cierre ya no está pendiente."
        info = self.db.obtener_anio_activo_epidemiologico() or {}
        maximo = int(info.get("semanas") or 53)
        if not (1 <= int(semana) <= maximo):
            return False, f"La semana debe estar entre 1 y {maximo}."
        if corte <= ahora:
            return False, "La fecha de corte debe ser posterior a este momento."

        corte_txt = corte.strftime(FORMATO)
        correccion = (int(semana) != c.get("semana_propuesta")) or (corte_txt != c.get("corte_propuesto"))
        r = (self._t("cierres_corte").update({
            "estado": "VALIDADA", "validado_por": usuario, "validado_por_nombre": nombre,
            "fecha_validacion": _iso_utc(), "semana_validada": int(semana), "corte_validado": corte_txt,
            "hubo_correccion": bool(correccion)})
            .eq("id", cierre_id).eq("estado", "PROVISIONAL").execute().data)
        if not r:
            return False, self.texto_ya_validado(self.obtener(cierre_id) or c)

        actual_s, actual_c = self._config_actual()
        fallo = None
        if actual_s != int(semana):
            ok, d = self.db.guardar_configuracion("semana_activa", str(int(semana)))
            fallo = None if ok else d
        if not fallo and (actual_c is None or actual_c.strftime(FORMATO) != corte_txt):
            ok, d = self.db.guardar_configuracion("fecha_corte", corte_txt)
            fallo = None if ok else d
        if fallo:
            self._t("cierres_corte").update({"estado": "PROVISIONAL", "validado_por": None, "validado_por_nombre": None,
                                             "fecha_validacion": None}).eq("id", cierre_id).execute()
            return False, f"No se pudo guardar la configuración: {fallo}"

        self.db.registrar_log(
            usuario=usuario, accion="VALIDAR_SEMANA",
            detalle=f"Semana {int(semana)} y corte {corte_txt} validados"
                    + (f" (corrigió la propuesta: semana {c.get('semana_propuesta')}, corte {c.get('corte_propuesto')})"
                       if correccion else " (sin cambios a la propuesta)"))
        self.avisar_validado(cierre_id)
        return True, f"Semana {int(semana)} validada. Se avisó a las demás personas."

    def avisar_validado(self, cierre_id) -> int:
        """UN correo corto a los demás: ya fue validado. Se reserva antes de enviar (no se duplica)."""
        r = (self._t("cierres_corte").update({"aviso_validado_enviado": True}).eq("id", cierre_id)
             .eq("estado", "VALIDADA").eq("aviso_validado_enviado", False).execute().data)
        if not r:
            return 0
        c = r[0]
        enviados = 0
        for d in self.destinatarios(excluir_usuario=c.get("validado_por")):
            ok, _ = correos.enviar_aviso_validado(self.sender, d["email"], d["nombre"], c)
            enviados += 1 if ok else 0
        return enviados

    def _avisos_validado_pendientes(self, acc: Dict):
        pend = (self._t("cierres_corte").select("id").eq("estado", "VALIDADA")
                .eq("aviso_validado_enviado", False).execute().data or [])
        for c in pend:
            acc["aviso_validado"] = acc.get("aviso_validado", 0) + self.avisar_validado(c["id"])

    @staticmethod
    def texto_ya_validado(c: Dict) -> str:
        from src.solicitudes_password import fecha_lima
        por = c.get("validado_por_nombre") or c.get("validado_por") or "otra persona"
        return f"Ya fue validada por {por} el {fecha_lima(c.get('fecha_validacion'))}."

    # ------------------------------------------------------------ resumen

    def validar_resumen(self, cierre_id, usuario: str, nombre: str) -> Tuple[bool, str]:
        """
        Una persona de la OIIS valida el resumen de la semana cerrada; recién entonces se
        envía a la entidad externa (y una copia a los administradores).
        """
        c = self.obtener(cierre_id)
        if not c:
            return False, "No se encontró el cierre."
        if c.get("resumen_estado") != "PENDIENTE":
            quien = c.get("resumen_validado_por_nombre") or c.get("resumen_validado_por") or "otra persona"
            return False, f"El resumen ya fue validado por {quien}."
        r = (self._t("cierres_corte").update({
            "resumen_estado": "VALIDADO", "resumen_validado_por": usuario,
            "resumen_validado_por_nombre": nombre, "resumen_fecha_validacion": _iso_utc()})
            .eq("id", cierre_id).eq("resumen_estado", "PENDIENTE").execute().data)
        if not r:
            return False, "El resumen ya fue validado por otra persona."
        self.db.registrar_log(usuario=usuario, accion="VALIDAR_RESUMEN",
                              detalle=f"Resumen de la semana {c['semana_cerrada']} ({c['anio']}) validado")
        ok, msg = self._enviar_a_externos(c, usuario, nombre, tras_validar=True)
        if not ok and not msg.startswith("Resumen validado"):
            # No se pudo ni generar el Excel: se deshace la validación para poder reintentar.
            self._t("cierres_corte").update({"resumen_estado": "PENDIENTE", "resumen_validado_por": None,
                                             "resumen_validado_por_nombre": None, "resumen_fecha_validacion": None}
                                            ).eq("id", cierre_id).execute()
        return ok, msg

    def _enviar_a_externos(self, c: Dict, usuario: str, nombre: str, tras_validar: bool = False) -> Tuple[bool, str]:
        """Genera el Excel y lo envía a la entidad externa (y copia a los administradores)."""
        externos = self.listar_externos(solo_activos=True)
        prefijo = "Resumen validado. " if tras_validar else ""
        if not externos:
            return True, (prefijo + "No hay destinatarios externos registrados: "
                          "un SUPER_ADMIN debe registrarlos y luego usar «Reintentar el envío».")
        try:
            nom, contenido = self.generar_excel(c["anio"], c["semana_cerrada"], parsear_corte(c["corte_cerrado"]))
        except Exception as e:
            return False, f"No se pudo generar el Excel: {e}"
        adj = [(nom, contenido, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
        mensaje = "Se remite el resumen de cumplimiento por red de la semana indicada, validado por la OIIS."
        enviados_ext = 0
        for e in externos:
            nombre_e = f"{e.get('nombre', '')} {e.get('apellidos', '')}".strip()
            ok, _ = correos.enviar_resumen(self.sender, e["correo"], nombre_e, c["semana_cerrada"], c["anio"],
                                           mensaje, f"{nombre} (OIIS)", adj)
            enviados_ext += 1 if ok else 0
        if enviados_ext:
            self._t("cierres_corte").update({"resumen_estado": "ENVIADO", "resumen_enviado_externo_at": _iso_utc()}
                                            ).eq("id", c["id"]).execute()
            self.db.registrar_log(usuario=usuario, accion="ENVIAR_RESUMEN_EXTERNO",
                                  detalle=f"Resumen semana {c['semana_cerrada']} enviado a {enviados_ext} destinatario(s) externo(s)")
            for d in self.destinatarios():
                correos.enviar_resumen(self.sender, d["email"], d["nombre"], c["semana_cerrada"], c["anio"],
                                       f"Versión validada por {nombre}. Se envió también a la entidad externa.",
                                       f"{nombre} (OIIS)", adj)
            return True, f"{prefijo}Resumen enviado a {enviados_ext} destinatario(s) externo(s)."
        return True, prefijo + "No se pudo enviar a la entidad externa. Use «Reintentar el envío»."

    def reintentar_envio_externo(self, cierre_id, usuario: str, nombre: str) -> Tuple[bool, str]:
        """Reenvía a la entidad externa un resumen ya validado que no llegó a enviarse."""
        c = self.obtener(cierre_id)
        if not c:
            return False, "No se encontró el cierre."
        if c.get("resumen_estado") != "VALIDADO":
            return False, "Solo se puede reintentar un resumen validado que aún no se envió."
        return self._enviar_a_externos(c, usuario, nombre)

    def enviar_resumen_manual(self, usuario: str, nombre_admin: str, anio: int, semana: int, nombres: str,
                              apellidos: str, correo: str, mensaje: str) -> Tuple[bool, str]:
        """Panel de envío manual (todos los administradores): manda el Excel a una persona."""
        nombres, apellidos = (nombres or "").strip(), (apellidos or "").strip()
        correo = normalizar_correo(correo)
        mensaje = (mensaje or "").strip()
        if len(nombres) < 2 or len(apellidos) < 2:
            return False, "Ingrese nombres y apellidos de la persona destinataria."
        if not formato_valido(correo):
            return False, "El correo no tiene un formato válido."
        if len(mensaje) > MAX_TEXTO:
            return False, f"El mensaje es muy largo (máximo {MAX_TEXTO} caracteres)."
        if not (1 <= int(semana) <= 53):
            return False, "Semana inválida."
        _, corte = self._config_actual()
        ult = None
        for c in self.listar(60):
            if c["anio"] == anio and c["semana_cerrada"] == int(semana):
                ult = c
                break
        corte_ref = parsear_corte(ult["corte_cerrado"]) if ult else None
        try:
            nom, contenido = self.generar_excel(anio, int(semana), corte_ref)
        except Exception as e:
            return False, f"No se pudo generar el Excel: {e}"
        ok, motivo = correos.enviar_resumen(
            self.sender, correo, f"{nombres} {apellidos}", int(semana), anio, mensaje,
            f"{nombre_admin} (OIIS)", [(nom, contenido, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")])
        if not ok:
            return False, f"No se pudo enviar el correo: {motivo}"
        self.db.registrar_log(usuario=usuario, accion="ENVIAR_RESUMEN",
                              detalle=f"Resumen semana {int(semana)} ({anio}) enviado a {correo}")
        return True, f"Resumen enviado a {correo}."

    # ------------------------------------------------------------ destinatarios externos

    def listar_externos(self, solo_activos: bool = False) -> List[Dict]:
        try:
            q = self._t("destinatarios_externos").select("*")
            if solo_activos:
                q = q.eq("activo", True)
            return q.order("id").execute().data or []
        except Exception as e:
            print(f"Destinatarios externos no disponibles: {e}")
            return []

    def agregar_externo(self, nombres: str, apellidos: str, correo: str, creado_por: str) -> Tuple[bool, str]:
        nombres, apellidos, correo = (nombres or "").strip(), (apellidos or "").strip(), normalizar_correo(correo)
        if len(nombres) < 2:
            return False, "Ingrese el nombre."
        if not formato_valido(correo):
            return False, "El correo no tiene un formato válido."
        if any(normalizar_correo(e.get("correo")) == correo for e in self.listar_externos()):
            return False, "Ese correo ya está registrado."
        try:
            self._t("destinatarios_externos").insert(
                {"nombre": nombres, "apellidos": apellidos, "correo": correo, "activo": True, "creado_por": creado_por}).execute()
        except Exception as e:
            return False, f"No se pudo registrar: {e}"
        self.db.registrar_log(usuario=creado_por, accion="AGREGAR_DESTINATARIO_EXTERNO", detalle=f"{correo} registrado")
        return True, f"{correo} registrado."

    def cambiar_estado_externo(self, ext_id, activo: bool, usuario: str) -> bool:
        r = self._t("destinatarios_externos").update({"activo": bool(activo)}).eq("id", ext_id).execute().data
        if r:
            self.db.registrar_log(usuario=usuario, accion="EDITAR_DESTINATARIO_EXTERNO",
                                  detalle=f"{r[0].get('correo')} {'activado' if activo else 'desactivado'}")
        return bool(r)

    def eliminar_externo(self, ext_id, usuario: str) -> bool:
        r = self._t("destinatarios_externos").delete().eq("id", ext_id).execute().data
        if r:
            self.db.registrar_log(usuario=usuario, accion="ELIMINAR_DESTINATARIO_EXTERNO", detalle=f"{r[0].get('correo')} eliminado")
        return bool(r)

    # ------------------------------------------------------------ ciclo completo

    def procesar(self, ahora: Optional[datetime] = None, ignorar_ventana: bool = False) -> Dict:
        """
        Un ciclo del proceso programado. Devuelve lo que hizo (para el registro y las pruebas).
        `ignorar_ventana=True` solo lo usa una persona desde el panel (cierre manual): procesa un corte
        vencido hace más de VENTANA_HORAS, porque ella decide hacerlo.
        """
        ahora = ahora or ahora_lima()
        acc: Dict = {}
        if not self.disponible():
            return {"omitido": "Falta ejecutar sql/10_programador_cierres_respaldos.sql"}
        self._detectar_cierre(ahora, acc, ignorar_ventana)
        self._avisos_iniciales_pendientes(acc)
        self._recordatorios(ahora, acc)
        self._avisos_validado_pendientes(acc)
        return acc


_cierres = None


def get_cierres() -> Cierres:
    global _cierres
    if _cierres is None:
        _cierres = Cierres()
    return _cierres
