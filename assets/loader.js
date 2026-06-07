/**
 * OpoNoticias — Loader de datos reales desde Supabase
 */

const SUPABASE_URL = "https://opnbxphxfclazxduhmkp.supabase.co";
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9wbmJ4cGh4ZmNsYXp4ZHVobWtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDQwMzcsImV4cCI6MjA5NDYyMDAzN30.lcMQwdW2HTCeg2X6Qrl0uTmZA73Yr0KdGHf3y3fLMtM";

const MESES_CORTO = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
const MESES_LARGO = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
                     'septiembre','octubre','noviembre','diciembre'];

/* ── Utilidades ─────────────────────────────────────────────────────────── */

function parseFecha(str) {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d) ? null : d;
}

function fmtCorto(str) {
  const d = parseFecha(str);
  if (!d) return '—';
  return `${d.getDate()} ${MESES_CORTO[d.getMonth()]}`;
}

function fmtLargo(str) {
  const d = parseFecha(str);
  if (!d) return '';
  return `${d.getDate()} de ${MESES_LARGO[d.getMonth()]} de ${d.getFullYear()}`;
}

function truncar(texto, max) {
  if (!texto) return '';
  return texto.length > max ? texto.slice(0, max).trimEnd() + '…' : texto;
}

function extraerOrganismo(titulo) {
  const match = titulo.match(/,\s+(?:de la|del|de los|de las|de)\s+(.+?)(?:,\s+(?:por la que|por el que|referente|en la que|sobre|relativa)|$)/i);
  if (match) return match[1].trim();
  const partes = titulo.split(',');
  if (partes.length >= 2) return partes[1].trim().replace(/^de la |^del |^de los |^de las |^de /i, '');
  return truncar(titulo, 80);
}

function extraerTipo(resumen) {
  if (!resumen) return '';
  const partes = resumen.split(' - ');
  for (let i = partes.length - 1; i >= 0; i--) {
    const p = partes[i].trim();
    if (p && !p.match(/^[IVX]+\.\s/) && p.length > 3) return p;
  }
  return '';
}

/**
 * Parsea "3 PLAZAS - POLICÍA LOCAL - CÁDIZ" en { plazas, puesto, lugar }
 */
function parsearResumen(resumen_claude) {
  if (!resumen_claude) return null;
  // Limpiar markdown residual
  const limpio = resumen_claude.replace(/\*\*/g, '').replace(/#+\s/g, '').trim();
  const partes = limpio.split(' - ');
  if (partes.length < 2) return null;
  return {
    plazas: partes[0].trim(),
    puesto: partes[1].trim(),
    lugar:  partes.slice(2).join(' · ').trim()
  };
}

/**
 * Elige la mejor convocatoria para destacar.
 * Sistema de puntuación:
 *  +3  número concreto de plazas (1 PLAZA, 5 PLAZAS...)
 *  +2  puesto específico (no genérico)
 *  +1  categoría distinta de Administración (más variedad)
 *  -10 modificación de tribunal (descartada)
 *  -5  sin puesto concreto
 */
function seleccionarDestacada(convs) {
  const GENERICOS = [
    'NO ESPECIFICADO','NO ESPECIFICADA','SIN ESPECIFICAR',
    'PERSONAL FUNCIONARIO','PERSONAL LABORAL','FUNCIONARIO',
    'PERSONAL','PLAZA','PLAZAS','PUESTO','VARIAS PLAZAS - PLAZA',
    'TITULADO','TITULADA'
  ];
  const NEGATIVOS = [
    'MODIFICACIÓN TRIBUNAL','MODIFICACION TRIBUNAL',
    'CORRECCIÓN DE ERRORES','SE CORRIGEN ERRORES',
    'DECLARA DESIERTO','INHÁBIL'
  ];

  function puntuar(c) {
    const r = (c.resumen_claude || '').toUpperCase();
    if (!r || r.length < 5) return -20;
    if (NEGATIVOS.some(n => r.includes(n))) return -20;

    const partes = r.split(' - ');
    const puesto = partes[1] ? partes[1].trim() : '';

    // Puesto genérico o inútil → descartar
    if (!puesto || GENERICOS.includes(puesto)) return -15;
    if (GENERICOS.some(g => puesto === g)) return -15;

    let pts = 0;

    // Plazas concretas (ej: "3 PLAZAS", "1 PLAZA") pero el puesto debe ser real
    if (/^\d+\s+PLAZA/.test(r) && puesto.length > 5) pts += 3;

    // Puesto específico y largo = buena señal
    if (puesto.length > 8) pts += 2;
    if (puesto.length > 15) pts += 1;

    // Variedad de categoría (priorizar no-Administración)
    if (c.categoria && c.categoria !== 'Administración') pts += 2;

    return pts;
  }

  const ordenadas = [...convs].sort((a, b) => puntuar(b) - puntuar(a));
  return ordenadas[0] || convs[0];
}

async function supaFetch(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: {
      'apikey': SUPABASE_KEY,
      'Authorization': `Bearer ${SUPABASE_KEY}`
    }
  });
  if (!res.ok) throw new Error(`Supabase ${res.status}: ${await res.text()}`);
  return res.json();
}

/* ── PORTADA (index.html) ───────────────────────────────────────────────── */

async function cargarPortada() {
  const convs = await supaFetch('convocatorias?select=*&order=created_at.desc&limit=250');
  if (!convs.length) return;

  /* 1 · Hero badge */
  const badge = document.querySelector('.hero-badge');
  if (badge) {
    const d = parseFecha(convs[0].created_at);
    const fecha = d ? `${d.getDate()} ${MESES_LARGO[d.getMonth()]}` : 'hoy';
    badge.innerHTML = `<span class="dot"></span>Actualizado · ${fecha}`;
  }

  /* 2 · Artículo destacado — elige la mejor convocatoria */
  const featured   = seleccionarDestacada(convs);
  const restantes  = convs.filter(c => c.id !== featured.id);

  /* 2a · Hero card (parte superior derecha) */
  const heroCard = document.querySelector('.hero-card');
  if (heroCard) {
    const parsedHero   = parsearResumen(featured.resumen_claude);
    const organismoH   = extraerOrganismo(featured.titulo);
    const dateEl       = heroCard.querySelector('.date');
    const tagEl        = heroCard.querySelector('.tag');
    const h3El         = heroCard.querySelector('h3');
    const metaEl       = heroCard.querySelector('.hero-card-meta');

    if (dateEl) dateEl.textContent = fmtCorto(featured.fecha);
    if (tagEl)  tagEl.textContent  = featured.categoria;
    if (h3El)   h3El.textContent   = parsedHero ? parsedHero.puesto : extraerTipo(featured.resumen);
    if (metaEl && parsedHero) {
      metaEl.innerHTML = `
        <span>Plazas: <b>${parsedHero.plazas}</b></span>
        <span>Organismo: <b>${truncar(organismoH, 30)}</b></span>`;
    }
  }

  const featuredEl = document.querySelector('.feature-lead');

  if (featuredEl) {
    const parsed   = parsearResumen(featured.resumen_claude);
    const organismo = extraerOrganismo(featured.titulo);

    const eyebrow = featuredEl.querySelector('.eyebrow');
    const h2      = featuredEl.querySelector('h2');
    const p       = featuredEl.querySelector('p');
    const src     = featuredEl.querySelector('.src');
    const link    = featuredEl.querySelector('.conv-readmore');

    if (eyebrow) eyebrow.textContent = `Destacada · ${featured.categoria}`;
    if (h2)      h2.textContent = organismo;

    if (p && parsed) {
      p.innerHTML = `
        <span style="display:flex;flex-wrap:wrap;gap:10px;margin-top:4px;">
          <b style="color:var(--primary)">${parsed.puesto}</b>
        </span>
        <span style="display:flex;flex-wrap:wrap;gap:16px;margin-top:10px;font-size:0.9rem;color:var(--gray);">
          <span>🔢 ${parsed.plazas}</span>
          ${parsed.lugar ? `<span>📍 ${truncar(parsed.lugar, 50)}</span>` : ''}
        </span>`;
    } else if (p) {
      p.textContent = extraerTipo(featured.resumen) || '';
    }

    if (src)  src.textContent = `BOE · ${fmtLargo(featured.fecha)}`;
    if (link) { link.href = featured.enlace; link.target = '_blank'; link.rel = 'noopener'; link.textContent = 'Ver en BOE →'; }
  }

  /* 3 · Grid de 3 tarjetas */
  const grid = document.querySelector('.conv-grid');
  if (grid) {
    grid.innerHTML = '';
    restantes.slice(0, 3).forEach((c) => {
      const organismo = extraerOrganismo(c.titulo);
      const parsed    = parsearResumen(c.resumen_claude);
      const desc      = parsed ? parsed.puesto : extraerTipo(c.resumen);
      const subtxt    = parsed && parsed.lugar ? truncar(parsed.lugar, 40) : '';

      const art = document.createElement('article');
      art.className = 'conv-card';
      art.innerHTML = `
        <div class="conv-card-strip"></div>
        <div class="conv-card-body">
          <span class="conv-tag">${c.categoria}</span>
          <h3><a href="${c.enlace}" target="_blank" rel="noopener">${organismo}</a></h3>
          <p>${desc}${subtxt ? `<br><small style="color:var(--gray)">${subtxt}</small>` : ''}</p>
          <div class="conv-meta">
            <span class="src">${parsed ? parsed.plazas : 'BOE'}</span>
            <span>${fmtCorto(c.fecha)}</span>
          </div>
        </div>`;
      grid.appendChild(art);
    });
  }

  /* 4 · Ticker — solo convocatorias con puesto real */
  const track = document.querySelector('.ticker-track');
  if (track) {
    const MALOS = ['NO ESPECIFICADO','PLAZA','PLAZAS','PERSONAL','FUNCIONARIO','SIN ESPECIFICAR'];
    const tickerItems = convs
      .map(c => ({ c, parsed: parsearResumen(c.resumen_claude) }))
      .filter(({ parsed }) => parsed && parsed.puesto && !MALOS.includes(parsed.puesto.toUpperCase()))
      .slice(0, 10)
      .map(({ c, parsed }) => `<span>${c.categoria} — ${parsed.plazas} · ${parsed.puesto}</span>`);

    if (tickerItems.length) {
      track.innerHTML = [...tickerItems, ...tickerItems].join('');
    }
  }

  /* 5 · Conteos por categoría */
  const todos = await supaFetch('convocatorias?select=categoria');
  const contadores = {};
  todos.forEach(r => {
    if (r.categoria) contadores[r.categoria] = (contadores[r.categoria] || 0) + 1;
  });
  document.querySelectorAll('.cat-card').forEach(card => {
    const nombre  = card.querySelector('h3')?.textContent.trim();
    const countEl = card.querySelector('.count');
    if (nombre && contadores[nombre] && countEl) {
      countEl.textContent = `${contadores[nombre]} convocatorias`;
    }
  });
}

/* ── PÁGINA DE CATEGORÍA ────────────────────────────────────────────────── */

async function cargarCategoria(categoria) {
  const convs = await supaFetch(
    `convocatorias?select=*&categoria=eq.${encodeURIComponent(categoria)}&order=created_at.desc&limit=100`
  );

  const statB = document.querySelector('.cat-hero-stats div:first-child b');
  if (statB) statB.textContent = convs.length;

  const lista = document.querySelector('.cat-list');
  if (!lista) return;

  if (!convs.length) {
    lista.innerHTML = `
      <p style="color:var(--gray);padding:40px 0;text-align:center;">
        No hay convocatorias disponibles para esta categoría todavía.<br>
        <a href="https://t.me/OPONOTICIAS" target="_blank" rel="noopener">Activa las alertas en Telegram →</a>
      </p>`;
    return;
  }

  lista.innerHTML = '';

  convs.forEach((c) => {
    const d   = parseFecha(c.fecha) || parseFecha(c.created_at);
    const dia = d ? d.getDate() : '—';
    const mes = d ? (MESES_CORTO[d.getMonth()].charAt(0).toUpperCase() + MESES_CORTO[d.getMonth()].slice(1)) : '—';

    const organismo = extraerOrganismo(c.titulo);
    const parsed    = parsearResumen(c.resumen_claude);

    // Puesto: info más importante, se muestra en grande
    const puesto = parsed ? parsed.puesto : extraerTipo(c.resumen);
    // Plazas: info secundaria como badge
    const plazas = parsed ? parsed.plazas : '';
    // Lugar: solo mostrar si NO está ya en el organismo (evitar repetición)
    const lugar = parsed ? parsed.lugar : '';
    const organismoUp = organismo.toUpperCase();
    const lugarRedundante = !lugar || organismoUp.includes(lugar.split(' ')[0]) || lugar.toUpperCase().includes(organismoUp.split(' ')[0]);

    const row = document.createElement('article');
    row.className = 'list-row';
    row.innerHTML = `
      <div class="list-date">
        <div class="d">${dia}</div>
        <div class="m">${mes}</div>
      </div>
      <a href="${c.enlace}" target="_blank" rel="noopener" class="list-main">
        <h3>${organismo}</h3>
        ${puesto ? `<p style="margin:3px 0 6px;font-weight:600;font-size:0.92rem;color:var(--primary);text-transform:uppercase;letter-spacing:0.02em;">${puesto}</p>` : ''}
        <div class="list-tags">
          ${plazas ? `<span>${plazas}</span>` : ''}
          ${!lugarRedundante ? `<span>📍 ${truncar(lugar, 35)}</span>` : ''}
        </div>
      </a>
      <span class="list-cta">Ver en BOE →</span>`;
    lista.appendChild(row);
  });

  const pag = document.querySelector('.pagination');
  if (pag) pag.style.display = 'none';
}

/* ── ARRANQUE ───────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const catMeta = document.querySelector('meta[name="opo-categoria"]');
    if (catMeta) {
      await cargarCategoria(catMeta.getAttribute('content'));
    } else if (document.querySelector('.conv-grid')) {
      await cargarPortada();
    }
  } catch (err) {
    console.error('[OpoNoticias loader]', err);
  }
});
