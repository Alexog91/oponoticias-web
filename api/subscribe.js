// Vercel Serverless Function — suscripción al newsletter via Brevo
// Variables de entorno requeridas en Vercel: BREVO_API_KEY, BREVO_LIST_ID

const https = require('https');

export default function handler(req, res) {
  // Solo aceptar POST
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { email } = req.body || {};

  // Validación básica
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: 'Email inválido' });
  }

  const apiKey  = process.env.BREVO_API_KEY;
  const listId  = parseInt(process.env.BREVO_LIST_ID, 10);

  if (!apiKey || !listId) {
    console.error('Faltan variables de entorno BREVO_API_KEY o BREVO_LIST_ID');
    return res.status(500).json({ error: 'Configuración incompleta' });
  }

  const body = JSON.stringify({
    email,
    listIds: [listId],
    updateEnabled: true,
  });

  const options = {
    hostname: 'api.brevo.com',
    path: '/v3/contacts',
    method: 'POST',
    headers: {
      'api-key': apiKey,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      'Content-Length': Buffer.byteLength(body),
    },
  };

  const request = https.request(options, (response) => {
    let data = '';
    response.on('data', (chunk) => { data += chunk; });
    response.on('end', () => {
      const status = response.statusCode;
      // 201 = creado, 204 = actualizado (ya existía)
      if (status === 201 || status === 204 || status === 200) {
        return res.status(200).json({ ok: true });
      }
      let parsed = {};
      try { parsed = JSON.parse(data); } catch (_) {}
      // Brevo devuelve code 'duplicate_parameter' si ya estaba suscrito
      if (parsed.code === 'duplicate_parameter') {
        return res.status(200).json({ ok: true, duplicate: true });
      }
      console.error('Brevo error:', status, data);
      return res.status(502).json({ error: 'Error al suscribir' });
    });
  });

  request.on('error', (err) => {
    console.error('Request error:', err);
    return res.status(502).json({ error: 'Error de conexión' });
  });

  request.write(body);
  request.end();
}
