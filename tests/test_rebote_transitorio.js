// tests/test_rebote_transitorio.js — cuándo un rebote TRANSITORIO debe dar de baja.
// Ejecuta:  node tests/test_rebote_transitorio.js
//
// Por qué existe: el endpoint solo daba de baja los rebotes Permanent, y a
// propósito ignoraba los Transient — un buzón lleno o un servidor caído se
// arregla solo y no debe costarle la suscripción a nadie.
//
// Pero hay un caso que NO se arregla nunca y llegaba como Transient:
// `nclariana@oulook.es` (typo de outlook.es) es un dominio ocupado por un
// squatter con `MX 0 localhost`, así que el correo no se entrega jamás. SES
// reintentaba 840 minutos, se rendía con `554 4.4.7 Message expired`, y como
// el código lo ignoraba la dirección seguía activa → otro intento al día
// siguiente → otro MAILER-DAEMON. Bucle diario, igual que el de julio.
//
// Regla: un transitorio que EXPIRA (SES agotó sus reintentos) o cuyo destino
// rechaza el relay es, en la práctica, permanente.

const path = require('path');
const { debeDarDeBaja } = require(path.join(__dirname, '..', 'api', '_lib', 'rebotes.js'));

const casos = [];
const test = (nombre, fn) => casos.push([nombre, fn]);

const bounce = (bounceType, bounceSubType, diagnosticCode) => ({
  bounceType,
  bounceSubType,
  bouncedRecipients: [{ emailAddress: 'x@ejemplo.com', diagnosticCode }],
});

// ── Permanentes: siempre fuera ─────────────────────────────────────────────
test('Permanent → baja', () =>
  debeDarDeBaja(bounce('Permanent', 'General', 'smtp; 550 5.1.1 User unknown')) === true);

test('Permanent/NoEmail → baja', () =>
  debeDarDeBaja(bounce('Permanent', 'NoEmail', '')) === true);

// ── EL CASO REAL que provocaba el bucle ────────────────────────────────────
test('🔴 Transient que EXPIRA tras reintentar → baja (el caso oulook.es)', () =>
  debeDarDeBaja(bounce('Transient', 'General',
    'smtp; 554 4.4.7 Message expired: unable to deliver in 840 minutes.' +
    '<454 4.7.1 <nclariana@oulook.es>: Relay access denied>')) === true);

test('🔴 Transient con "Relay access denied" → baja', () =>
  debeDarDeBaja(bounce('Transient', 'General', 'smtp; 454 4.7.1 Relay access denied')) === true);

test('🔴 Transient con "Message expired" → baja', () =>
  debeDarDeBaja(bounce('Transient', 'General', 'smtp; 554 Message expired')) === true);

// ── Transitorios de verdad: NO perder al suscriptor ────────────────────────
test('buzón lleno → NO baja (se vacía solo)', () =>
  debeDarDeBaja(bounce('Transient', 'MailboxFull', 'smtp; 452 4.2.2 Mailbox full')) === false);

test('servidor caído un rato → NO baja', () =>
  debeDarDeBaja(bounce('Transient', 'General',
    'smtp; 421 4.3.2 Service not available, try again later')) === false);

test('mensaje demasiado grande → NO baja', () =>
  debeDarDeBaja(bounce('Transient', 'MessageTooLarge', 'smtp; 552 Message too large')) === false);

test('contenido rechazado → NO baja', () =>
  debeDarDeBaja(bounce('Transient', 'ContentRejected', 'smtp; 550 Content rejected')) === false);

// ── Bordes ─────────────────────────────────────────────────────────────────
test('Undetermined → NO baja (no sabemos qué pasó)', () =>
  debeDarDeBaja(bounce('Undetermined', 'Undetermined', '')) === false);

test('sin diagnosticCode no revienta', () =>
  debeDarDeBaja(bounce('Transient', 'General', undefined)) === false);

test('sin bouncedRecipients no revienta', () =>
  debeDarDeBaja({ bounceType: 'Transient', bounceSubType: 'General' }) === false);

test('objeto vacío no revienta', () => debeDarDeBaja({}) === false);

test('null no revienta', () => debeDarDeBaja(null) === false);

(async () => {
  let fallos = 0;
  for (const [nombre, fn] of casos) {
    let ok = false;
    try { ok = await fn(); } catch (e) { ok = false; }
    console.log(`${ok ? '✓' : '✗'} ${nombre}`);
    if (!ok) fallos++;
  }
  console.log('─'.repeat(66));
  console.log(fallos ? `${fallos} test(s) fallaron` : 'TODO OK');
  process.exit(fallos ? 1 : 0);
})();
