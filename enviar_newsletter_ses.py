"""
enviar_newsletter_ses.py — Motor de envío propio del boletín diario vía Amazon SES.

REEMPLAZO (en construcción, Fase 3 del PLAN-EMAIL-SES.md) de enviar_newsletter.py.
NO se conecta a ningún workflow todavía: Brevo sigue siendo el canal oficial hasta
el corte. Este script se puede ejecutar a mano en modo prueba sin afectar a nada.

Diferencias clave con la versión de Brevo:
  - Los suscriptores se leen de la tabla `suscriptores` de Supabase (no de una lista
    de Brevo). Ver crear_tabla_suscriptores.sql.
  - El filtrado por comunidad autónoma se hace EN PYTHON (no con etiquetas
    condicionales {% if %} de Brevo): se genera el HTML ya filtrado para cada contacto.
  - El envío es contacto a contacto por SMTP de Amazon SES (biblioteca estándar
    `smtplib`, sin boto3). Cada correo lleva cabecera List-Unsubscribe de 1 clic.
  - Idempotencia por la tabla `envios_newsletter` (una fila por día = ya enviado).

Variables de entorno:
  SUPABASE_URL        — URL del proyecto Supabase
  SUPABASE_API_KEY    — Clave service_role LEGACY (JWT eyJ…, no sb_secret_)
  SES_SMTP_HOST       — (opcional) por defecto email-smtp.eu-west-1.amazonaws.com
  SES_SMTP_PORT       — (opcional) por defecto 587 (STARTTLS)
  SES_SMTP_USER       — usuario SMTP de SES (SES → Configuración de SMTP → crear cred.)
  SES_SMTP_PASS       — contraseña SMTP de SES
  SENDER_EMAIL        — (opcional) remitente, por defecto info@oponoticias.com
  SENDER_NAME         — (opcional) por defecto "OpoNoticias"
  SITE_URL            — (opcional) por defecto https://oponoticias.com

Modos para las pruebas (Fase 4, sin tocar la lista real):
  TEST_EMAILS         — si se define (correos separados por comas), IGNORA la tabla
                        de suscriptores y envía SOLO a esas direcciones (comunidad
                        tomada de TEST_COMUNIDAD, o "" = ve todo). Para probar entrega.
  TEST_COMUNIDAD      — comunidad simulada para los TEST_EMAILS (opcional).
  DRY_RUN=1           — construye los correos y lo registra por pantalla, pero NO envía
                        ni toca Supabase. Para revisar sin mandar nada.
"""

import os
import re
import ssl
import json
import time
import html as html_lib
import smtplib
import urllib.request
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime, formataddr
from datetime import datetime, date

import newsletter_utils

SUPABASE_URL     = os.environ["SUPABASE_URL"]
SUPABASE_API_KEY = os.environ["SUPABASE_API_KEY"]

SES_SMTP_HOST = os.environ.get("SES_SMTP_HOST", "email-smtp.eu-west-1.amazonaws.com")
SES_SMTP_PORT = int(os.environ.get("SES_SMTP_PORT", "587"))
SES_SMTP_USER = os.environ.get("SES_SMTP_USER", "")
SES_SMTP_PASS = os.environ.get("SES_SMTP_PASS", "")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "info@oponoticias.com")
SENDER_NAME  = os.environ.get("SENDER_NAME", "OpoNoticias")
SITE_URL     = os.environ.get("SITE_URL", "https://oponoticias.com").rstrip("/")

TEST_EMAILS    = [e.strip() for e in os.environ.get("TEST_EMAILS", "").split(",") if e.strip()]
TEST_COMUNIDAD = os.environ.get("TEST_COMUNIDAD", "")
DRY_RUN        = os.environ.get("DRY_RUN") == "1"
# Pausa entre envíos (seg). Producción SES admite 14/seg; en sandbox es 1/seg,
# así que en pruebas conviene subirlo (p.ej. SEND_INTERVAL=1.1).
SEND_INTERVAL  = float(os.environ.get("SEND_INTERVAL", "0.3"))

HOY = date.today().isoformat()

# Comunidades de ámbito estatal/nacional (o sin dato): las ve TODO el mundo.
# Idéntico a enviar_newsletter.py para no divergir el criterio de segmentación.
_ESTATAL = {"", "nacional", "nacional/estatal", "estatal", "espana", "españa"}

formatear_fecha_larga = newsletter_utils.formatear_fecha_larga


# ── Supabase (REST) ─────────────────────────────────────────────────
def supabase_get(endpoint, params):
    return newsletter_utils.supabase_get(SUPABASE_URL, SUPABASE_API_KEY, endpoint, params)


def supabase_write(endpoint, body, method="POST", params=None):
    """INSERT (POST) / UPDATE (PATCH) en Supabase. Devuelve (status, data).
    La escritura necesita la cabecera Authorization además de apikey (RLS)."""
    qs = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}{qs}"
    data = json.dumps(body).encode("utf-8")
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, (resp.read() or b"")
    except urllib.request.HTTPError as e:
        return e.code, e.read() or b""


def obtener_convocatorias_hoy():
    # `fecha` se guarda como string RFC, no ISO → traemos recientes y filtramos
    # en Python comparando la fecha parseada con hoy (igual que la versión Brevo).
    rows = supabase_get("convocatorias", {
        "order": "id.desc",
        "limit": "150",
        "select": "titulo,fecha,enlace,resumen_claude,categoria,comunidad_autonoma",
    })
    hoy = date.today()
    de_hoy = []
    for r in rows:
        try:
            if parsedate_to_datetime(r["fecha"]).date() == hoy:
                de_hoy.append(r)
        except Exception:
            continue
    print(f"  {len(de_hoy)} convocatorias de hoy ({hoy}) — de {len(rows)} recientes")
    return de_hoy


def obtener_suscriptores():
    """Suscriptores activos. En modo TEST devuelve los TEST_EMAILS simulados."""
    if TEST_EMAILS:
        print(f"  🧪 Modo prueba: {len(TEST_EMAILS)} destinatario(s) de TEST_EMAILS "
              f"(comunidad simulada: '{TEST_COMUNIDAD or 'todas'}')")
        return [{"email": e, "comunidad": TEST_COMUNIDAD, "token_baja": "test"}
                for e in TEST_EMAILS]
    subs = supabase_get("suscriptores", {
        "select": "email,comunidad,token_baja",
        "estado": "eq.activo",
    })
    print(f"  {len(subs)} suscriptores activos")
    return subs


# ── Segmentación por comunidad (en Python) ──────────────────────────
def _es_estatal(ccaa):
    return (ccaa or "").strip().lower() in _ESTATAL


def convocatorias_para(comunidad, convocatorias):
    """Devuelve las convocatorias que le tocan a un suscriptor según su comunidad.
    - Sin comunidad (o estatal) → las ve TODAS.
    - Con una CCAA concreta → solo las suyas + las de ámbito estatal.
    Misma regla que la condición {% if %} que usaba Brevo, resuelta en Python."""
    if _es_estatal(comunidad):
        return list(convocatorias)
    objetivo = comunidad.strip()
    return [c for c in convocatorias
            if _es_estatal(c.get("comunidad_autonoma"))
            or (c.get("comunidad_autonoma") or "").strip() == objetivo]


# ── Construcción del HTML (reutiliza la estética de la versión Brevo) ─
def tarjeta_html(c):
    titulo   = html_lib.escape(c.get("titulo", ""))
    enlace   = html_lib.escape(c.get("enlace", "#"))
    cat      = html_lib.escape(c.get("categoria", "") or "")
    ccaa     = html_lib.escape((c.get("comunidad_autonoma") or "").strip())

    # resumen_claude es un STRING "N PLAZAS - PUESTO - LUGAR" (no JSON).
    plazas_txt = ""
    puesto = ""
    rc = c.get("resumen_claude")
    if rc:
        limpio = re.sub(r'\*\*', '', str(rc))
        limpio = re.sub(r'#+\s', '', limpio).strip()
        partes = [p.strip() for p in limpio.split(' - ') if p.strip()]
        if partes:
            m = re.search(r'\d[\d.]*', partes[0])
            if m:
                num = m.group()
                plazas_txt = f"{num} plaza" + ("" if num == "1" else "s")
            elif partes[0]:
                plazas_txt = partes[0].capitalize()
        if len(partes) > 1:
            puesto = html_lib.escape(partes[1].capitalize())

    badge_cat  = f'<span style="background:#efe9e0;color:#5a5047;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600;margin-right:6px;">{cat}</span>' if cat else ""
    badge_ccaa = f'<span style="background:#f0f4ee;color:#7a8b6e;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600;">{ccaa}</span>' if ccaa else ""
    badge_plazas = f'<span style="background:#f8f6f2;color:#5a5047;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:700;margin-left:8px;">{html_lib.escape(plazas_txt)}</span>' if plazas_txt else ""

    detalle_html = f'<p style="margin:4px 0 0;color:#5a5047;font-size:14px;font-weight:600;">{puesto}</p>' if puesto else ""

    return f"""
    <tr>
      <td style="padding:16px 24px;border-bottom:1px solid #e7e0d5;">
        <div style="margin-bottom:6px;">{badge_cat}{badge_ccaa}{badge_plazas}</div>
        <a href="{enlace}" style="font-family:'Georgia',serif;font-size:15px;font-weight:700;color:#2b2622;text-decoration:none;"
           target="_blank" rel="noopener">{titulo}</a>
        {detalle_html}
        <p style="margin:8px 0 0;">
          <a href="{enlace}" style="font-size:12px;color:#c4a574;text-decoration:none;" target="_blank" rel="noopener">
            Ver en el BOE →
          </a>
        </p>
      </td>
    </tr>"""


def construir_html(convocatorias_suyas, total_hoy, comunidad, unsubscribe_url):
    """HTML del correo YA filtrado para un suscriptor concreto. `comunidad` decide
    el bloque de contexto; `total_hoy` es el total del día (para el que filtra)."""
    fecha_larga = formatear_fecha_larga(HOY)
    n = len(convocatorias_suyas)

    if convocatorias_suyas:
        cuerpo_tabla = "".join(tarjeta_html(c) for c in convocatorias_suyas)
    else:
        cuerpo_tabla = """
        <tr><td style="padding:24px;text-align:center;color:#8b8b7a;font-size:14px;">
          Hoy no se han publicado convocatorias de tu comunidad ni de ámbito estatal.
        </td></tr>"""

    # Bloque de contexto/preferencias, resuelto en Python (no con {% if %}).
    if not _es_estatal(comunidad):
        pref = (f'📍 <strong>Estás viendo solo las de {html_lib.escape(comunidad)}</strong> '
                f'y las de ámbito estatal. Hoy se han publicado <strong>{total_hoy}</strong> '
                f"convocatoria{'s' if total_hoy != 1 else ''} en total en el BOE. "
                f'<a href="{SITE_URL}/boe-hoy" style="color:#c4a574;text-decoration:none;font-weight:600;">Ver todas&nbsp;→</a> '
                f'&nbsp;·&nbsp; '
                f'<a href="{SITE_URL}/preferencias" style="color:#c4a574;text-decoration:none;font-weight:600;">cambiar comunidad</a>')
    else:
        pref = ('📍 <strong>¿Solo te interesan las de tu comunidad?</strong> '
                f'<a href="{SITE_URL}/preferencias" style="color:#c4a574;text-decoration:none;font-weight:600;">Elígela aquí&nbsp;→</a> '
                'y recibirás cada mañana solo las convocatorias de tu zona (más las de ámbito estatal).')

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>OpoNoticias — {fecha_larga}</title></head>
<body style="margin:0;padding:0;background:#f8f6f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f6f2;">
<tr><td align="center" style="padding:24px 16px 0;">

  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:linear-gradient(135deg,#5a5047,#c4a574);border-radius:14px 14px 0 0;">
  <tr><td style="padding:28px 32px;">
    <div style="color:#fff;font-size:22px;font-family:'Georgia',serif;font-weight:700;">OpoNoticias</div>
    <div style="color:rgba(255,255,255,0.8);font-size:13px;margin-top:4px;">{fecha_larga} · {n} convocatoria{'s' if n != 1 else ''}</div>
  </td></tr>
  </table>

  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-left:1px solid #e7e0d5;border-right:1px solid #e7e0d5;">
  <tr><td style="padding:20px 24px 8px;">
    <p style="margin:0;color:#5a5047;font-size:14px;">Buenos días. Estas son las nuevas convocatorias publicadas hoy en el BOE:</p>
  </td></tr>
  {cuerpo_tabla}
  <tr><td style="padding:20px 24px;">
    <a href="{SITE_URL}" style="display:inline-block;background:#5a5047;color:#fff;text-decoration:none;padding:11px 22px;border-radius:8px;font-size:14px;font-weight:600;">
      Ver todas las oposiciones →
    </a>
  </td></tr>
  <tr><td style="padding:4px 24px 20px;">
    <div style="background:#f8f6f2;border-radius:10px;padding:14px 18px;">
      <p style="margin:0;color:#4a4540;font-size:14px;line-height:1.6;">{pref}</p>
    </div>
  </td></tr>
  </table>

  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#2b2622;border-radius:0 0 14px 14px;">
  <tr><td style="padding:20px 24px;text-align:center;color:rgba(255,255,255,0.5);font-size:12px;line-height:1.7;">
    <a href="{SITE_URL}" style="color:#c4a574;text-decoration:none;">oponoticias.com</a>
    &nbsp;·&nbsp;
    <a href="https://t.me/OPONOTICIAS" style="color:#c4a574;text-decoration:none;">Telegram</a>
    &nbsp;·&nbsp;
    <a href="mailto:info@oponoticias.com" style="color:#c4a574;text-decoration:none;">info@oponoticias.com</a>
    <br>
    Recibiste este correo porque te suscribiste en oponoticias.com
    <br>
    <a href="{unsubscribe_url}" style="color:rgba(255,255,255,0.35);text-decoration:underline;">Darse de baja</a>
  </td></tr>
  </table>

</td></tr>
</table>
</body>
</html>"""


def construir_texto(convocatorias_suyas, comunidad, unsubscribe_url):
    """Versión en texto plano (mejora la entregabilidad y accesibilidad)."""
    fecha_larga = formatear_fecha_larga(HOY)
    lineas = [f"OpoNoticias — {fecha_larga}", ""]
    if convocatorias_suyas:
        lineas.append("Nuevas convocatorias publicadas hoy en el BOE:\n")
        for c in convocatorias_suyas:
            titulo = (c.get("titulo") or "").strip()
            enlace = (c.get("enlace") or "").strip()
            lineas.append(f"• {titulo}\n  {enlace}")
    else:
        lineas.append("Hoy no se han publicado convocatorias de tu comunidad ni de ámbito estatal.")
    lineas += ["", f"Ver todas: {SITE_URL}", "",
               "Recibiste este correo porque te suscribiste en oponoticias.com",
               f"Darse de baja: {unsubscribe_url}"]
    return "\n".join(lineas)


def url_baja(token):
    return f"{SITE_URL}/api/unsubscribe?t={urllib.parse.quote(token or '')}"


# ── Envío por SMTP de Amazon SES ────────────────────────────────────
def construir_mensaje(email, html, texto, unsubscribe_url, asunto):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = formataddr((SENDER_NAME, SENDER_EMAIL))
    msg["To"] = email
    # Baja de 1 clic (obligatoria por RGPD y exigida por Gmail/Yahoo a remitentes
    # masivos). El endpoint /api/unsubscribe debe aceptar GET (clic) y POST (1-clic).
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.attach(MIMEText(texto, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def main():
    print(f"\n📧 [SES] Boletín de {HOY}"
          + ("  (DRY RUN)" if DRY_RUN else "")
          + ("  (TEST)" if TEST_EMAILS else ""))

    convocatorias = obtener_convocatorias_hoy()
    if not convocatorias and not TEST_EMAILS:
        print("  ℹ️  Sin convocatorias hoy — no se envía (evita email vacío).")
        return 0

    # Idempotencia: reclamamos el día insertando la fila. Si ya existe (día ya
    # enviado), Supabase devuelve 409 por la PK y salimos sin reenviar.
    if not DRY_RUN and not TEST_EMAILS:
        status, _ = supabase_write("envios_newsletter", {"fecha": HOY})
        if status == 409:
            print(f"  ⏭️  El boletín de {HOY} ya se envió (idempotencia). No se reenvía.")
            return 0
        if status not in (200, 201):
            print(f"  ⚠️  No se pudo registrar el envío ({status}); abortando por seguridad.")
            return 1

    suscriptores = obtener_suscriptores()
    if not suscriptores:
        print("  ℹ️  No hay suscriptores a los que enviar.")
        return 0

    fecha_larga = formatear_fecha_larga(HOY)
    total_hoy = len(convocatorias)

    # Conexión SMTP (una sola para todo el lote). En DRY_RUN no se abre.
    servidor = None
    if not DRY_RUN:
        if not SES_SMTP_USER or not SES_SMTP_PASS:
            print("  ❌ Faltan SES_SMTP_USER / SES_SMTP_PASS.")
            return 1
        servidor = smtplib.SMTP(SES_SMTP_HOST, SES_SMTP_PORT, timeout=30)
        servidor.starttls(context=ssl.create_default_context())
        servidor.login(SES_SMTP_USER, SES_SMTP_PASS)

    n_ok, n_err = 0, 0
    try:
        for s in suscriptores:
            email = (s.get("email") or "").strip()
            if not email:
                continue
            comunidad = s.get("comunidad") or ""
            suyas = convocatorias_para(comunidad, convocatorias)
            unsub = url_baja(s.get("token_baja"))
            asunto = (f"Oposiciones {fecha_larga}: "
                      f"{len(suyas)} convocatoria{'s' if len(suyas) != 1 else ''} nueva"
                      f"{'s' if len(suyas) != 1 else ''}")
            html  = construir_html(suyas, total_hoy, comunidad, unsub)
            texto = construir_texto(suyas, comunidad, unsub)

            if DRY_RUN:
                print(f"  · [DRY] {email} — {len(suyas)}/{total_hoy} convocatorias "
                      f"(comunidad: '{comunidad or 'todas'}')")
                n_ok += 1
                continue

            try:
                msg = construir_mensaje(email, html, texto, unsub, asunto)
                servidor.sendmail(SENDER_EMAIL, [email], msg.as_string())
                n_ok += 1
                print(f"  ✓ {email} — {len(suyas)}/{total_hoy}")
            except Exception as e:
                n_err += 1
                print(f"  ❌ {email}: {e}")
            time.sleep(SEND_INTERVAL)
    finally:
        if servidor is not None:
            try:
                servidor.quit()
            except Exception:
                pass

    print(f"\n  Resumen: {n_ok} enviados, {n_err} errores.")

    # Actualiza los contadores del día (best-effort; no crítico).
    if not DRY_RUN and not TEST_EMAILS:
        supabase_write("envios_newsletter", {"enviados": n_ok, "errores": n_err},
                       method="PATCH", params={"fecha": f"eq.{HOY}"})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
