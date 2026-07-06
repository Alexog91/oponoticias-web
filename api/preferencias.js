// Vercel Serverless Function — guarda la comunidad autónoma preferida de un
// suscriptor como atributo COMUNIDAD en Brevo. La usa la página /preferencias
// (enlazada desde el email diario y el de bienvenida) para segmentar el envío.
// Variables de entorno en Vercel: BREVO_API_KEY

const { brevoRequest, supabaseUpsert } = require('./_lib/http');

// Comunidades válidas (nombre tal cual se guarda en Supabase → permite filtrar
// después el envío diario por comunidad_autonoma). "" = recibir todas.
const COMUNIDADES = new Set([
  'Andalucía', 'Aragón', 'Asturias', 'Baleares', 'Canarias', 'Cantabria',
  'Castilla-La Mancha', 'Castilla y León', 'Cataluña', 'Comunidad Valenciana',
  'Extremadura', 'Galicia', 'La Rioja', 'Madrid', 'Murcia', 'Navarra',
  'País Vasco', 'Ceuta', 'Melilla', 'Nacional/Estatal',
]);

// Doble escritura (Fase 2 migración a SES): además de guardar COMUNIDAD en Brevo,
// actualiza la comunidad del suscriptor en Supabase (tabla `suscriptores`) para
// mantener la tabla sincronizada. No bloquea. Upsert por email (merge-duplicates);
// se omite estado y token_baja (se conservan; el default cubre las filas nuevas).
// Variables de entorno NUEVAS en Vercel: SUPABASE_URL, SUPABASE_API_KEY.
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

  const apiKey = process.env.BREVO_API_KEY;
  if (!apiKey) {
    console.error('Falta BREVO_API_KEY');
    return res.status(500).json({ error: 'Configuración incompleta' });
  }

  // 1) Asegura que el atributo COMUNIDAD existe (idempotente; ignora "ya existe").
  await brevoRequest('contacts/attributes/normal/COMUNIDAD', apiKey, { type: 'text' });

  // 2) Actualiza el contacto. updateEnabled crea el contacto si no existía
  //    (por si el enlace se abre antes de que Brevo lo tenga), pero lo normal
  //    es que ya esté suscrito.
  const upd = await brevoRequest('contacts', apiKey, {
    email,
    attributes: { COMUNIDAD: com },
    updateEnabled: true,
  });

  const ok = [200, 201, 204].includes(upd.status)
    || upd.data.code === 'duplicate_parameter';
  if (!ok) {
    console.error('Brevo preferencias error:', upd.status, JSON.stringify(upd.data));
    return res.status(502).json({ error: 'No se pudo guardar la preferencia' });
  }

  // Doble escritura en Supabase (no bloquea).
  const sb = await supabaseUpsertComunidad(email, com);
  if (!sb.skipped && !(sb.status >= 200 && sb.status < 300)) {
    console.error('Supabase upsert comunidad (no bloquea):', sb.status, JSON.stringify(sb.data).slice(0, 200));
  }

  return res.status(200).json({ ok: true });
}
