/* SIREA · Requisitos de contraseña en tiempo real (perfil "red").
 *
 * Réplica en el navegador de src/password_policy.py (perfil "red"): marca cada requisito
 * mientras la persona escribe, sin esperar a que salga del campo. La contraseña NUNCA sale
 * del navegador por aquí; el servidor vuelve a validarla completa al guardar.
 *
 * Qué panel actualiza: el elemento con clase sire-req y atributos data-pw-prefijo y data-cfg
 * que dibuja utils/cuentas_ui.py. Los campos son los de claves PREFIJO_nueva y PREFIJO_confirmar.
 * Si cambia una regla en password_policy.py, cámbiela también aquí (la prueba
 * tests/test_password_js_paridad.py compara ambas con más de 3000 contraseñas).
 */
(function () {
  if (window.__sirePwVivo) { window.__sirePwVivo.montar(); return; }

  var LEET = { '@': 'a', '4': 'a', '0': 'o', '1': 'i', '!': 'i', '3': 'e', '$': 's', '5': 's', '7': 't', '€': 'e' };

  function norm(t) { return String(t == null ? '' : t).normalize('NFD').replace(/\p{Mn}/gu, '').toLowerCase(); }
  function solo(t) { return norm(t).replace(/[^a-z0-9]/g, ''); }
  function destr(t) {
    return Array.from(norm(t)).map(function (c) { return LEET[c] || c; }).join('').replace(/[^a-z0-9]/g, '');
  }
  function largo(p) { return Array.from(p).length; }

  function tieneSecuencia(p, cfg) {
    var q = norm(p), n = 4;
    for (var b = 0; b < cfg.sec.length; b++) {
      var base = cfg.sec[b], inv = base.split('').reverse().join('');
      var dos = [base, inv];
      for (var d = 0; d < 2; d++)
        for (var i = 0; i + n <= dos[d].length; i++)
          if (q.indexOf(dos[d].substr(i, n)) !== -1) return true;
    }
    return false;
  }
  function tieneRepeticion(p) {
    if (/(.)\1{2,}/u.test(p)) return true;
    return /(..)\1{1,}/u.test(p) && new Set(Array.from(p)).size <= 4;
  }
  function esComun(p, cfg) {
    var n = norm(p), s = solo(p), d = destr(p), cand = [n, s, d];
    var base = d.replace(/[^a-z]+$/, ''); if (base) cand.push(base);
    var sinAnio = d.replace(/(19|20)\d{2}$/, ''); if (sinAnio) cand.push(sinAnio);
    for (var i = 0; i < cand.length; i++) if (cand[i] && cfg.comunes.indexOf(cand[i]) !== -1) return true;
    var vars = [s, d];
    for (var j = 0; j < cfg.largas.length; j++)
      for (var k = 0; k < vars.length; k++) if (vars[k].indexOf(cfg.largas[j]) !== -1) return true;
    return false;
  }

  /* {clave: true/false} para el perfil "red". */
  function evaluar(p, cfg) {
    var plano = destr(p), L = largo(p), r = {};
    var usaCtx = cfg.ctx.some(function (f) { return plano.indexOf(f) !== -1; });
    var inst = cfg.inst.some(function (w) { return plano.indexOf(w) !== -1; });
    var letra = /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(p), num = /\d/.test(p);
    r.largo = L >= cfg.min;
    r.largo_max = L <= cfg.max && new TextEncoder().encode(p).length <= cfg.bytes;
    r.letras_numero = (letra && num) || L >= cfg.frase;
    r.comun = !!p && !esComun(p, cfg);
    r.contexto = !!p && !usaCtx && !inst;
    r.patron = !!p && !tieneSecuencia(p, cfg) && !tieneRepeticion(p);
    return r;
  }

  function nivel(p, r, cfg) {
    if (!p) return 0;
    var claves = Object.keys(r), cumplidos = claves.filter(function (k) { return r[k]; }).length;
    if (cumplidos === claves.length) return largo(p) >= cfg.frase ? 4 : 3;
    return cumplidos >= claves.length - 2 ? 2 : 1;
  }

  function campo(prefijo, sufijo) {
    var cont = document.querySelector('.st-key-' + prefijo + '_' + sufijo);
    return cont ? cont.querySelector('input') : null;
  }

  function pintar(panel) {
    var cfg; try { cfg = JSON.parse(panel.getAttribute('data-cfg')); } catch (e) { return; }
    var pre = panel.getAttribute('data-pw-prefijo');
    var a = campo(pre, 'nueva'), b = campo(pre, 'confirmar');
    if (!a) return;
    var p = a.value || '', c = b ? (b.value || '') : '';
    var enFoco = document.activeElement === a;
    var r = evaluar(p, cfg), escrita = p.length > 0, todos = escrita;

    panel.querySelectorAll('[data-req]').forEach(function (it) {
      var k = it.getAttribute('data-req'), ok = !!r[k], estado;
      if (!escrita) estado = 'vacio';
      else if (ok) estado = 'ok';
      else estado = (enFoco && cfg.pos.indexOf(k) !== -1) ? 'pend' : 'mal';
      if (!ok) todos = false;
      it.className = 'sire-req-i ' + (estado === 'ok' ? 'ok' : estado === 'mal' ? 'mal' : '');
      it.querySelector('.sire-req-ico').innerHTML = cfg.ico[estado === 'vacio' ? 'vacio' : estado === 'pend' ? 'vacio' : estado];
      var x = it.querySelector('.sire-req-x');
      if (x) {
        x.textContent = (k === 'largo' && escrita && !ok) ? ' · le faltan ' + (cfg.min - largo(p)) : '';
      }
    });

    var n = nivel(p, r, cfg);
    var seg = panel.querySelectorAll('.sire-fuerza-p i');
    seg.forEach(function (s, i) { s.style.background = i < n ? cfg.col[n] : '#E3EEF7'; });
    var et = panel.querySelector('.sire-fuerza-n');
    if (et) { et.textContent = cfg.fz[n]; et.style.color = n ? cfg.col[n] : '#4F6070'; }
    var barra = panel.querySelector('.sire-fuerza-p');
    if (barra) barra.setAttribute('aria-label', 'Fortaleza: ' + cfg.fz[n]);

    var co = panel.querySelector('[data-coincide]');
    if (co) {
      var estadoC = !c ? 'vacio' : (c === p && p ? 'ok' : 'mal');
      co.className = 'sire-req-i ' + (estadoC === 'ok' ? 'ok' : estadoC === 'mal' ? 'mal' : '');
      co.querySelector('.sire-req-ico').innerHTML = cfg.ico[estadoC];
      co.querySelector('.sire-req-t2').textContent = estadoC === 'mal' ? 'Las contraseñas no coinciden' : 'Las dos contraseñas coinciden';
      if (estadoC !== 'ok') todos = false;
    }

    var fin = panel.querySelector('[data-listo]');
    if (fin) {
      var listo = todos && c === p;
      fin.className = 'sire-req-listo ' + (listo ? 'ok' : '');
      fin.textContent = listo ? 'Todo listo: ya puede guardar su contraseña.' : 'Cuando todo esté en verde, podrá guardar.';
    }
  }

  function barrer() { document.querySelectorAll('.sire-req[data-pw-prefijo]').forEach(pintar); }

  /* Prefijo del campo de contraseña al que pertenece el elemento, o null. */
  function prefijoDe(el) {
    if (!el || el.tagName !== 'INPUT') return null;
    var cont = el.closest('[class*="st-key-"]');
    if (!cont) return null;
    var m = /st-key-(.+)_(nueva|confirmar)(?:\s|$)/.exec(cont.className);
    return m ? m[1] : null;
  }

  function repintar(prefijo) {
    var panel = document.querySelector('.sire-req[data-pw-prefijo="' + prefijo + '"]');
    if (panel) pintar(panel);
  }

  /* Solo se reacciona a lo que la persona hace en los campos de contraseña. Al cargar la
     página, o cuando el servidor vuelve a dibujar el panel (por ejemplo tras «Sugerir una
     contraseña»), manda el estado del servidor: el navegador aún puede tener los campos
     con su valor anterior. */
  function alInteractuar(ev) {
    var pre = prefijoDe(ev.target);
    if (pre) setTimeout(function () { repintar(pre); }, 0);
  }

  function alMontar() {
    setTimeout(function () {
      var pre = prefijoDe(document.activeElement);
      if (pre) repintar(pre);
    }, 0);
  }

  document.addEventListener('input', alInteractuar, true);
  document.addEventListener('focusin', alInteractuar, true);
  document.addEventListener('focusout', alInteractuar, true);

  window.__sirePwVivo = { barrer: barrer, montar: alMontar, evaluar: evaluar, nivel: nivel };
  alMontar();
})();
