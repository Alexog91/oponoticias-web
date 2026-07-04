// Vercel Serverless Function — guarda la comunidad autónoma preferida de un
// suscriptor como atributo COMUNIDAD en Brevo. La usa la página /preferencias
// (enlazada desde el email diario y el de bienvenida) para segmentar el envío.
// Variables de entorno en Vercel: BREVO_API_KEY

const https = require('https');

// Comunidades válidas (nombre tal cual se guarda en Supabase → permite filtrar
// después el envío diario por comunidad_autonoma). "" = recibir todas.
const COMUNIDADES = new Set([
  'Andalucía', 'Aragón', 'Asturias', 'Baleares', 'Canarias', 'Cantabria',
  'Castilla-La Mancha', 'Castilla y León', 'Cataluña', 'Comunidad Valenciana',
  'Extremadura', 'Galicia', 'La Rioja', 'Madrid', 'Murcia', 'Navarra',
  'País Vasco', 'Ceuta', 'Melilla', 'Nacional/Estatal',
]);

// Petición genérica a Brevo. Resuelve siempre (sin lanzar) con {status, data}.
function brevo(method, path, apiKey, payload) {
  return new Promise((resolve) => {
    const body = payload ? JSON.stringify(payload) : '';
    const req = https.request(
      {
        hostname: 'api.brevo.com',
        path: `/v3/${path}`,
        method,
        headers: {
          'api-key': apiKey,
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'Content-Length': Buffer.byteLength(body),
        },
      },
      (response) => {
        let data = '';
        response.on('data', (chunk) => { data += chunk; });
        response.on('end', () => {
          let parsed = {};
          try { parsed = JSON.parse(data || '{}'); } catch (_) {}
          resolve({ status: response.statusCode, data: parsed });
        });
      }
    );
    req.on('error', (err) => resolve({ status: 0, data: { _err: String(err) } }));
    if (body) req.write(body);
    req.end();
  });
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
  await brevo('POST', 'contacts/attributes/normal/COMUNIDAD', apiKey, { type: 'text' });

  // 2) Actualiza el contacto. updateEnabled crea el contacto si no existía
  //    (por si el enlace se abre antes de que Brevo lo tenga), pero lo normal
  //    es que ya esté suscrito.
  const upd = await brevo('POST', 'contacts', apiKey, {
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

  return res.status(200).json({ ok: true });
}
