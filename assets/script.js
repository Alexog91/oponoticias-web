/* ============================================================
   OPONOTICIAS — interacciones ligeras (vanilla JS)
   Scroll-reveal · header sticky · menú móvil
   ============================================================ */
(function () {
  'use strict';

  /* ── Header con sombra al hacer scroll ── */
  var header = document.querySelector('.site-header');
  if (header) {
    var onScroll = function () {
      header.classList.toggle('scrolled', window.scrollY > 8);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ── Menú móvil ── */
  var toggle = document.querySelector('.nav-toggle');
  var nav = document.querySelector('.nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      nav.classList.toggle('open');
      var expanded = nav.classList.contains('open');
      toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    });
    nav.querySelectorAll('.nav-links a').forEach(function (a) {
      a.addEventListener('click', function () { nav.classList.remove('open'); });
    });
  }

  /* ── Scroll-reveal con IntersectionObserver ── */
  var reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && reveals.length) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add('in'); });
  }

  /* ── Filtros de categoría (solo visual, sin recarga) ── */
  var pills = document.querySelectorAll('.filter-pill');
  if (pills.length) {
    pills.forEach(function (pill) {
      pill.addEventListener('click', function () {
        pills.forEach(function (p) { p.classList.remove('active'); });
        pill.classList.add('active');
      });
    });
  }

  /* ── Newsletter subscription form ── */
  var nForm = document.getElementById('newsletterForm');
  if (nForm) {
    nForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var emailInput = document.getElementById('newsletterEmail');
      var msgEl      = document.getElementById('newsletterMsg');
      var btn        = nForm.querySelector('button[type="submit"]');
      var email      = emailInput.value.trim();

      if (!email) return;

      btn.disabled    = true;
      btn.textContent = 'Enviando…';
      msgEl.textContent = '';
      msgEl.className   = 'newsletter-msg';

      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/subscribe');
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onload = function () {
        btn.disabled    = false;
        btn.textContent = 'Enviarme la guía →';
        var resp = {};
        try { resp = JSON.parse(xhr.responseText); } catch (_) {}
        if (xhr.status === 200 && resp.ok) {
          // Marca como suscrito para que el pop-up no le moleste después.
          try { localStorage.setItem('on_nl_popup', JSON.stringify({ status: 'subscribed', ts: Date.now() })); } catch (_) {}
          nForm.innerHTML = '<p class="newsletter-msg ok" style="font-size:1.05rem;">✓ ¡Listo! Te hemos enviado el calendario a tu correo. Revisa tu bandeja (y la carpeta de spam por si acaso).</p>';
        } else {
          msgEl.textContent = 'Algo ha ido mal. Inténtalo de nuevo o escríbenos a info@oponoticias.com';
          msgEl.className   = 'newsletter-msg err';
        }
      };
      xhr.onerror = function () {
        btn.disabled    = false;
        btn.textContent = 'Enviarme la guía →';
        msgEl.textContent = 'Error de conexión. Inténtalo de nuevo.';
        msgEl.className   = 'newsletter-msg err';
      };
      xhr.send(JSON.stringify({ email: email }));
    });
  }

  /* ── Pop-up de newsletter (no intrusivo, SEO-safe) ──────────
     Reglas:
     · NUNCA al cargar. Desktop → exit-intent (el cursor sale por
       arriba). Móvil/táctil → tras >55% de scroll y >30 s en la
       página (fuera de la ventana que Google penaliza como
       "interstitial intrusivo").
     · Máximo una vez por sesión. Si se cierra, no reaparece en
       30 días; si el visitante se suscribe, no reaparece nunca.
     · No se muestra en páginas legales ni de contacto.        */
  (function nlPopup() {
    var STORE_KEY = 'on_nl_popup';
    var SESSION_KEY = 'on_nl_popup_session';
    var COOLDOWN_DAYS = 30;
    var path = location.pathname.toLowerCase();

    var SKIP = ['privacidad', 'cookies', 'aviso-legal', 'contacto', 'calendario'];
    if (SKIP.some(function (s) { return path.indexOf(s) !== -1; })) return;

    function blocked() {
      try {
        if (sessionStorage.getItem(SESSION_KEY)) return true;
        var raw = localStorage.getItem(STORE_KEY);
        if (!raw) return false;
        var rec = JSON.parse(raw);
        if (rec.status === 'subscribed') return true;
        var ageDays = (Date.now() - (rec.ts || 0)) / 86400000;
        return ageDays < COOLDOWN_DAYS;
      } catch (_) { return false; }
    }
    function remember(status) {
      try { localStorage.setItem(STORE_KEY, JSON.stringify({ status: status, ts: Date.now() })); } catch (_) {}
    }

    if (blocked()) return;

    // Ruta relativa a privacidad.html según la profundidad de la URL.
    function privacyHref() {
      var dir = location.pathname.replace(/\/[^/]*$/, '');
      var depth = dir.split('/').filter(Boolean).length;
      return (depth > 0 ? new Array(depth + 1).join('../') : '') + 'privacidad.html';
    }

    var overlay = null, lastFocus = null, shown = false, armed = false;
    var startTs = Date.now();
    var isTouch = window.matchMedia && window.matchMedia('(hover: none), (pointer: coarse)').matches;

    function build() {
      overlay = document.createElement('div');
      overlay.className = 'nl-pop-overlay';
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');
      overlay.setAttribute('aria-labelledby', 'nlPopTitle');
      overlay.innerHTML =
        '<div class="nl-pop">' +
          '<button type="button" class="nl-pop-close" aria-label="Cerrar">&times;</button>' +
          '<span class="eyebrow">Guía gratuita</span>' +
          '<h2 id="nlPopTitle">Descárgate gratis el Calendario del Opositor 2026</h2>' +
          '<p class="nl-pop-sub">Te lo enviamos al instante a tu correo. Y de regalo, cada mañana el resumen del BOE. Sin spam, cancela cuando quieras.</p>' +
          '<ul class="nl-pop-perks">' +
            '<li>Calendario y Guía del Opositor 2026 (PDF)</li>' +
            '<li>Resumen diario de convocatorias nuevas</li>' +
            '<li>Gratis para siempre</li>' +
          '</ul>' +
          '<form id="nlPopForm" novalidate>' +
            '<input type="email" id="nlPopEmail" name="email" placeholder="tu@email.com" required autocomplete="email">' +
            '<button type="submit" class="btn btn-primary">Enviarme la guía →</button>' +
            '<p class="newsletter-legal">Al suscribirte aceptas nuestra <a href="' + privacyHref() + '">política de privacidad</a>. Sin spam.</p>' +
            '<div class="newsletter-msg" id="nlPopMsg" aria-live="polite"></div>' +
          '</form>' +
        '</div>';
      document.body.appendChild(overlay);

      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) close('dismissed');
      });
      overlay.querySelector('.nl-pop-close').addEventListener('click', function () { close('dismissed'); });
      overlay.querySelector('#nlPopForm').addEventListener('submit', submit);
    }

    function open() {
      if (shown) return;
      shown = true;
      try { sessionStorage.setItem(SESSION_KEY, '1'); } catch (_) {}
      remember('seen'); // aunque lo ignore, no reaparece en 14 días
      detachTriggers();
      build();
      lastFocus = document.activeElement;
      document.body.classList.add('nl-pop-lock');
      requestAnimationFrame(function () {
        overlay.classList.add('open');
        var inp = overlay.querySelector('#nlPopEmail');
        if (inp) inp.focus();
      });
      document.addEventListener('keydown', onKey);
    }

    function close(reason) {
      if (!overlay) return;
      overlay.classList.remove('open');
      document.removeEventListener('keydown', onKey);
      document.body.classList.remove('nl-pop-lock');
      if (reason) remember(reason);
      if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (_) {} }
      var dead = overlay;
      setTimeout(function () { if (dead && dead.parentNode) dead.parentNode.removeChild(dead); }, 400);
      overlay = null;
    }

    function onKey(e) {
      if (e.key === 'Escape' || e.keyCode === 27) { close('dismissed'); return; }
      if ((e.key === 'Tab' || e.keyCode === 9) && overlay) {
        var f = overlay.querySelectorAll('button, [href], input');
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }

    function submit(e) {
      e.preventDefault();
      var input = overlay.querySelector('#nlPopEmail');
      var msg   = overlay.querySelector('#nlPopMsg');
      var btn   = overlay.querySelector('button[type="submit"]');
      var email = (input.value || '').trim();
      if (!email) return;

      btn.disabled = true; btn.textContent = 'Enviando…';
      msg.textContent = ''; msg.className = 'newsletter-msg';

      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/subscribe');
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onload = function () {
        var resp = {};
        try { resp = JSON.parse(xhr.responseText); } catch (_) {}
        if (xhr.status === 200 && resp.ok) {
          remember('subscribed');
          var form = overlay.querySelector('#nlPopForm');
          if (form) {
            form.outerHTML = '<p class="newsletter-msg ok" style="font-size:1.05rem;">✓ ¡Listo! Te hemos enviado el calendario a tu correo. Revisa tu bandeja (y spam).</p>';
          }
          setTimeout(function () { close(null); }, 2600);
        } else {
          btn.disabled = false; btn.textContent = 'Enviarme la guía →';
          msg.textContent = 'Algo ha ido mal. Inténtalo de nuevo o escríbenos a info@oponoticias.com';
          msg.className = 'newsletter-msg err';
        }
      };
      xhr.onerror = function () {
        btn.disabled = false; btn.textContent = 'Enviarme la guía →';
        msg.textContent = 'Error de conexión. Inténtalo de nuevo.';
        msg.className = 'newsletter-msg err';
      };
      xhr.send(JSON.stringify({ email: email }));
    }

    /* ── Disparadores ── */
    function onExitIntent(e) {
      if (shown) return;
      if (e.clientY <= 0 && !e.relatedTarget && !e.toElement) open();
    }
    function onScrollCheck() {
      if (shown) return;
      var doc = document.documentElement;
      var scrolled = (window.scrollY || doc.scrollTop || 0);
      var height = (doc.scrollHeight - doc.clientHeight) || 1;
      var pct = scrolled / height;
      var elapsed = Date.now() - startTs;
      if (isTouch) {
        if (pct >= 0.55 && elapsed >= 30000) open();
      } else {
        if (pct >= 0.6 && elapsed >= 10000) open();
      }
    }
    function detachTriggers() {
      document.removeEventListener('mouseout', onExitIntent);
      window.removeEventListener('scroll', onScrollCheck);
    }
    function arm() {
      if (armed) return; armed = true;
      if (!isTouch) document.addEventListener('mouseout', onExitIntent);
      window.addEventListener('scroll', onScrollCheck, { passive: true });
    }

    // No "armamos" los triggers hasta pasados unos segundos: así nunca
    // se dispara en la ventana de carga inicial (segura para SEO).
    setTimeout(arm, isTouch ? 4000 : 3000);
  })();

})();
