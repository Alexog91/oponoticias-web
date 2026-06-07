/**
 * OpoNoticias — Loader de datos reales desde Supabase
 * Carga convocatorias en portada y páginas de categoría.
 *
 * ⚠️ Sustituye TU_ANON_KEY_AQUI por tu anon key de Supabase
 *    (Settings → API → anon public)
 */

const SUPABASE_URL  = "https://opnbxphxfclazxduhmkp.supabase.co";
const SUPABASE_KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9wbmJ4cGh4ZmNsYXp4ZHVobWtwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkwNDQwMzcsImV4cCI6MjA5NDYyMDAzN30.lcMQwdW2HTCeg2X6Qrl0uTmZA73Yr0KdGHf3y3fLMtM";

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
  // "Resolución de X, de/del [Organismo], por la que / referente a..."
  const match = titulo.match(/,\s+(?:de la|del|de los|de las|de)\s+(.+?)(?:,\s+(?:por la que|por el que|referente|en la que|sobre|relativa)|$)/i);
  if (match) return match[1].trim();
  // Fallback: segunda parte tras la primera coma
  const partes = titulo.split(',');
  if (partes.length >= 2) return partes[1].trim().replace(/^de la |^del |^de los |^de las |^de /i, '');
  return truncar(titulo, 80);
}

function extraerTipo(resumen) {
  // El resumen BOE tiene formato: "II. Sección - Subsección - ÁREA - Tipo de plaza"
  if (!resumen) return '';
  const partes = resumen.split(' - ');
  for (let i = partes.length - 1; i >= 0; i--) {
    const p = partes[i].trim();
    if (p && !p.match(/^[IVX]+\.\s/) && p.length > 3) return p;
  }
  return '';
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
  // Últimas 9 convocatorias para el feed
  const convs = await supaFetch(
    'convocatorias?select=*&order=created_at.desc&limit=9'
  );
  if (!convs.length) return;

  /* 1 · Hero badge — fecha de última actualización */
  const badge = document.querySelector('.hero-badge');
  if (badge) {
    const d = parseFecha(convs[0].created_at);
    const fecha = d ? `${d.getDate()} ${MESES_LARGO[d.getMonth()]}` : 'hoy';
    badge.innerHTML = `<span class="dot"></span>Actualizado · ${fecha}`;
  }

  /* 2 · Hero trust — total de convocatorias */
  const trustTotal = document.querySelector('.hero-trust span:last-child strong');
  if (trustTotal) {
    const total = await supaFetch('convocatorias?select=id');
    trustTotal.closest('span').innerHTML = `<strong>${total.length}+</strong> convocatorias publicadas`;
  }

  /* 3 · Artículo destacado */
  const featured = convs[0];
  const featuredEl = document.querySelector('.feature-lead');
  if (featuredEl) {
    const eyebrow = featuredEl.querySelector('.eyebrow');
    const h2      = featuredEl.querySelector('h2');
    const p       = featuredEl.querySelector('p');
    const src     = featuredEl.querySelector('.src');
    const link    = featuredEl.querySelector('.conv-readmore');

    const orgFeatured  = extraerOrganismo(featured.titulo);
    const descFeatured = featured.resumen_claude || extraerTipo(featured.resumen) || '';
    if (eyebrow) eyebrow.textContent = `Destacada · ${featured.categoria}`;
    if (h2)      h2.textContent = orgFeatured;
    if (p)       p.textContent  = descFeatured;
    if (src)     src.textContent = `BOE · ${fmtLargo(featured.fecha)}`;
    if (link)  { link.href = featured.enlace; link.target = '_blank'; link.rel = 'noopener'; link.textContent = 'Ver en BOE →'; }
  }

  /* 4 · Grid de tarjetas (siguientes 3) */
  const grid = document.querySelector('.conv-grid');
  if (grid) {
    grid.innerHTML = '';
    convs.slice(1, 4).forEach((c) => {
      const organismo   = extraerOrganismo(c.titulo);
      const descripcion = c.resumen_claude || extraerTipo(c.resumen) || '';
      const art = document.createElement('article');
      art.className = 'conv-card';
      art.innerHTML = `
        <div class="conv-card-strip"></div>
        <div class="conv-card-body">
          <span class="conv-tag">${c.categoria}</span>
          <h3><a href="${c.enlace}" target="_blank" rel="noopener">${organismo}</a></h3>
          <p>${descripcion}</p>
          <div class="conv-meta">
            <span class="src">BOE</span>
            <span>${fmtCorto(c.fecha)}</span>
          </div>
        </div>`;
      grid.appendChild(art);
    });
  }

  /* 5 · Ticker con títulos reales */
  const track = document.querySelector('.ticker-track');
  if (track && convs.length) {
    const items = convs.slice(0, 8).map(c =>
      `<span>${c.categoria} · ${truncar(c.titulo, 55)}</span>`
    );
    track.innerHTML = [...items, ...items].join(''); // duplicar para el loop
  }

  /* 6 · Conteos en las tarjetas de categoría */
  const todos = await supaFetch('convocatorias?select=categoria');
  const contadores = {};
  todos.forEach(r => {
    if (r.categoria) contadores[r.categoria] = (contadores[r.categoria] || 0) + 1;
  });

  document.querySelectorAll('.cat-card').forEach(card => {
    const nombre = card.querySelector('h3')?.textContent.trim();
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

  /* Actualizar contador en el hero de la categoría */
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
  const delays = ['reveal-d1', 'reveal-d2', 'reveal-d3'];

  convs.forEach((c, i) => {
    const d   = parseFecha(c.fecha) || parseFecha(c.created_at);
    const dia = d ? d.getDate() : '—';
    const mes = d
      ? (MESES_CORTO[d.getMonth()].charAt(0).toUpperCase() + MESES_CORTO[d.getMonth()].slice(1))
      : '—';

    const organismo   = extraerOrganismo(c.titulo);
    const descripcion = c.resumen_claude || extraerTipo(c.resumen) || '';
    const row = document.createElement('article');
    row.className = 'list-row';
    row.innerHTML = `
      <div class="list-date">
        <div class="d">${dia}</div>
        <div class="m">${mes}</div>
      </div>
      <a href="${c.enlace}" target="_blank" rel="noopener" class="list-main">
        <h3>${organismo}</h3>
        <div class="list-tags">
          ${descripcion ? `<span>${descripcion}</span>` : ''}
          <span>${c.categoria}</span>
        </div>
      </a>
      <span class="list-cta">Ver en BOE →</span>`;
    lista.appendChild(row);
  });

  /* Ocultar paginación estática (ya se muestran todas) */
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
