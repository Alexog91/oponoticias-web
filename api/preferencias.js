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

// Actualiza la comunidad del suscriptor en Supabase. Upsert por email
// (merge-duplicates); se omiten estado y token_baja (se conservan; el default
// cubre las filas nuevas, p. ej. si el enlace se abre antes del alta).
function supabaseUpsertComunidad(email, comunidad) {
  return supabaseUpsert('suscriptores', [{ email, comunidad }]);
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { email, comunidad } = req.body || {};

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: 'Email inválido' });
  }
  // "" (cadena vacía) es válido: significa "recibir todas".
  const com = (comunidad || '').trim();
  if (com && !COMUNIDADES.has(com)) {
    return res.status(400).json({ error: 'Comunidad no válida' });
  }

  // Guarda la comunidad en Supabase (fuente de verdad). Upsert por email:
  // actualiza si ya existe, o crea la fila si el enlace se abre antes del alta.
  const sb = await supabaseUpsertComunidad(email, com);
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
