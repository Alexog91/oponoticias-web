// tests/test_sns_firma.js — Verificación de firma de SNS (api/_lib/sns.js).
// Ejecuta:  node tests/test_sns_firma.js
//
// Es la única barrera que impide que alguien falsifique un aviso de rebote y dé
// de baja a un suscriptor con un POST a /api/ses-bounce. Se prueba con un par de
// claves generado al vuelo (la clave pública hace de "certificado"), inyectando
// el descargador para no depender de la red.

const crypto = require('crypto');
const path = require('path');
const { verificarFirmaSNS, cadenaCanonica, CERT_URL_OK } =
  require(path.join(__dirname, '..', 'api', '_lib', 'sns.js'));

const { publicKey, privateKey } = crypto.generateKeyPairSync('rsa', {
  modulusLength: 2048,
  publicKeyEncoding: { type: 'spki', format: 'pem' },
  privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
});

const CERT_URL = 'https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-abc123.pem';
const fetchCert = async () => publicKey;

function mensajeFirmado(extra = {}) {
  const msg = {
    Type: 'Notification',
    MessageId: 'm-1',
    TopicArn: 'arn:aws:sns:eu-west-1:819947220143:oponoticias-ses-bounces',
    Message: JSON.stringify({ notificationType: 'Bounce' }),
    Timestamp: '2026-07-22T10:00:00.000Z',
    SignatureVersion: '1',
    SigningCertURL: CERT_URL,
    ...extra,
  };
  const firma = crypto.createSign('RSA-SHA1').update(cadenaCanonica(msg), 'utf8');
  msg.Signature = firma.sign(privateKey, 'base64');
  return msg;
}

const casos = [];
const test = (nombre, fn) => casos.push([nombre, fn]);

test('acepta un mensaje legítimo bien firmado', async () => {
  return (await verificarFirmaSNS(mensajeFirmado(), fetchCert)) === true;
});

test('RECHAZA si manipulan el Message tras firmar (ataque principal)', async () => {
  const m = mensajeFirmado();
  m.Message = JSON.stringify({ notificationType: 'Bounce', bounce: { bounceType: 'Permanent' } });
  return (await verificarFirmaSNS(m, fetchCert)) === false;
});

test('RECHAZA si cambian el TopicArn tras firmar', async () => {
  const m = mensajeFirmado();
  m.TopicArn = 'arn:aws:sns:eu-west-1:000000000000:otro';
  return (await verificarFirmaSNS(m, fetchCert)) === false;
});

test('RECHAZA una firma inventada', async () => {
  const m = mensajeFirmado();
  m.Signature = Buffer.from('basura').toString('base64');
  return (await verificarFirmaSNS(m, fetchCert)) === false;
});

test('RECHAZA si falta la firma', async () => {
  const m = mensajeFirmado();
  delete m.Signature;
  return (await verificarFirmaSNS(m, fetchCert)) === false;
});

test('RECHAZA un tipo de mensaje desconocido', async () => {
  // Se firma como Notification válido y se cambia el Type después: es lo que
  // haría un atacante. cadenaCanonica no sabe qué campos firmar → se rechaza.
  const m = mensajeFirmado();
  m.Type = 'LoQueSea';
  return (await verificarFirmaSNS(m, fetchCert)) === false;
});

test('RECHAZA certificados de dominios que no son de AWS (spoofing)', () => {
  const malas = [
    'https://sns.eu-west-1.amazonaws.com.atacante.com/x.pem',
    'http://sns.eu-west-1.amazonaws.com/x.pem',            // sin TLS
    'https://atacante.com/SimpleNotificationService.pem',
    'https://evil.com/?u=https://sns.eu-west-1.amazonaws.com/x.pem',
  ];
  const buenas = ['https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-abc123.pem'];
  return malas.every((u) => !CERT_URL_OK.test(u)) && buenas.every((u) => CERT_URL_OK.test(u));
});

(async () => {
  let fallos = 0;
  for (const [nombre, fn] of casos) {
    let ok = false;
    try { ok = await fn(); } catch (e) { ok = false; }
    console.log(`${ok ? '✓' : '✗'} ${nombre}`);
    if (!ok) fallos++;
  }
  console.log('─'.repeat(58));
  console.log(fallos ? `${fallos} test(s) fallaron` : 'TODO OK');
  process.exit(fallos ? 1 : 0);
})();
