// api/_lib/sns.js — Verificación de la firma de los mensajes de Amazon SNS.
//
// Aislado del endpoint (api/ses-bounce.js) para poder testearlo: es la única
// barrera que impide que cualquiera falsifique un aviso de rebote y dé de baja
// a un suscriptor con un POST.

const crypto = require('crypto');
const https = require('https');

// Campos que entran en la cadena firmada, EN ESTE ORDEN (spec de AWS SNS).
const CAMPOS_FIRMA = {
  Notification: ['Message', 'MessageId', 'Subject', 'Timestamp', 'TopicArn', 'Type'],
  SubscriptionConfirmation: ['Message', 'MessageId', 'SubscribeURL', 'Timestamp', 'Token', 'TopicArn', 'Type'],
  UnsubscribeConfirmation: ['Message', 'MessageId', 'SubscribeURL', 'Timestamp', 'Token', 'TopicArn', 'Type'],
};

// El certificado SOLO puede venir del propio SNS de AWS. Sin esta comprobación,
// un atacante apuntaría SigningCertURL a un dominio suyo y firmaría mensajes
// falsos con su propia clave (la firma cuadraría y pasaría el filtro).
const CERT_URL_OK = /^https:\/\/sns\.[a-z0-9-]+\.amazonaws\.com\/[\w\-/.]+\.pem$/;

function descargar(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (r) => {
      if (r.statusCode !== 200) { r.resume(); return reject(new Error('HTTP ' + r.statusCode)); }
      let d = '';
      r.on('data', (c) => { d += c; });
      r.on('end', () => resolve(d));
    }).on('error', reject);
  });
}

/** Cadena canónica "campo\nvalor\n" con los campos del tipo de mensaje. */
function cadenaCanonica(msg) {
  const campos = CAMPOS_FIRMA[msg.Type];
  if (!campos) return null;
  let out = '';
  for (const c of campos) {
    if (msg[c] === undefined || msg[c] === null) continue;   // Subject es opcional
    out += `${c}\n${msg[c]}\n`;
  }
  return out;
}

/**
 * Verifica la firma de un mensaje SNS. Devuelve true/false; nunca lanza.
 * `fetchCert` se inyecta en los tests para no depender de la red.
 */
async function verificarFirmaSNS(msg, fetchCert = descargar) {
  try {
    if (!msg || !msg.Signature) return false;
    const canonica = cadenaCanonica(msg);
    if (canonica === null) return false;
    if (!CERT_URL_OK.test(msg.SigningCertURL || '')) return false;

    const algoritmo = msg.SignatureVersion === '2' ? 'RSA-SHA256' : 'RSA-SHA1';
    const cert = await fetchCert(msg.SigningCertURL);
    return crypto.createVerify(algoritmo).update(canonica, 'utf8')
      .verify(cert, msg.Signature, 'base64');
  } catch (_) {
    return false;
  }
}

module.exports = { verificarFirmaSNS, cadenaCanonica, CERT_URL_OK, descargar };
