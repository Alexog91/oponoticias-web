// test_ses_helper.js — Prueba de api/_lib/ses.js (cliente SMTP SES nativo).
// Envía UN email real a TEST_TO (o info@oponoticias.com) usando los secretos
// SES_SMTP_USER/PASS. Sirve para validar el cliente antes de cablearlo al alta.
//   TEST_TO=info@oponoticias.com node test_ses_helper.js
const { enviarEmailSES } = require('./api/_lib/ses');

const to = process.env.TEST_TO || 'info@oponoticias.com';

(async () => {
  const r = await enviarEmailSES({
    from: 'info@oponoticias.com',
    fromName: 'OpoNoticias',
    to,
    subject: 'Prueba del cliente SMTP de SES ✅ (tildes: ñ á)',
    html: '<h1>Funciona 🎉</h1><p>Este correo confirma que <b>api/_lib/ses.js</b> '
        + 'envía por SMTP de Amazon SES sin dependencias. Tildes y emoji: ñ, é, 📥.</p>',
  });
  console.log('Resultado:', JSON.stringify(r));
  process.exit(r.ok ? 0 : 1);
})();
