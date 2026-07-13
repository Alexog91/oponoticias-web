// Vercel Serverless Function — alta en el newsletter (tabla `suscriptores` de
// Supabase, fuente de verdad) + envío automático del lead magnet por Amazon SES.
// Variables de entorno en Vercel: SUPABASE_URL, SUPABASE_API_KEY,
//   SES_SMTP_USER, SES_SMTP_PASS  (opcionales: SENDER_EMAIL, SENDER_NAME).

const { supabaseUpsert } = require('./_lib/http');
const { enviarEmailSES } = require('./_lib/ses');

const BASE = 'https://oponoticias.com/descargas';

// Catálogo de materiales descargables. La clave es el `slug` que envía el
// front-end; cada uno define el nombre y el archivo a entregar por email.
// Si no llega `material` (formulario de la home / pop-up), se usa MATERIAL_DEFECTO.
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
    nombre: 'Kit del Opositor',
    desc: 'tu agenda en Excel para preparar la oposición: retroplanning, repaso espaciado (1, 7 y 30 días) y tracker de tests que detecta tus temas flojos',
    url: `${BASE}/kit-del-opositor.xlsx`,
    // El Kit es un .xlsx: sin la guía de uso cuesta arrancar (y en el móvil no
    // siempre se abre). Se adjunta como enlace secundario en el email.
    extra: { nombre: 'guía de uso (PDF)', url: `${BASE}/kit-del-opositor.pdf` },
  },
  'kit-del-opositor-guia': {
    nombre: 'Kit del Opositor (guía de uso, PDF)',
    desc: 'cómo sacarle el máximo partido al Kit del Opositor paso a paso',
    url: `${BASE}/kit-del-opositor.pdf`,
  },
};
const MATERIAL_DEFECTO = 'kit-del-opositor';

// Alta/actualización del suscriptor en Supabase (tabla `suscriptores`). Upsert
// por email (merge-duplicates). Se omite token_baja (lo pone el default de la BD
// en las filas nuevas y se conserva en las existentes).
function supabaseUpsertSuscriptor(fields) {
  return supabaseUpsert('suscriptores', [fields]);
}

function emailBienvenidaHtml(material, email) {
  const prefUrl = `https://oponoticias.com/preferencias?e=${encodeURIComponent(email || '')}`;
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
    <p style="text-align:center;margin:24px 0 ${material.extra ? '10px' : '24px'};">
      <a href="${material.url}" target="_blank" rel="noopener"
         style="display:inline-block;background:#5a5047;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-size:15px;font-weight:600;">
        📥 Descargar ${material.nombre}
      </a>
    </p>
    ${material.extra ? `<p style="text-align:center;margin:0 0 24px;color:#8b8b7a;font-size:14px;">
      Y aquí tienes la <a href="${material.extra.url}" target="_blank" rel="noopener"
         style="color:#c4a574;text-decoration:none;font-weight:600;">${material.extra.nombre}</a>
      para sacarle todo el partido.
    </p>` : ''}
    <p style="margin:0 0 8px;color:#4a4540;font-size:15px;line-height:1.6;">
      A partir de mañana recibirás cada día laborable un resumen de las nuevas convocatorias del BOE,
      organizadas por categoría y comunidad autónoma. No se te escapará ninguna plaza.
    </p>

    <!-- Bloque de bienvenida: cómo usarlo + síguenos (todo en este único email) -->
    <div style="margin:22px 0 6px;padding:20px 22px;background:#f8f6f2;border-radius:10px;">
      <p style="margin:0 0 12px;color:#2b2622;font-size:16px;font-weight:700;font-family:'Georgia',serif;">Para empezar</p>
      <p style="margin:0 0 10px;color:#4a4540;font-size:14px;line-height:1.6;">
        🔎 <strong>Busca las de tu comunidad:</strong> en la web puedes filtrar todas las convocatorias
        por comunidad autónoma y categoría, con enlace directo al BOE.
        <a href="https://oponoticias.com/boe-hoy" style="color:#c4a574;text-decoration:none;font-weight:600;">Verlas ahora&nbsp;→</a>
      </p>
      <p style="margin:0 0 10px;color:#4a4540;font-size:14px;line-height:1.6;">
        📍 <strong>Recibe solo lo de tu zona:</strong> elige tu comunidad y el correo diario te traerá solo
        tus convocatorias (más las de ámbito estatal).
        <a href="${prefUrl}" style="color:#c4a574;text-decoration:none;font-weight:600;">Elegir comunidad&nbsp;→</a>
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

  const { email, material, comunidad } = req.body || {};

  // Validación básica
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: 'Email inválido' });
  }
  // Comunidad opcional (viene de un <select> controlado; validación laxa).
  const com = typeof comunidad === 'string' ? comunidad.trim().slice(0, 40) : '';

  // Material a entregar (por slug). Si no llega o es desconocido → MATERIAL_DEFECTO.
  const matSlug = MATERIALES[material] ? material : MATERIAL_DEFECTO;
  const mat = MATERIALES[matSlug];

  // 1) Alta en Supabase, la fuente de verdad. Opt-in explícito → estado 'activo'
  //    (reactiva si alguien se había dado de baja y vuelve a suscribirse). Solo se
  //    manda comunidad si viene (para no pisar una preferencia ya guardada).
  const sb = await supabaseUpsertSuscriptor({
    email,
    estado: 'activo',
    origen: material ? 'recursos' : 'web',
    material: matSlug,
    ...(com ? { comunidad: com } : {}),
  });
  if (sb.skipped) {
    console.error('Faltan SUPABASE_URL / SUPABASE_API_KEY');
    return res.status(500).json({ error: 'Configuración incompleta' });
  }
  if (!(sb.status >= 200 && sb.status < 300)) {
    console.error('Supabase upsert suscriptor:', sb.status, JSON.stringify(sb.data).slice(0, 200));
    return res.status(502).json({ error: 'Error al suscribir' });
  }

  // 2) Email de bienvenida con el lead magnet, por Amazon SES. NO bloquea: si el
  //    envío falla, el alta ya está hecha y recibirá el boletín diario igualmente.
  const correo = await enviarEmailSES({
    from: process.env.SENDER_EMAIL || 'info@oponoticias.com',
    fromName: process.env.SENDER_NAME || 'OpoNoticias',
    to: email,
    subject: `Tu descarga: ${mat.nombre} (gratis) 📥`,
    html: emailBienvenidaHtml(mat, email),
  });
  if (!correo.ok) {
    console.error('Email bienvenida SES (no bloquea):', correo.message);
  }

  return res.status(200).json({ ok: true });
}
