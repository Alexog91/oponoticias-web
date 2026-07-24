// api/_lib/rebotes.js — decidir si un rebote de SES debe dar de baja.
//
// Aislado del endpoint (api/ses-bounce.js) para poder testearlo: equivocarse
// aquí cuesta suscriptores (si damos de baja de más) o un bucle de correos
// diarios de MAILER-DAEMON (si damos de baja de menos).

// Un rebote transitorio normal —buzón lleno, servidor caído— se arregla solo y
// NO debe costarle la suscripción a nadie. Pero estos dos casos llegan como
// Transient y no se arreglan jamás:
//
//   · "Message expired": SES agotó sus reintentos (hasta 14 h). Si no entró en
//     14 h, no va a entrar mañana.
//   · "Relay access denied": el servidor de destino rechaza de plano el correo.
//     Típico de dominios ocupados por squatters con `MX 0 localhost`, que es
//     justo lo que hay detrás de los typos de dominios populares.
//
// Caso real (24 jul 2026): nclariana@oulook.es — typo de outlook.es, dominio
// squatter con MX a localhost. Rebotaba a diario sin que nadie lo diera de baja.
const DEFINITIVO_PESE_A_TRANSIENT = /message expired|relay access denied|unable to deliver in \d+ minutes/i;

/**
 * ¿Este rebote significa que la dirección está muerta?
 * `bounce` es el objeto `bounce` del evento de SES. Nunca lanza.
 */
function debeDarDeBaja(bounce) {
  if (!bounce || typeof bounce !== 'object') return false;
  if (bounce.bounceType === 'Permanent') return true;
  if (bounce.bounceType !== 'Transient') return false;

  // Transient: solo si el diagnóstico dice que ya no hay nada que hacer.
  const destinatarios = Array.isArray(bounce.bouncedRecipients) ? bounce.bouncedRecipients : [];
  return destinatarios.some((d) => DEFINITIVO_PESE_A_TRANSIENT.test(d?.diagnosticCode || ''));
}

module.exports = { debeDarDeBaja, DEFINITIVO_PESE_A_TRANSIENT };
