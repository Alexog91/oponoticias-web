// Vercel Serverless Function — baja del boletín (motor propio SES).
// El correo diario incluye un enlace y la cabecera List-Unsubscribe apuntando aquí.
// Marca al suscriptor como 'baja' en Supabase (tabla `suscriptores`), buscándolo por
// su `token_baja` (UUID opaco: NUNCA se pone el email en la URL, por privacidad).
//
// Acepta:
//   GET  /api/unsubscribe?t=<token>  → el usuario pulsa el enlace: devuelve una página
//                                       de confirmación HTML.
//   POST /api/unsubscribe?t=<token>  → "one-click" de Gmail/Yahoo (List-Unsubscribe-Post):
//                                       devuelve 200 sin cuerpo.
//
// Variables de entorno en Vercel (NUEVAS, hay que añadirlas):
//   SUPABASE_URL        — URL del proyecto Supabase
//   SUPABASE_API_KEY    — clave service_role LEGACY (JWT eyJ…, no sb_secret_)

const https = require('https');

// PATCH a Supabase (actualiza filas que cumplen el filtro). Resuelve siempre.
function supabasePatch(path, apiKey, baseUrl, body) {
  return new Promise((resolve) => {
    const data = JSON.stringify(body);
    const u = new URL(`${baseUrl}/rest/v1/${path}`);
    const req = https.request(
      {
        hostname: u.hostname,
        path: u.pathname + u.search,
        method: 'PATCH',
        headers: {
          apikey: apiKey,
          Authorization: `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
          Prefer: 'return=representation', // devuelve las filas afectadas
          'Content-Length': Buffer.byteLength(data),
        },
      },
      (response) => {
        let out = '';
        response.on('data', (c) => { out += c; });
        response.on('end', () => {
          let parsed = [];
          try { parsed = JSON.parse(out || '[]'); } catch (_) {}
          resolve({ status: response.statusCode, data: parsed });
        });
      }
    );
    req.on('error', () => resolve({ status: 0, data: [] }));
    req.write(data);
    req.end();
  });
}

function paginaConfirmacion(ok) {
  const titulo = ok ? 'Te has dado de baja' : 'No hemos podido procesar la baja';
  const msg = ok
    ? 'Ya no recibirás más el boletín diario de OpoNoticias. Si cambias de opinión, puedes volver a suscribirte cuando quieras en oponoticias.com.'
    : 'El enlace no es válido o ya no está activo. Si sigues recibiendo correos, escríbenos a info@oponoticias.com y lo resolvemos.';
  return `<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>${titulo} — OpoNoticias</title></head>
<body style="margin:0;background:#f8f6f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:520px;margin:60px auto;padding:0 20px;text-align:center;">
  <div style="font-family:'Georgia',serif;font-size:24px;font-weight:700;color:#5a5047;">OpoNoticias</div>
  <div style="background:#fff;border:1px solid #e7e0d5;border-radius:14px;padding:32px 28px;margin-top:20px;">
    <h1 style="font-family:'Georgia',serif;font-size:22px;color:#2b2622;margin:0 0 12px;">${titulo}</h1>
    <p style="color:#4a4540;font-size:15px;line-height:1.6;margin:0 0 20px;">${msg}</p>
    <a href="https://oponoticias.com" style="display:inline-block;background:#5a5047;color:#fff;text-decoration:none;padding:11px 22px;border-radius:8px;font-size:14px;font-weight:600;">Ir a oponoticias.com →</a>
  </div>
</div>
</body></html>`;
}

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // El token puede venir en la query (?t=) tanto en GET como en POST.
  const token = (req.query && typeof req.query.t === 'string') ? req.query.t.trim() : '';

  const apiKey  = process.env.SUPABASE_API_KEY;
  const baseUrl = process.env.SUPABASE_URL;
  if (!apiKey || !baseUrl) {
    console.error('Faltan SUPABASE_URL o SUPABASE_API_KEY');
    return res.status(500).json({ error: 'Configuración incompleta' });
  }

  // Validación estricta del token: solo se acepta un UUID. Evita cualquier riesgo
  // de PATCH sin filtro efectivo (que afectaría a más filas de la cuenta).
  const esUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(token);
  let ok = false;
  if (esUuid) {
    const filtro = `suscriptores?token_baja=eq.${encodeURIComponent(token)}`;
    const r = await supabasePatch(filtro, apiKey, baseUrl, {
      estado: 'baja',
      fecha_baja: new Date().toISOString(),
    });
    // 200 con al menos una fila devuelta = baja aplicada (o ya estaba de baja).
    ok = r.status >= 200 && r.status < 300 && Array.isArray(r.data) && r.data.length > 0;
    if (!ok) {
      console.error('Baja no aplicada:', r.status, JSON.stringify(r.data).slice(0, 200));
    }
  }

  // One-click (POST): responder 200 sin cuerpo, como esperan Gmail/Yahoo.
  if (req.method === 'POST') {
    return res.status(ok ? 200 : 400).end();
  }
  // GET: página de confirmación para el usuario.
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  return res.status(200).send(paginaConfirmacion(ok));
}
