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
    var BREVO_API_KEY  = 'TU_BREVO_API_KEY';   /* ← reemplazar */
    var BREVO_LIST_ID  = 0;                     /* ← reemplazar con el ID numérico de tu lista */

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

      var body = JSON.stringify({
        email: email,
        listIds: [BREVO_LIST_ID],
        updateEnabled: true
      });

      var xhr = new XMLHttpRequest();
      xhr.open('POST', 'https://api.brevo.com/v3/contacts');
      xhr.setRequestHeader('api-key', BREVO_API_KEY);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('Accept', 'application/json');
      xhr.onload = function () {
        btn.disabled    = false;
        btn.textContent = 'Suscribirme →';
        if (xhr.status === 201 || xhr.status === 204 || xhr.status === 200) {
          nForm.innerHTML = '<p class="newsletter-msg ok" style="font-size:1.05rem;">✓ ¡Suscrito! Recibirás el primer boletín mañana.</p>';
        } else {
          var resp = {};
          try { resp = JSON.parse(xhr.responseText); } catch (_) {}
          if (resp.code === 'duplicate_parameter') {
            msgEl.textContent = '¡Ya estabas suscrito! Te tenemos en la lista.';
            msgEl.className   = 'newsletter-msg ok';
          } else {
            msgEl.textContent = 'Algo ha ido mal. Inténtalo de nuevo o escríbenos a info@oponoticias.com';
            msgEl.className   = 'newsletter-msg err';
          }
        }
      };
      xhr.onerror = function () {
        btn.disabled    = false;
        btn.textContent = 'Suscribirme →';
        msgEl.textContent = 'Error de conexión. Inténtalo de nuevo.';
        msgEl.className   = 'newsletter-msg err';
      };
      xhr.send(body);
    });
  }

})();
