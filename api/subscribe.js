// Vercel Serverless Function — suscripción al newsletter via Brevo
// + envío automático del lead magnet (Calendario y Guía del Opositor 2026).
// Variables de entorno en Vercel: BREVO_API_KEY, BREVO_LIST_ID,
//   BREVO_SENDER_EMAIL (opcional), BREVO_SENDER_NAME (opcional)

const https = require('https');

const BASE = 'https://oponoticias.com/descargas';

// Catálogo de materiales descargables. La clave es el `slug` que envía el
// front-end; cada uno define el nombre y el archivo a entregar por email.
// Si no llega `material` (formulario de la home / pop-up), se usa el calendario.
const MATERIALES = {
  'calendario-opositor-2026': {
    nombre: 'Calendario y Guía del Opositor 2026',
    desc: 'cómo funciona el calendario de las oposiciones, los grandes procesos del año, qué hacer cuando encuentras tu oposición y cómo no perderte ninguna convocatoria',
    url: `${BASE}/calendario-opositor-2026.pdf`,
  },
  'guia-como-leer-el-boe': {
    nombre: 'Guía: Cómo leer el BOE',
    desc: 'cómo interpretar el BOE para no perderte ninguna convocatoria, con la fuente oficial paso a paso',
    url: `${BASE}/guia-como-leer-el-boe.pdf`,
  },
  'guia-el-dia-del-examen': {
    nombre: 'Guía: El día del examen',
    desc: 'tu checklist imprimible para llegar sin sustos al examen y dar lo mejor de ti',
    url: `${BASE}/guia-el-dia-del-examen.pdf`,
  },
  'guia-instancia-y-tasas': {
    nombre: 'Guía: La instancia y las tasas',
    desc: 'cómo presentar tu solicitud y pagar las tasas sin quedarte fuera (modelo 790 e inscripción electrónica)',
    url: `${BASE}/guia-instancia-y-tasas.pdf`,
  },
  'kit-del-opositor': {
    nombre: 'Kit del Opositor (Excel)',
    desc: 'tu agenda para preparar la oposición: retroplanning, repaso espaciado (1, 7 y 30 días) y tracker de tests que detecta tus temas flojos',
    url: `${BASE}/kit-del-opositor.xlsx`,
  },
  'kit-del-opositor-guia': {
    nombre: 'Kit del Opositor (guía de uso, PDF)',
    desc: 'cómo sacarle el máximo partido al Kit del Opositor paso a paso',
    url: `${BASE}/kit-del-opositor.pdf`,
  },
};
const MATERIAL_DEFECTO = 'calendario-opositor-2026';

// Llama a la API de Brevo y resuelve siempre (sin lanzar) con {status, data}.
function brevoRequest(path, apiKey, payload) {
  return new Promise((resolve) => {
    const body = JSON.stringify(payload);
    const req = https.request(
      {
        hostname: 'api.brevo.com',
        path: `/v3/${path}`,
        method: 'POST',
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
    req.write(body);
    req.end();
  });
}

function emailBienvenidaHtml(material) {
  return `<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f8f6f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f6f2;"><tr><td align="center" style="padding:24px 16px;">

  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:linear-gradient(135deg,#5a5047,#c4a574);border-radius:14px 14px 0 0;">
  <tr><td style="padding:32px;">
    <div style="color:#fff;font-size:22px;font-family:'Georgia',serif;font-weight:700;">OpoNoticias</div>
    <div style="color:rgba(255,255,255,0.85);font-size:13px;margin-top:4px;">Tu descarga gratuita</div>
  </td></tr>
  </table>

  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-left:1px solid #e7e0d5;border-right:1px solid #e7e0d5;">
  <tr><td style="padding:28px 32px;">
    <h1 style="margin:0 0 12px;font-family:'Georgia',serif;font-size:22px;color:#2b2622;">¡Aquí tienes tu material! 📥</h1>
    <p style="margin:0 0 16px;color:#4a4540;font-size:15px;line-height:1.6;">
      Gracias por suscribirte. Aquí tienes tu <strong>${material.nombre}</strong>:
      ${material.desc}.
    </p>
    <p style="text-align:center;margin:24px 0;">
      <a href="${material.url}" target="_blank" rel="noopener"
         style="display:inline-block;background:#5a5047;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-size:15px;font-weight:600;">
        📥 Descargar ${material.nombre}
      </a>
    </p>
    <p style="margin:0 0 8px;color:#4a4540;font-size:15px;line-height:1.6;">
      A partir de mañana recibirás cada día laborable un resumen de las nuevas convocatorias del BOE,
      en lenguaje claro y organizadas por categoría y comunidad autónoma.
    </p>

    <!-- Bloque de bienvenida: cómo usarlo + síguenos (todo en este único email) -->
    <div style="margin:22px 0 6px;padding:20px 22px;background:#f8f6f2;border-radius:10px;">
      <p style="margin:0 0 12px;color:#2b2622;font-size:16px;font-weight:700;font-family:'Georgia',serif;">Para empezar</p>
      <p style="margin:0 0 10px;color:#4a4540;font-size:14px;line-height:1.6;">
        🔎 <strong>Busca las de tu comunidad:</strong> en la web puedes filtrar todas las convocatorias
        por comunidad autónoma y categoría, con enlace directo al BOE.
        <a href="https://oponoticias.com/boe-hoy" style="color:#c4a574;text-decoration:none;font-weight:600;">Verlas ahora&nbsp;→</a>
      </p>
      <p style="margin:0;color:#4a4540;font-size:14px;line-height:1.6;">
        📲 <strong>Síguenos también</strong> para no perderte nada al instante:
        <a href="https://t.me/OPONOTICIAS" style="color:#c4a574;text-decoration:none;font-weight:600;">Telegram</a>
        &nbsp;·&nbsp;
        <a href="https://instagram.com/oponoticiason" style="color:#c4a574;text-decoration:none;font-weight:600;">Instagram</a>
      </p>
    </div>

    <p style="margin:16px 0 0;color:#8b8b7a;font-size:13px;line-height:1.6;">
      ¿No ves el botón? Copia este enlace en tu navegador:<br>
      <a href="${material.url}" style="color:#c4a574;">${material.url}</a>
    </p>
  </td></tr>
  </table>

  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#2b2622;border-radius:0 0 14px 14px;">
  <tr><td style="padding:20px 24px;text-align:center;color:rgba(255,255,255,0.5);font-size:12px;line-height:1.7;">
    <a href="https://oponoticias.com" style="color:#c4a574;text-decoration:none;">oponoticias.com</a>
    &nbsp;·&nbsp;
    <a href="https://t.me/OPONOTICIAS" style="color:#c4a574;text-decoration:none;">Telegram</a>
    &nbsp;·&nbsp;
    <a href="mailto:info@oponoticias.com" style="color:#c4a574;text-decoration:none;">info@oponoticias.com</a>
    <br>Recibiste este correo porque te suscribiste en oponoticias.com
  </td></tr>
  </table>

</td></tr></table>
</body></html>`;
}

export default async function handler(req, res) {
  // Solo aceptar POST
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { email, material } = req.body || {};

  // Validación básica
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: 'Email inválido' });
  }

  // Material a entregar (por slug). Si no llega o es desconocido → calendario.
  const mat = MATERIALES[material] || MATERIALES[MATERIAL_DEFECTO];

  const apiKey      = process.env.BREVO_API_KEY;
  const listId      = parseInt(process.env.BREVO_LIST_ID, 10);
  const senderEmail = process.env.BREVO_SENDER_EMAIL || 'info@oponoticias.com';
  const senderName  = process.env.BREVO_SENDER_NAME || 'OpoNoticias';

  if (!apiKey || !listId) {
    console.error('Faltan variables de entorno BREVO_API_KEY o BREVO_LIST_ID');
    return res.status(500).json({ error: 'Configuración incompleta' });
  }

  // 1) Alta del contacto en la lista
  const contacto = await brevoRequest('contacts', apiKey, {
    email,
    listIds: [listId],
    updateEnabled: true,
  });
  // 201 = creado, 204 = actualizado, duplicate_parameter = ya estaba suscrito
  const altaOk = [200, 201, 204].includes(contacto.status)
    || contacto.data.code === 'duplicate_parameter';
  if (!altaOk) {
    console.error('Brevo contacts error:', contacto.status, JSON.stringify(contacto.data));
    return res.status(502).json({ error: 'Error al suscribir' });
  }

  // 2) Email de bienvenida con el lead magnet.
  //    No bloquea la suscripción: si el envío falla, el contacto ya está dado
  //    de alta y recibirá el boletín diario igualmente.
  const correo = await brevoRequest('smtp/email', apiKey, {
    sender: { name: senderName, email: senderEmail },
    to: [{ email }],
    subject: `Tu descarga: ${mat.nombre} (gratis) 📥`,
    htmlContent: emailBienvenidaHtml(mat),
  });
  if (![200, 201].includes(correo.status)) {
    console.error('Brevo email bienvenida error (no bloquea):', correo.status, JSON.stringify(correo.data));
  }

  return res.status(200).json({ ok: true });
}
