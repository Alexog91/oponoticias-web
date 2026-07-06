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

/** Escapa texto antes de insertarlo vía innerHTML (los datos vienen de
 *  Supabase — título, resumen, etc. — y aunque no hay ruta de escritura
 *  anónima, es buena higiene no confiar en el contenido). */
function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function tiempoRelativo(str) {
  const d = parseFecha(str);
  if (!d) return '';
  const seg = Math.floor((Date.now() - d.getTime()) / 1000);
  if (seg < 60)       return 'ahora';
  const min = Math.floor(seg / 60);
  if (min < 60)       return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24)         return `hace ${h} h`;
  const dias = Math.floor(h / 24);
  if (dias === 1)     return 'ayer';
  if (dias < 7)       return `hace ${dias} días`;
  return fmtCorto(str);
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

// Si el puesto CONTIENE alguno de estos fragmentos → no sirve para destacar
// (no se excluyen "PERSONAL FUNCIONARIO/LABORAL": son convocatorias reales)
const PUESTO_SUBSTRINGS_MALOS = [
  'ESPECIFICAD', 'NO DISPONIBLE', 'NO DETERMINAD', 'NO INDICAD',
  'SIN ESPECIF', 'PUESTO DE TRABAJO', 'PUESTO NO', 'PLAZA NO',
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

/** ¿Convocatoria apta para destacar / ticker? (filtro estricto: puesto específico) */
function convocatoriaValida(c) {
  const r = (c.resumen_claude || '').toUpperCase();
  if (RESUMEN_NEGATIVOS.some(n => r.includes(n))) return false;
  const parsed = parsearResumen(c.resumen_claude);
  return parsed && puestoValido(parsed.puesto);
}

/** ¿Es una convocatoria REAL? (filtro laxo: solo descarta modificaciones,
 *  correcciones, bolsas y listas de espera; acepta puestos genéricos).
 *  Se usa en la sección "El BOE de hoy" para mostrar todo lo publicado. */
function convocatoriaReal(c) {
  const r = (c.resumen_claude || '').toUpperCase();
  if (!r) return false;
  return !RESUMEN_NEGATIVOS.some(n => r.includes(n));
}

/** Normaliza para comparar (mayúsculas, sin acentos). */
function _norm(s) {
  return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
}

// Cuerpos con gran masa de opositores potenciales (oposiciones muy demandadas):
// muchísima gente interesada aunque convoquen pocas plazas a la vez.
const CUERPOS_MASIVOS = [
  'CORREOS',
  'AUXILIAR ADMINISTRATIVO', 'ADMINISTRATIVO DEL ESTADO', 'ADMINISTRACION GENERAL DEL ESTADO',
  'CUERPO GENERAL ADMINISTRATIVO', 'CUERPO GENERAL AUXILIAR', 'GESTION DE LA ADMINISTRACION',
  'TRAMITACION PROCESAL', 'AUXILIO JUDICIAL', 'GESTION PROCESAL',
  'GUARDIA CIVIL', 'POLICIA NACIONAL', 'POLICIA LOCAL', 'BOMBERO',
  'AGENCIA TRIBUTARIA', 'AGENTE DE HACIENDA', 'SEGURIDAD SOCIAL',
  'INSTITUTO NACIONAL DE LA SEGURIDAD',
  'MAESTRO', 'MAESTRA', 'PROFESOR DE ENSENANZA SECUNDARIA',
  'CUERPO DE MAESTROS', 'CUERPO DE PROFESORES',
  'ENFERMER', 'AUXILIAR DE ENFERMERIA', 'TECNICO EN CUIDADOS', 'TCAE', 'CELADOR',
];

// Interés amplio pero más moderado.
const CUERPOS_MEDIOS = [
  'ADMINISTRATIV', 'AUXILIAR', 'TECNICO', 'MEDICO', 'TRABAJADOR SOCIAL',
  'SUBALTERNO', 'ORDENANZA', 'PEON', 'CONDUCTOR', 'LIMPIEZA', 'JUSTICIA',
  'ESTATUTARIO', 'SANITARIO', 'EDUCADOR',
];

// Puestos muy especializados de interés limitado: plazas docentes universitarias,
// investigación, cátedras… (poca gente potencialmente interesada).
const CUERPOS_NICHO = [
  'CUERPOS DOCENTES UNIVERSITARIOS', 'CUERPO DOCENTE UNIVERSITARIO',
  'PROFESOR TITULAR', 'PROFESORA TITULAR', 'CATEDRATICO', 'CATEDRATICA',
  'AYUDANTE DOCTOR', 'CONTRATADO DOCTOR', 'PROFESOR CONTRATADO',
  'PROFESOR DE UNIVERSIDAD', 'TITULAR DE UNIVERSIDAD', 'PROFESOR ASOCIADO',
  'INVESTIGADOR', 'PROFESOR VISITANTE',
];

/**
 * Bonus por demanda potencial del cuerpo: cuántas personas podrían estar
 * interesadas según el tipo de plaza (no solo el nº de plazas convocadas).
 * Lo nicho (docencia universitaria, investigación) penaliza.
 */
function relevanciaCuerpo(c) {
  const parsed = parsearResumen(c.resumen_claude);
  const txt = _norm(`${parsed ? parsed.puesto : ''} ${c.categoria || ''} ${c.titulo || ''}`);
  if (CUERPOS_NICHO.some(k => txt.includes(k)))   return -30;
  if (CUERPOS_MASIVOS.some(k => txt.includes(k))) return 50;
  if (CUERPOS_MEDIOS.some(k => txt.includes(k)))  return 20;
  return 0;
}

/**
 * Puntúa una convocatoria por ATRACTIVO para el gran público: combina el
 * número de plazas convocadas con la demanda potencial del cuerpo (cuántos
 * posibles interesados hay). La frescura desempata para que la portada rote.
 */
/** Días transcurridos desde que se registró la convocatoria. */
function diasDesde(c) {
  const d = parseFecha(c.created_at || c.fecha);
  if (!d) return 999;
  return Math.max(0, Math.floor((Date.now() - d.getTime()) / 86400000));
}

function puntuarConvocatoria(c) {
  if (!convocatoriaValida(c)) return -1000;
  const parsed = parsearResumen(c.resumen_claude);

  let pts = 10;                            // base por ser válida
  pts += Math.min(numPlazas(parsed.plazas), 80);  // más plazas = más relevante
  pts += relevanciaCuerpo(c);              // demanda potencial del cuerpo
  if (parsed.puesto.length > 12) pts += 4; // puesto descriptivo
  if (parsed.puesto.length > 22) pts += 3;
  if (c.categoria && c.categoria !== 'Administración') pts += 3; // variedad
  // Frescura: las recientes pesan más para que la destacada se renueve a diario.
  // Hoy +30, y baja 6 puntos por día hasta agotarse a los 5 días.
  pts += Math.max(0, 30 - diasDesde(c) * 6);
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
  // Para el grid: SOLO la última edición del BOE (mismo día) — nunca mezclamos
  // días. Dentro de ese día, las más ATRACTIVAS (nº de plazas + demanda
  // potencial del cuerpo). Excluimos la destacada, que ya se muestra arriba.
  const validas = convs.filter(convocatoriaValida);
  const tiempos = validas.map(c => parseFecha(c.fecha)).filter(Boolean).map(d => d.getTime());
  const maxDate = tiempos.length ? new Date(Math.max(...tiempos)) : null;
  const mismoDia = (c) => {
    const d = parseFecha(c.fecha);
    return maxDate && d
        && d.getFullYear() === maxDate.getFullYear()
        && d.getMonth()    === maxDate.getMonth()
        && d.getDate()     === maxDate.getDate();
  };
  const restantes  = validas
    .filter(c => c.id !== featured.id && mismoDia(c))
    .sort((a, b) => puntuarConvocatoria(b) - puntuarConvocatoria(a));

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
        <span>Plazas: <b>${escapeHtml(parsedHero.plazas)}</b></span>
        <span>Organismo: <b>${escapeHtml(truncar(organismoH, 30))}</b></span>`;
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
        <span style="display:block;font-size:1.15rem;font-weight:700;color:var(--primary);margin-bottom:12px;">${escapeHtml(parsed.puesto)}</span>
        <span style="display:flex;flex-wrap:wrap;gap:18px;font-size:0.92rem;color:var(--gray);">
          <span>🔢 ${escapeHtml(parsed.plazas)}</span>
          ${!lugarRedundante ? `<span>📍 ${escapeHtml(truncar(parsed.lugar, 50))}</span>` : ''}
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
          <span class="conv-tag">${escapeHtml(c.categoria)}</span>
          <h3><a href="${escapeHtml(c.enlace)}" target="_blank" rel="noopener">${escapeHtml(organismo)}</a></h3>
          <p style="font-weight:600;color:var(--primary);text-transform:uppercase;font-size:0.9rem;letter-spacing:0.02em;">${escapeHtml(desc)}</p>
          <div class="conv-meta">
            <span class="src">${escapeHtml(parsed ? parsed.plazas : 'BOE')}</span>
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
        return `<span>${escapeHtml(c.categoria)} — ${escapeHtml(p.plazas)} · ${escapeHtml(p.puesto)}</span>`;
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

/* ── PÁGINA "EL BOE DE HOY" (boe-hoy.html) ──────────────────────────────────
   Lista TODAS las convocatorias reales de la última edición del BOE.        */
async function cargarBoeHoy() {
  const boeGrid = document.getElementById('boeHoyGrid');
  if (!boeGrid) return;

  const convs  = await supaFetch('convocatorias?select=*&order=created_at.desc&limit=150');
  const reales = convs.filter(convocatoriaReal);

  if (!reales.length) {
    const empty = document.getElementById('boeHoyEmpty');
    if (empty) empty.hidden = false;
    return;
  }

  // Fecha de la edición más reciente del BOE
  const tiempos = reales
    .map(c => parseFecha(c.fecha))
    .filter(Boolean)
    .map(d => d.getTime());
  const maxDate = new Date(Math.max(...tiempos));
  const mismaFecha = (c) => {
    const d = parseFecha(c.fecha);
    return d && d.getFullYear() === maxDate.getFullYear()
        && d.getMonth() === maxDate.getMonth()
        && d.getDate() === maxDate.getDate();
  };
  // Ordenar por nº de plazas (desc); las de puesto concreto pesan algo más
  const plazasDe = (c) => {
    const p = parsearResumen(c.resumen_claude);
    if (!p) return 0;
    let n = numPlazas(p.plazas);
    if (puestoValido(p.puesto)) n += 0.5;
    return n;
  };
  const deHoy = reales
    .filter(mismaFecha)
    .sort((a, b) => plazasDe(b) - plazasDe(a));

  const fechaEl = document.getElementById('boeHoyFecha');
  if (fechaEl) {
    const n = deHoy.length;
    fechaEl.textContent =
      `${n} convocatoria${n === 1 ? '' : 's'} de oposición publicada${n === 1 ? '' : 's'} el `
      + `${maxDate.getDate()} de ${MESES_LARGO[maxDate.getMonth()]} de ${maxDate.getFullYear()}.`;
  }

  boeGrid.innerHTML = '';
  deHoy.forEach(c => {
    const organismo = extraerOrganismo(c.titulo);
    const parsed    = parsearResumen(c.resumen_claude);
    const desc      = parsed ? parsed.puesto : extraerTipo(c.resumen);
    const art = document.createElement('article');
    art.className = 'conv-card';
    art.innerHTML = `
      <div class="conv-card-strip"></div>
      <div class="conv-card-body">
        <span class="conv-tag">${escapeHtml(c.categoria)}</span>
        <h3><a href="${escapeHtml(c.enlace)}" target="_blank" rel="noopener">${escapeHtml(organismo)}</a></h3>
        <p style="font-weight:600;color:var(--primary);text-transform:uppercase;font-size:0.86rem;letter-spacing:0.02em;">${escapeHtml(desc)}</p>
        <div class="conv-meta">
          <span class="src">${escapeHtml(parsed ? parsed.plazas : 'BOE')}</span>
          <span>${fmtCorto(c.fecha)}</span>
        </div>
      </div>`;
    boeGrid.appendChild(art);
  });
}

/* ── COLUMNA DE NOTICIAS (RSS · index.html) ─────────────────────────────── */

async function cargarNoticias() {
  const col = document.querySelector('.col-news');
  if (!col) return;

  let noticias;
  try {
    noticias = await supaFetch('noticias_rss?select=*&order=fecha_pub.desc&limit=6');
  } catch (err) {
    // La tabla aún no existe o no es accesible → se mantiene el contenido de ejemplo
    console.warn('[OpoNoticias] noticias_rss no disponible todavía:', err.message);
    return;
  }

  if (!noticias || !noticias.length) return;

  // Quitar los items de ejemplo, conservando cabecera y enlace "Más noticias"
  col.querySelectorAll('.news-item').forEach(n => n.remove());
  const more = col.querySelector('.col-more');

  noticias.forEach(n => {
    const art = document.createElement('article');
    art.className = 'news-item';
    art.innerHTML = `
      <a href="${escapeHtml(n.enlace)}" class="news-link" target="_blank" rel="noopener">
        <h4>${escapeHtml(n.titulo)}</h4>
        <div class="news-meta">
          <span class="news-src">${escapeHtml(n.fuente || '20minutos')}</span>
          <span>${tiempoRelativo(n.fecha_pub)}</span>
        </div>
      </a>`;
    if (more) col.insertBefore(art, more);
    else col.appendChild(art);
  });
}

/* ── BLOG: artículos reales en la columna derecha de la portada ─────────── */
const CAT_NOMBRE = {
  educacion:'Educación', sanidad:'Sanidad', administracion:'Administración',
  justicia:'Justicia', seguridad:'Seguridad', hacienda:'Hacienda',
  correos:'Correos', tecnica:'Técnica'
};

async function cargarBlog() {
  const col = document.querySelector('.col-aside');
  if (!col) return;

  let articulos;
  try {
    articulos = await supaFetch('articulos_blog?select=titulo,slug,categoria,resumen&publicado=eq.true&order=fecha_pub.desc&limit=4');
  } catch (err) {
    // La tabla aún no existe → se mantienen los ejemplos
    console.warn('[OpoNoticias] articulos_blog no disponible todavía:', err.message);
    return;
  }

  if (!articulos || !articulos.length) return;

  // Quitar los artículos de ejemplo del bloque blog
  col.querySelectorAll('.blog-item').forEach(n => n.remove());
  const more = col.querySelector('.col-more');

  articulos.forEach(a => {
    const art = document.createElement('article');
    art.className = 'blog-item';
    const cat = CAT_NOMBRE[a.categoria] || 'Blog';
    art.innerHTML = `
      <a href="/blog/${encodeURIComponent(a.slug)}" class="blog-link">
        <span class="blog-tag">${escapeHtml(cat)}</span>
        <h4>${escapeHtml(a.titulo)}</h4>
        <span class="blog-read">Leer artículo →</span>
      </a>`;
    if (more) col.insertBefore(art, more);
    else col.appendChild(art);
  });

  // El enlace "Ver todo el blog" apunta al índice
  if (more) more.setAttribute('href', '/blog');
}

/* ── COMUNIDAD AUTÓNOMA: inferencia desde el texto ──────────────────────── */
/* Si en el futuro existe la columna `comunidad_autonoma`, se usa directamente.
   Mientras tanto se infiere de la provincia (entre paréntesis o en el texto),
   del nombre de la comunidad o de la capital. Lo que no se reconoce → null. */

const PROVINCIA_CA = {
  // Andalucía
  'ALMERÍA':'Andalucía','ALMERIA':'Andalucía','CÁDIZ':'Andalucía','CADIZ':'Andalucía',
  'CÓRDOBA':'Andalucía','CORDOBA':'Andalucía','GRANADA':'Andalucía','HUELVA':'Andalucía',
  'JAÉN':'Andalucía','JAEN':'Andalucía','MÁLAGA':'Andalucía','MALAGA':'Andalucía','SEVILLA':'Andalucía',
  // Aragón
  'HUESCA':'Aragón','TERUEL':'Aragón','ZARAGOZA':'Aragón',
  // Asturias / Cantabria / La Rioja / Murcia / Navarra (uniprovinciales)
  'ASTURIAS':'Asturias','CANTABRIA':'Cantabria','LA RIOJA':'La Rioja','RIOJA':'La Rioja',
  'MURCIA':'Murcia','NAVARRA':'Navarra',
  // Baleares / Canarias
  'BALEARES':'Baleares','ILLES BALEARS':'Baleares','MALLORCA':'Baleares','MENORCA':'Baleares','IBIZA':'Baleares',
  'LAS PALMAS':'Canarias','SANTA CRUZ DE TENERIFE':'Canarias','TENERIFE':'Canarias',
  // Castilla-La Mancha
  'ALBACETE':'Castilla-La Mancha','CIUDAD REAL':'Castilla-La Mancha','CUENCA':'Castilla-La Mancha',
  'GUADALAJARA':'Castilla-La Mancha','TOLEDO':'Castilla-La Mancha',
  // Castilla y León
  'ÁVILA':'Castilla y León','AVILA':'Castilla y León','BURGOS':'Castilla y León','LEÓN':'Castilla y León','LEON':'Castilla y León',
  'PALENCIA':'Castilla y León','SALAMANCA':'Castilla y León','SEGOVIA':'Castilla y León','SORIA':'Castilla y León',
  'VALLADOLID':'Castilla y León','ZAMORA':'Castilla y León',
  // Cataluña
  'BARCELONA':'Cataluña','GIRONA':'Cataluña','GERONA':'Cataluña','LLEIDA':'Cataluña','LÉRIDA':'Cataluña','LERIDA':'Cataluña','TARRAGONA':'Cataluña',
  // Comunidad Valenciana
  'ALICANTE':'Comunidad Valenciana','ALACANT':'Comunidad Valenciana','CASTELLÓN':'Comunidad Valenciana','CASTELLON':'Comunidad Valenciana',
  'CASTELLÓ':'Comunidad Valenciana','VALENCIA':'Comunidad Valenciana','VALÈNCIA':'Comunidad Valenciana',
  // Extremadura
  'BADAJOZ':'Extremadura','CÁCERES':'Extremadura','CACERES':'Extremadura',
  // Galicia
  'A CORUÑA':'Galicia','LA CORUÑA':'Galicia','CORUÑA':'Galicia','LUGO':'Galicia','OURENSE':'Galicia','ORENSE':'Galicia','PONTEVEDRA':'Galicia',
  // Madrid
  'MADRID':'Madrid',
  // País Vasco
  'ÁLAVA':'País Vasco','ALAVA':'País Vasco','ARABA':'País Vasco','GUIPÚZCOA':'País Vasco','GUIPUZCOA':'País Vasco',
  'GIPUZKOA':'País Vasco','VIZCAYA':'País Vasco','BIZKAIA':'País Vasco',
  // Ciudades autónomas
  'CEUTA':'Ceuta','MELILLA':'Melilla',
};

// Capitales/ciudades notables que no coinciden con el nombre de su provincia
const CIUDAD_CA = {
  'GIJÓN':'Asturias','GIJON':'Asturias','OVIEDO':'Asturias','VIGO':'Galicia','SANTIAGO DE COMPOSTELA':'Galicia',
  'BILBAO':'País Vasco','SAN SEBASTIÁN':'País Vasco','VITORIA':'País Vasco','PALMA':'Baleares',
  'JEREZ':'Andalucía','MARBELLA':'Andalucía','VIGO':'Galicia',
};

// Nombres de comunidad / organismos autonómicos que aparecen literalmente
const CCAA_DIRECTAS = [
  ['JUNTA DE ANDALUCÍA','Andalucía'],['JUNTA DE ANDALUCIA','Andalucía'],
  ['GOBIERNO DE ARAGÓN','Aragón'],['PRINCIPADO DE ASTURIAS','Asturias'],
  ['GOVERN DE LES ILLES BALEARS','Baleares'],['GOBIERNO DE CANARIAS','Canarias'],
  ['GOBIERNO DE CANTABRIA','Cantabria'],['CASTILLA-LA MANCHA','Castilla-La Mancha'],
  ['CASTILLA LA MANCHA','Castilla-La Mancha'],['JUNTA DE CASTILLA Y LEÓN','Castilla y León'],
  ['CASTILLA Y LEÓN','Castilla y León'],['GENERALITAT DE CATAL','Cataluña'],['CATALUÑA','Cataluña'],['CATALUNYA','Cataluña'],
  ['GENERALITAT VALENCIANA','Comunidad Valenciana'],['COMUNITAT VALENCIANA','Comunidad Valenciana'],['COMUNIDAD VALENCIANA','Comunidad Valenciana'],
  ['JUNTA DE EXTREMADURA','Extremadura'],['XUNTA DE GALICIA','Galicia'],['GALICIA','Galicia'],
  ['GOBIERNO DE LA RIOJA','La Rioja'],['COMUNIDAD DE MADRID','Madrid'],['COMUNIDAD AUTÓNOMA DE MADRID','Madrid'],
  ['REGIÓN DE MURCIA','Murcia'],['GOBIERNO DE NAVARRA','Navarra'],['COMUNIDAD FORAL DE NAVARRA','Navarra'],
  ['GOBIERNO VASCO','País Vasco'],['PAÍS VASCO','País Vasco'],['EUSKADI','País Vasco'],
];

// Organismos de ámbito estatal → "Nacional/Estatal"
const ORGANISMOS_NACIONALES = [
  'MINISTERIO','INSTITUTO NACIONAL','ADMINISTRACIÓN GENERAL DEL ESTADO','INGESA',
  'AGENCIA ESTATAL','AGENCIA TRIBUTARIA','CONSEJO GENERAL','GUARDIA CIVIL',
  'POLICÍA NACIONAL','FUERZAS ARMADAS','SEGURIDAD SOCIAL','CORREOS','AENA','ADIF',
];

/** Devuelve un nombre de comunidad (o "Nacional/Estatal") o null si no se reconoce. */
function inferirCA(c) {
  if (c.comunidad_autonoma) return c.comunidad_autonoma;   // exacto, si existe la columna
  const blob = ((c.resumen_claude || '') + ' ' + (c.titulo || '')).toUpperCase();

  // 1 · Provincia entre paréntesis: "... (HUELVA)" → muy fiable
  const paren = blob.match(/\(([^)]+)\)/g);
  if (paren) {
    for (const p of paren) {
      const dentro = p.replace(/[()]/g, '').trim();
      if (PROVINCIA_CA[dentro]) return PROVINCIA_CA[dentro];
    }
  }
  // 2 · Nombre de comunidad / organismo autonómico literal
  for (const [clave, ca] of CCAA_DIRECTAS) {
    if (blob.includes(clave)) return ca;
  }
  // 3 · Provincia como palabra suelta
  for (const prov in PROVINCIA_CA) {
    const re = new RegExp('(^|[^A-ZÁÉÍÓÚÑ])' + prov.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '([^A-ZÁÉÍÓÚÑ]|$)');
    if (re.test(blob)) return PROVINCIA_CA[prov];
  }
  // 4 · Ciudad notable
  for (const ciudad in CIUDAD_CA) {
    if (blob.includes(ciudad)) return CIUDAD_CA[ciudad];
  }
  // 5 · Organismo estatal
  if (ORGANISMOS_NACIONALES.some(o => blob.includes(o))) return 'Nacional/Estatal';

  return null;
}

// Orden preferente para el desplegable
const ORDEN_CA = [
  'Andalucía','Aragón','Asturias','Baleares','Canarias','Cantabria',
  'Castilla-La Mancha','Castilla y León','Cataluña','Comunidad Valenciana',
  'Extremadura','Galicia','La Rioja','Madrid','Murcia','Navarra','País Vasco',
  'Ceuta','Melilla','Nacional/Estatal',
];

/* ── PÁGINA DE CATEGORÍA ────────────────────────────────────────────────── */

async function cargarCategoria(categoria) {
  const convs = await supaFetch(
    `convocatorias?select=*&categoria=eq.${encodeURIComponent(categoria)}&order=created_at.desc&limit=100`
  );

  // Excluir modificaciones de tribunal, correcciones de errores y bolsas
  const convsFiltradas = convs.filter(convocatoriaReal);

  const statB = document.querySelector('.cat-hero-stats div:first-child b');
  if (statB) statB.textContent = convsFiltradas.length;

  const lista = document.querySelector('.cat-list');
  if (!lista) return;

  if (!convsFiltradas.length) {
    lista.innerHTML = `
      <p style="color:var(--gray);padding:40px 0;text-align:center;">
        No hay convocatorias disponibles para esta categoría todavía.<br>
        <a href="https://t.me/OPONOTICIAS" target="_blank" rel="noopener">Activa las alertas en Telegram →</a>
      </p>`;
    return;
  }

  // Inferir comunidad de cada convocatoria
  convsFiltradas.forEach(c => { c._ca = inferirCA(c); });

  // Comunidades presentes (para poblar el desplegable y el contador)
  const caPresentes = ORDEN_CA.filter(ca => convsFiltradas.some(c => c._ca === ca));
  const statCom = document.querySelector('.cat-hero-stats div:nth-child(2) b');
  if (statCom) statCom.textContent = caPresentes.length;

  lista.innerHTML = '';

  convsFiltradas.forEach((c) => {
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
    row.dataset.ca = c._ca || 'Otras';
    row.innerHTML = `
      <div class="list-date">
        <div class="d">${dia}</div>
        <div class="m">${mes}</div>
      </div>
      <a href="${escapeHtml(c.enlace)}" target="_blank" rel="noopener" class="list-main">
        <h3>${escapeHtml(organismo)}</h3>
        ${puesto ? `<p style="margin:3px 0 6px;font-weight:600;font-size:0.92rem;color:var(--primary);text-transform:uppercase;letter-spacing:0.02em;">${escapeHtml(puesto)}</p>` : ''}
        <div class="list-tags">
          ${plazas ? `<span>${escapeHtml(plazas)}</span>` : ''}
          ${c._ca ? `<span>🗺️ ${escapeHtml(c._ca)}</span>` : (!lugarRedundante ? `<span>📍 ${escapeHtml(truncar(lugar, 35))}</span>` : '')}
        </div>
      </a>
      <span class="list-cta">Ver en BOE →</span>`;
    lista.appendChild(row);
  });

  // Ahora que las filas existen, montar el desplegable y conectar el filtrado
  montarFiltroCA(categoria, caPresentes);

  const pag = document.querySelector('.pagination');
  if (pag) pag.style.display = 'none';
}

/* Inserta el desplegable de Comunidad Autónoma en la toolbar y lo conecta. */
function montarFiltroCA(categoria, caPresentes) {
  const toolbar = document.querySelector('.cat-toolbar');
  if (!toolbar) return;

  // Sustituir las pills estáticas por una etiqueta + desplegable funcional
  const pills = toolbar.querySelector('.filter-pills');
  const wrap = document.createElement('div');
  wrap.className = 'filter-pills ca-filter';

  const total = document.querySelectorAll('.cat-list .list-row').length;
  let opciones = `<option value="__all__">Todas las comunidades</option>`;
  caPresentes.forEach(ca => { opciones += `<option value="${ca}">${ca}</option>`; });

  wrap.innerHTML = `
    <label class="ca-label" for="caSelect">Comunidad autónoma</label>
    <select class="sort-select ca-select" id="caSelect" aria-label="Filtrar por comunidad autónoma">
      ${opciones}
    </select>
    <span class="ca-count" id="caCount"></span>`;

  if (pills) pills.replaceWith(wrap);
  else toolbar.insertBefore(wrap, toolbar.firstChild);

  const select = wrap.querySelector('#caSelect');
  const count  = wrap.querySelector('#caCount');

  function aplicar() {
    const val = select.value;
    let visibles = 0;
    document.querySelectorAll('.cat-list .list-row').forEach(row => {
      const ok = (val === '__all__') || (row.dataset.ca === val);
      row.style.display = ok ? '' : 'none';
      if (ok) visibles++;
    });
    count.textContent = (val === '__all__')
      ? `${visibles} convocatorias`
      : `${visibles} en ${val}`;

    // Mensaje si una comunidad concreta se queda sin resultados visibles
    let vacio = document.querySelector('.cat-list .ca-empty');
    if (visibles === 0) {
      if (!vacio) {
        vacio = document.createElement('p');
        vacio.className = 'ca-empty';
        vacio.style.cssText = 'color:var(--gray);padding:30px 0;text-align:center;';
        document.querySelector('.cat-list').appendChild(vacio);
      }
      vacio.textContent = `No hay convocatorias de esta categoría en ${val} por ahora.`;
      vacio.style.display = '';
    } else if (vacio) {
      vacio.style.display = 'none';
    }
  }

  select.addEventListener('change', aplicar);
  aplicar();
}

/* ── ARRANQUE ───────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const catMeta = document.querySelector('meta[name="opo-categoria"]');
    const pageMeta = document.querySelector('meta[name="opo-page"]');
    if (catMeta) {
      await cargarCategoria(catMeta.getAttribute('content'));
    } else if (pageMeta && pageMeta.getAttribute('content') === 'boe-hoy') {
      await cargarBoeHoy();
    } else if (document.querySelector('.conv-grid')) {
      await cargarPortada();
      await cargarNoticias();
      await cargarBlog();
    }
  } catch (err) {
    console.error('[OpoNoticias loader]', err);
  }
});
