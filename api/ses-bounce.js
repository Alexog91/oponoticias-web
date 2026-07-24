// api/ses-bounce.js — Recibe de Amazon SES (vía SNS) los avisos de rebote y de
// queja (spam) y marca al suscriptor en Supabase para no volver a escribirle.
//
// Por qué existe: sin esto, una dirección muerta se queda como 'activo' en la
// tabla, le intentamos enviar CADA DÍA, SES lo rechaza (está en su lista de
// supresión) y nos devuelve un aviso de fallo diario. Pasó en julio de 2026 con
// una dirección: 29 correos de MAILER-DAEMON en una semana.
//
// Seguridad: se verifica la FIRMA del mensaje con el certificado de AWS y que el
// TopicArn sea el nuestro. Sin eso, cualquiera podría dar de baja a un
// suscriptor haciendo un POST a este endpoint.
//
// Env en Vercel: SUPABASE_URL, SUPABASE_API_KEY, SNS_TOPIC_ARN.

const { supabasePatch } = require('./_lib/http');
const { verificarFirmaSNS, descargar } = require('./_lib/sns');
const { debeDarDeBaja } = require('./_lib/rebotes');

async function marcar(email, estado) {
  const filtro = `suscriptores?email=eq.${encodeURIComponent(email)}`;
  const r = await supabasePatch(filtro, { estado, fecha_baja: new Date().toISOString() });
  const ok = r.status >= 200 && r.status < 300 && Array.isArray(r.data) && r.data.length > 0;
  console.log(ok ? `✓ ${email} → ${estado}` : `· ${email}: sin fila que actualizar (${r.status})`);
  return ok;
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  // SNS envía Content-Type: text/plain, así que el body puede llegar sin parsear.
  let msg = req.body;
  try {
    if (typeof msg === 'string') msg = JSON.parse(msg);
  } catch (_) {
    return res.status(400).json({ error: 'Body no es JSON' });
  }
  if (!msg || !msg.Type) return res.status(400).json({ error: 'Falta Type' });

  // El tema debe ser el nuestro (además de la firma).
  const arnEsperado = process.env.SNS_TOPIC_ARN;
  if (arnEsperado && msg.TopicArn !== arnEsperado) {
    console.error('TopicArn inesperado:', msg.TopicArn);
    return res.status(403).json({ error: 'Topic no autorizado' });
  }

  try {
    if (!(await verificarFirmaSNS(msg))) {
      console.error('Firma SNS inválida');
      return res.status(403).json({ error: 'Firma inválida' });
    }
  } catch (e) {
    console.error('Error verificando firma:', e.message);
    return res.status(403).json({ error: 'Firma no verificable' });
  }

  // 1) Alta del endpoint: SNS manda una confirmación que hay que visitar.
  if (msg.Type === 'SubscriptionConfirmation') {
    await descargar(msg.SubscribeURL);
    console.log('✓ Suscripción SNS confirmada');
    return res.status(200).json({ ok: true, confirmed: true });
  }

  // 2) Aviso real de SES.
  if (msg.Type === 'Notification') {
    let ev;
    try { ev = JSON.parse(msg.Message); } catch (_) { return res.status(200).json({ ok: true }); }

    if (ev.notificationType === 'Bounce') {
      // Los permanentes dan de baja siempre. Los transitorios solo si el
      // diagnóstico dice que la entrega ya no va a ocurrir nunca (ver
      // _lib/rebotes.js): un buzón lleno se vacía, pero un dominio que rechaza
      // el relay seguirá rechazándolo mañana, y nos deja en bucle diario.
      if (debeDarDeBaja(ev.bounce)) {
        for (const d of ev.bounce.bouncedRecipients || []) {
          if (d.emailAddress) await marcar(d.emailAddress, 'rebote');
        }
      } else {
        console.log('Rebote transitorio recuperable, se mantiene:',
                    ev.bounce?.bounceType, ev.bounce?.bounceSubType);
      }
    } else if (ev.notificationType === 'Complaint') {
      // Marcó el correo como spam: fuera de la lista inmediatamente.
      for (const d of ev.complaint?.complainedRecipients || []) {
        if (d.emailAddress) await marcar(d.emailAddress, 'baja');
      }
    }
  }

  // Siempre 200: si devolviéramos error, SNS reintentaría en bucle.
  return res.status(200).json({ ok: true });
}
