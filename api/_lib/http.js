// api/_lib/http.js — helpers HTTP compartidos por los endpoints de newsletter
// (subscribe.js, preferencias.js, unsubscribe.js). El prefijo "_lib" hace que
// Vercel NO lo trate como una ruta propia.

const https = require('https');

// Petición HTTPS genérica. Resuelve SIEMPRE (nunca rechaza) con {status, data}
// — data es el body parseado como JSON, o {} si no se pudo parsear.
function httpsJson({ hostname, path, method = 'GET', headers = {}, body }) {
  return new Promise((resolve) => {
    const data = body !== undefined ? JSON.stringify(body) : undefined;
    const req = https.request(
      {
        hostname,
        path,
        method,
        headers: {
          ...headers,
          ...(data ? { 'Content-Length': Buffer.byteLength(data) } : {}),
        },
      },
      (response) => {
        let out = '';
        response.on('data', (chunk) => { out += chunk; });
        response.on('end', () => {
          let parsed = {};
          try { parsed = JSON.parse(out || '{}'); } catch (_) {}
          resolve({ status: response.statusCode, data: parsed });
        });
      }
    );
    req.on('error', (err) => resolve({ status: 0, data: { _err: String(err) } }));
    if (data) req.write(data);
    req.end();
  });
}

// Llama a la API de Brevo. Resuelve siempre con {status, data}.
function brevoRequest(path, apiKey, payload, method = 'POST') {
  return httpsJson({
    hostname: 'api.brevo.com',
    path: `/v3/${path}`,
    method,
    headers: {
      'api-key': apiKey,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: payload,
  });
}

// Upsert en Supabase (merge-duplicates por on_conflict). No bloquea: si faltan
// las variables de entorno, resuelve {status:0, skipped:true} sin lanzar.
function supabaseUpsert(table, rows, { onConflict = 'email' } = {}) {
  const baseUrl = process.env.SUPABASE_URL;
  const apiKey = process.env.SUPABASE_API_KEY;
  if (!baseUrl || !apiKey) return Promise.resolve({ status: 0, skipped: true });
  const u = new URL(`${baseUrl}/rest/v1/${table}?on_conflict=${onConflict}`);
  return httpsJson({
    hostname: u.hostname,
    path: u.pathname + u.search,
    method: 'POST',
    headers: {
      apikey: apiKey,
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      Prefer: 'resolution=merge-duplicates,return=minimal',
    },
    body: rows,
  });
}

// PATCH en Supabase (usado por unsubscribe.js). `pathWithQuery` incluye la
// tabla y el filtro (p. ej. "suscriptores?token_baja=eq.xxx"). Devuelve las
// filas afectadas (Prefer: return=representation) para poder confirmar match.
function supabasePatch(pathWithQuery, body) {
  const baseUrl = process.env.SUPABASE_URL;
  const apiKey = process.env.SUPABASE_API_KEY;
  if (!baseUrl || !apiKey) return Promise.resolve({ status: 0, data: [] });
  const u = new URL(`${baseUrl}/rest/v1/${pathWithQuery}`);
  return httpsJson({
    hostname: u.hostname,
    path: u.pathname + u.search,
    method: 'PATCH',
    headers: {
      apikey: apiKey,
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      Prefer: 'return=representation',
    },
    body,
  }).then((r) => ({ status: r.status, data: Array.isArray(r.data) ? r.data : [] }));
}

module.exports = { httpsJson, brevoRequest, supabaseUpsert, supabasePatch };
