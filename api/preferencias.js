// Vercel Serverless Function — guarda la comunidad autónoma preferida de un
// suscriptor en la tabla `suscriptores` de Supabase (fuente de verdad). La usa la
// página /preferencias (enlazada desde el email diario y el de bienvenida) para
// segmentar el envío. Variables de entorno en Vercel: SUPABASE_URL, SUPABASE_API_KEY.

const { supabaseUpsert } = require('./_lib/http');

// Comunidades válidas (nombre tal cual se guarda en Supabase → permite filtrar
// después el envío diario por comunidad_autonoma). "" = recibir todas.
const COMUNIDADES = new Set([
  'Andalucía', 'Aragón', 'Asturias', 'Baleares', 'Canarias', 'Cantabria',
  'Castilla-La Mancha', 'Castilla y León', 'Cataluña', 'Comunidad Valenciana',
  'Extremadura', 'Galicia', 'La Rioja', 'Madrid', 'Murcia', 'Navarra',
  'País Vasco', 'Ceuta', 'Melilla', 'Nacional/Estatal',
]);

// Categorías válidas (nombre tal cual se guarda en convocatorias.categoria).
// "" = todas las categorías.
const CATEGORIAS = new Set([
  'Educación', 'Sanidad', 'Justicia', 'Seguridad',
  'Administración', 'Hacienda', 'Correos', 'Técnica',
]);

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const body = req.body || {};
  const { email, comunidad, categoria } = body;

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: 'Email inválido' });
  }
  // "" (cadena vacía) es válido: significa "recibir todas".
  const com = (comunidad || '').trim();
  if (com && !COMUNIDADES.has(com)) {
    return res.status(400).json({ error: 'Comunidad no válida' });
  }

  // La comunidad se escribe siempre (permite volver a "todas" con ""). La
  // categoría solo si viene en el body: así una página antigua que no la manda no
  // la pisa; y "" (o un valor desconocido) la limpia → todas las categorías.
  const fila = { email, comunidad: com };
  if ('categoria' in body) {
    const c = typeof categoria === 'string' ? categoria.trim() : '';
    fila.categoria = CATEGORIAS.has(c) ? c : '';
  }

  // Upsert por email: actualiza si ya existe, o crea la fila si el enlace se abre
  // antes del alta (el default de la BD cubre estado y token_baja).
  const sb = await supabaseUpsert('suscriptores', [fila]);
  if (sb.skipped) {
    console.error('Faltan SUPABASE_URL / SUPABASE_API_KEY');
    return res.status(500).json({ error: 'Configuración incompleta' });
  }
  if (!(sb.status >= 200 && sb.status < 300)) {
    console.error('Supabase upsert comunidad:', sb.status, JSON.stringify(sb.data).slice(0, 200));
    return res.status(502).json({ error: 'No se pudo guardar la preferencia' });
  }

  return res.status(200).json({ ok: true });
}
