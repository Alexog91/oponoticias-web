// api/_lib/ses.js — Envía UN email por SMTP de Amazon SES usando solo módulos
// nativos de Node (net + tls), sin dependencias (mismo criterio zero-deps que el
// resto de api/, para no añadir package.json ni tocar el build de Vercel).
// Se usa para el email de bienvenida del alta (subscribe.js).
//
// enviarEmailSES(...) NUNCA lanza: devuelve { ok:boolean, message:string }.
// Env (en Vercel): SES_SMTP_USER, SES_SMTP_PASS.  Opcionales: SES_SMTP_HOST/PORT.

const net = require('net');
const tls = require('tls');

const HOST = process.env.SES_SMTP_HOST || 'email-smtp.eu-west-1.amazonaws.com';
const PORT = parseInt(process.env.SES_SMTP_PORT || '587', 10);
const TIMEOUT_MS = 15000;

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
// Cabecera con posibles no-ASCII (asunto con tildes/emoji) → RFC 2047 base64.
const encHeader = (s) => (/[^\x00-\x7F]/.test(s) ? `=?UTF-8?B?${b64(s)}?=` : s);
// Cuerpo en base64 partido en líneas de 76 (RFC 2045) → evita dot-stuffing y
// problemas de longitud de línea del SMTP con HTML UTF-8.
const wrap76 = (s) => s.replace(/(.{1,76})/g, '$1\r\n').trimEnd();

// Lee respuestas SMTP de un socket. Junta las líneas de continuación
// ("NNN-...") hasta la final ("NNN ..." con espacio). read() → {code, text}.
function crearLector(sock) {
  let buffer = '';
  let acc = [];
  const listos = [];
  const esperando = [];
  sock.on('data', (d) => {
    buffer += d.toString('utf8');
    let nl;
    while ((nl = buffer.indexOf('\r\n')) !== -1) {
      const ln = buffer.slice(0, nl);
      buffer = buffer.slice(nl + 2);
      acc.push(ln);
      if (/^\d{3} /.test(ln)) {           // línea final de la respuesta
        const rep = { code: parseInt(ln.slice(0, 3), 10), text: acc.join('\n') };
        acc = [];
        esperando.length ? esperando.shift()(rep) : listos.push(rep);
      }
    }
  });
  return () => new Promise((res) => (listos.length ? res(listos.shift()) : esperando.push(res)));
}

function enviarEmailSES({ from, fromName, to, subject, html }) {
  const user = process.env.SES_SMTP_USER;
  const pass = process.env.SES_SMTP_PASS;
  if (!user || !pass) return Promise.resolve({ ok: false, message: 'faltan SES_SMTP_USER/PASS' });

  const mensaje = [
    `From: ${fromName ? encHeader(fromName) + ' ' : ''}<${from}>`,
    `To: <${to}>`,
    `Subject: ${encHeader(subject)}`,
    'MIME-Version: 1.0',
    'Content-Type: text/html; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
    '',
    wrap76(b64(html)),
  ].join('\r\n');

  return new Promise((resolve) => {
    let terminado = false;
    const fin = (ok, message) => {
      if (terminado) return;
      terminado = true;
      resolve({ ok, message });
    };

    let sock = net.connect(PORT, HOST);
    const armar = (s) => {
      s.setTimeout(TIMEOUT_MS);
      s.on('error', (e) => fin(false, 'socket: ' + e.message));
      s.on('timeout', () => { try { s.destroy(); } catch (_) {} fin(false, 'timeout'); });
    };
    armar(sock);

    (async () => {
      try {
        let leer = crearLector(sock);
        const esperar = async (claseOk, etapa) => {
          const r = await leer();
          if (Math.floor(r.code / 100) !== claseOk) {
            throw new Error(`${etapa}: ${r.code} ${r.text.replace(/\s+/g, ' ').slice(0, 90)}`);
          }
          return r;
        };
        const escribir = (l) => sock.write(l + '\r\n');

        await esperar(2, 'saludo');            // 220
        escribir('EHLO oponoticias.com');
        await esperar(2, 'EHLO');              // 250
        escribir('STARTTLS');
        await esperar(2, 'STARTTLS');          // 220

        // Upgrade a TLS sobre el mismo socket.
        sock = tls.connect({ socket: sock, servername: HOST });
        armar(sock);
        await new Promise((res, rej) => {
          sock.once('secureConnect', res);
          sock.once('error', rej);
        });
        leer = crearLector(sock);

        escribir('EHLO oponoticias.com');
        await esperar(2, 'EHLO-tls');          // 250
        escribir('AUTH LOGIN');
        await esperar(3, 'AUTH');              // 334
        escribir(b64(user));
        await esperar(3, 'usuario');           // 334
        escribir(b64(pass));
        await esperar(2, 'password');          // 235
        escribir(`MAIL FROM:<${from}>`);
        await esperar(2, 'MAIL FROM');         // 250
        escribir(`RCPT TO:<${to}>`);
        await esperar(2, 'RCPT TO');           // 250
        escribir('DATA');
        await esperar(3, 'DATA');              // 354
        sock.write(mensaje + '\r\n.\r\n');
        await esperar(2, 'fin de datos');      // 250
        escribir('QUIT');
        try { sock.end(); } catch (_) {}
        fin(true, 'enviado');
      } catch (e) {
        try { sock.destroy(); } catch (_) {}
        fin(false, e.message);
      }
    })();
  });
}

module.exports = { enviarEmailSES };
