// api/cron-diario.js — Vercel Serverless Function llamada por un Vercel Cron cada
// mañana. Dispara el workflow "Daily BOE Check" de GitHub Actions vía la API,
// SIN depender del scheduler de GitHub (que en ago 2026 falló 3 días seguidos,
// disparando los crons con 9-11h de retraso o nada). Los crons de Vercel son
// mucho más fiables. El propio leer_boe respeta la ventana matinal de envío.
//
// Requiere (variables de entorno en Vercel):
//   GH_DISPATCH_TOKEN — PAT de GitHub (fine-grained) con permiso Actions: R/W
//                       sobre el repo Alexog91/oponoticias-web.
//   CRON_SECRET       — (opcional pero recomendado) secreto que Vercel envía en
//                       la cabecera Authorization de las peticiones de cron.

const REPO = 'Alexog91/oponoticias-web';
const WORKFLOW = 'daily-boe.yml';

export default async function handler(req, res) {
  // Seguridad: si hay CRON_SECRET, exigir la cabecera que Vercel Cron envía.
  const secret = process.env.CRON_SECRET;
  if (secret && req.headers['authorization'] !== `Bearer ${secret}`) {
    return res.status(401).json({ error: 'No autorizado' });
  }

  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) {
    console.error('Falta GH_DISPATCH_TOKEN en el entorno de Vercel.');
    return res.status(500).json({ error: 'Configuración incompleta (GH_DISPATCH_TOKEN)' });
  }

  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
        'User-Agent': 'oponoticias-cron',
      },
      body: JSON.stringify({ ref: 'main' }),
    });

    // GitHub responde 204 (sin cuerpo) cuando acepta el dispatch.
    if (r.status === 204) {
      return res.status(200).json({ ok: true, dispatched: WORKFLOW });
    }
    const txt = await r.text();
    console.error('GitHub dispatch falló:', r.status, txt.slice(0, 300));
    return res.status(502).json({ error: 'No se pudo disparar el workflow', status: r.status });
  } catch (e) {
    console.error('Error llamando a la API de GitHub:', e);
    return res.status(502).json({ error: 'Error de red al disparar el workflow' });
  }
}
