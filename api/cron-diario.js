// api/cron-diario.js — Serverless Function que dispara el workflow "Daily BOE
// Check" de GitHub Actions vía la API. La llama cada mañana un CRON EXTERNO
// (cron-job.org, gratis y fiable) — porque el scheduler de GitHub falló 3 días
// seguidos (ago 2026) y los crons de Vercel necesitan plan Pro. El propio
// leer_boe respeta la ventana matinal de envío.
//
// El cron externo debe hacer POST a https://oponoticias.com/api/cron-diario con
// la cabecera:  Authorization: Bearer <CRON_SECRET>
//
// Requiere (variables de entorno en Vercel, ambas GRATIS en Hobby):
//   GH_DISPATCH_TOKEN — PAT de GitHub (fine-grained) con permiso Actions: R/W
//                       sobre el repo Alexog91/oponoticias-web.
//   CRON_SECRET       — secreto que el cron externo envía en Authorization para
//                       que nadie más pueda disparar el proceso.

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
