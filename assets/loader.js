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

/* ── Validación de puestos (listas compartidas) ─────────────────────────── */

// Si el puesto CONTIENE alguno de estos fragmentos → no sirve
const PUESTO_SUBSTRINGS_MALOS = [
  'ESPECIFICAD', 'NO DISPONIBLE', 'NO DETERMINAD', 'NO INDICAD',
  'SIN ESPECIF', 'PUESTO DE TRABAJO', 'PUESTO NO', 'PLAZA NO',
  'PERSONAL FUNCIONARIO', 'PERSONAL LABORAL', 'FUNCIONARIO Y LABORAL',
  'DENOMINACION', 'DENOMINACIÓN', 'NO CONSTA', 'A DETERMINAR'
];
// Si el puesto ES EXACTAMENTE uno de estos → no sirve
const PUESTO_EXACTOS_MALOS = [
  'PLAZA', 'PLAZAS', 'VARIAS PLAZAS', '1 PLAZA', 'PERSONAL',
  'FUNCIONARIO', 'TITULADO', 'TITULADA', 'PUESTO', 'PUESTOS',
  'TRABAJO', 'EMPLEO', 'VACANTE', 'VACANTES'
];
// Si el resumen completo contiene esto → no es una convocatoria útil
const RESUMEN_NEGATIVOS = [
  'MODIFICACIÓN TRIBUNAL', 'MODIFICACION TRIBUNAL', 'MODIFICACIÓN DEL TRIBUNAL',
  'CORRECCIÓN DE ERRORES', 'CORRECCION DE ERRORES', 'SE CORRIGEN ERRORES',
  'DECLARA DESIERTO', 'INHÁBIL', 'INHABIL', 'LISTA DE ESPERA', 'BOLSA DE'
];

/** ¿El puesto es específico y útil para mostrar/destacar? */
function puestoValido(puesto) {
  if (!puesto) return false;
  const p = puesto.toUpperCase().trim();
  if (p.length < 4) return false;
  if (PUESTO_EXACTOS_MALOS.includes(p)) return false;
  if (PUESTO_SUBSTRINGS_MALOS.some(s => p.includes(s))) return false;
  return true;
}

/** Extrae el número de plazas para puntuar (VARIAS = 6 estimado) */
function numPlazas(plazasStr) {
  if (!plazasStr) return 0;
  const up = plazasStr.toUpperCase();
  const m = up.match(/(\d+)/);
  if (m) return parseInt(m[1], 10);
  if (up.includes('VARIAS')) return 6; // plural sin número concreto
  return 1;
}

/** ¿Convocatoria apta para destacar / ticker? */
function convocatoriaValida(c) {
  const r = (c.resumen_claude || '').toUpperCase();
  if (RESUMEN_NEGATIVOS.some(n => r.includes(n))) return false;
  const parsed = parsearResumen(c.resumen_claude);
  return parsed && puestoValido(parsed.puesto);
}

/**
 * Puntúa una convocatoria. La prioridad principal es el NÚMERO DE PLAZAS,
 * seguido de la especificidad del puesto y la variedad de categoría.
 */
function puntuarConvocatoria(c) {
  if (!convocatoriaValida(c)) return -1000;
  const parsed = parsearResumen(c.resumen_claude);

  let pts = 10;                            // base por ser válida
  pts += Math.min(numPlazas(parsed.plazas), 60);  // más plazas = más relevante
  if (parsed.puesto.length > 12) pts += 4; // puesto descriptivo
  if (parsed.puesto.length > 22) pts += 3;
  if (c.categoria && c.categoria !== 'Administración') pts += 3; // variedad
  return pts;
}

/** Elige la mejor convocatoria para destacar. */
function seleccionarDestacada(convs) {
  const ordenadas = [...convs]
    .map(c => ({ c, score: puntuarConvocatoria(c) }))
    .sort((a, b) => b.score - a.score);
  const mejor = ordenadas[0];
  return (mejor && mejor.score > -1000) ? mejor.c : convs[0];
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
  // Para el grid: solo convocatorias válidas, más recientes primero
  const restantes  = convs.filter(c => c.id !== featured.id && convocatoriaValida(c));

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
      const orgUp = organismo.toUpperCase();
      const lugarRedundante = !parsed.lugar
        || orgUp.includes(parsed.lugar.split(' ')[0])
        || parsed.lugar.toUpperCase().includes(orgUp.split(' ')[0]);
      p.innerHTML = `
        <span style="display:block;font-size:1.15rem;font-weight:700;color:var(--primary);margin-bottom:12px;">${parsed.puesto}</span>
        <span style="display:flex;flex-wrap:wrap;gap:18px;font-size:0.92rem;color:var(--gray);">
          <span>🔢 ${parsed.plazas}</span>
          ${!lugarRedundante ? `<span>📍 ${truncar(parsed.lugar, 50)}</span>` : ''}
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

      const art = document.createElement('article');
      art.className = 'conv-card';
      art.innerHTML = `
        <div class="conv-card-strip"></div>
        <div class="conv-card-body">
          <span class="conv-tag">${c.categoria}</span>
          <h3><a href="${c.enlace}" target="_blank" rel="noopener">${organismo}</a></h3>
          <p style="font-weight:600;color:var(--primary);text-transform:uppercase;font-size:0.9rem;letter-spacing:0.02em;">${desc}</p>
          <div class="conv-meta">
            <span class="src">${parsed ? parsed.plazas : 'BOE'}</span>
            <span>${fmtCorto(c.fecha)}</span>
          </div>
        </div>`;
      grid.appendChild(art);
    });
  }

  /* 4 · Ticker — solo convocatorias con puesto real, mejores primero */
  const track = document.querySelector('.ticker-track');
  if (track) {
    const tickerItems = convs
      .filter(convocatoriaValida)
      .sort((a, b) => puntuarConvocatoria(b) - puntuarConvocatoria(a))
      .slice(0, 12)
      .map(c => {
        const p = parsearResumen(c.resumen_claude);
        return `<span>${c.categoria} — ${p.plazas} · ${p.puesto}</span>`;
      });

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
