"""
enviar_newsletter.py — Envía el boletín diario de OpoNoticias via Brevo.

Lee las convocatorias publicadas HOY en Supabase y manda un email HTML
a todos los suscriptores de la lista configurada.

Variables de entorno requeridas:
  SUPABASE_URL        — URL de tu proyecto Supabase
  SUPABASE_API_KEY    — Clave de servicio (service_role) de Supabase
  BREVO_API_KEY       — API key de Brevo
  BREVO_LIST_ID       — ID numérico de la lista de suscriptores en Brevo
  BREVO_SENDER_EMAIL  — Email remitente (debe estar verificado en Brevo)
  BREVO_SENDER_NAME   — Nombre remitente (ej: "OpoNoticias")
"""

import os
import json
import html as html_lib
import urllib.request
import urllib.parse
from datetime import datetime, date
from email.utils import parsedate_to_datetime

SUPABASE_URL       = os.environ["SUPABASE_URL"]
SUPABASE_API_KEY   = os.environ["SUPABASE_API_KEY"]
BREVO_API_KEY      = os.environ["BREVO_API_KEY"]
BREVO_LIST_ID      = int(os.environ["BREVO_LIST_ID"])
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "info@oponoticias.com")
BREVO_SENDER_NAME  = os.environ.get("BREVO_SENDER_NAME", "OpoNoticias")

HOY = date.today().isoformat()
MESES = ['enero','febrero','marzo','abril','mayo','junio',
         'julio','agosto','septiembre','octubre','noviembre','diciembre']


def formatear_fecha_larga(iso):
    try:
        d = datetime.fromisoformat(iso[:10])
        return f"{d.day} de {MESES[d.month-1]} de {d.year}"
    except Exception:
        return iso[:10]


def supabase_get(endpoint, params):
    qs = urllib.parse.urlencode(params)
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}?{qs}"
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def brevo_post(path, body):
    url = f"https://api.brevo.com/v3/{path}"
    data = json.dumps(body).encode("utf-8")
    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.request.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def brevo_get(path):
    url = f"https://api.brevo.com/v3/{path}"
    headers = {"api-key": BREVO_API_KEY, "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.request.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def campana_de_hoy_ya_existe():
    """True si ya existe en Brevo una campaña 'Newsletter {HOY}'. Idempotencia:
    evita que un segundo disparo del workflow el mismo día reenvíe el correo."""
    nombre = f"Newsletter {HOY}"
    status, data = brevo_get("emailCampaigns?type=classic&sort=desc&limit=100")
    if status not in (200, 201):
        # No se pudo comprobar. El cron ya es único (causa raíz resuelta), así
        # que priorizamos no perder el envío diario y continuamos.
        print(f"  ⚠️  No se pudo comprobar campañas existentes ({status}); continúo.")
        return False
    for c in (data.get("campaigns") or []):
        if (c.get("name") or "") == nombre:
            print(f"  ⏭️  Ya existe la campaña '{nombre}' (estado: {c.get('status')}). "
                  f"No se reenvía (idempotencia).")
            return True
    return False


def obtener_convocatorias_hoy():
    # `fecha` se guarda como string RFC ("Sat, 13 Jun 2026 00:00:00 +0200"),
    # no como ISO, así que no se puede filtrar con eq.{HOY}. Traemos las filas
    # recientes y filtramos en Python comparando la fecha parseada con hoy.
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


def tarjeta_html(c):
    titulo   = html_lib.escape(c.get("titulo", ""))
    enlace   = html_lib.escape(c.get("enlace", "#"))
    cat      = html_lib.escape(c.get("categoria", "") or "")
    ccaa     = html_lib.escape(c.get("comunidad_autonoma", "") or "")

    rc = c.get("resumen_claude") or {}
    if isinstance(rc, str):
        try:
            rc = json.loads(rc)
        except Exception:
            rc = {}
    plazas  = str(rc.get("plazas", "") or "")
    puesto  = html_lib.escape(rc.get("puesto", "") or "")
    resumen = html_lib.escape(rc.get("resumen", "") or "")

    badge_cat  = f'<span style="background:#efe9e0;color:#5a5047;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600;margin-right:6px;">{cat}</span>' if cat else ""
    badge_ccaa = f'<span style="background:#f0f4ee;color:#7a8b6e;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600;">{ccaa}</span>' if ccaa else ""
    badge_plazas = f'<span style="background:#f8f6f2;color:#5a5047;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:700;margin-left:8px;">{plazas} plazas</span>' if plazas else ""

    detalle_html = ""
    if puesto:
        detalle_html += f'<p style="margin:4px 0 0;color:#8b8b7a;font-size:13px;">{puesto}</p>'
    if resumen:
        detalle_html += f'<p style="margin:6px 0 0;color:#4a4540;font-size:13px;line-height:1.5;">{resumen}</p>'

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


def construir_html(convocatorias):
    fecha_larga = formatear_fecha_larga(HOY)
    n = len(convocatorias)

    if not convocatorias:
        cuerpo_tabla = """
        <tr><td style="padding:32px 24px;text-align:center;color:#8b8b7a;">
          Hoy no se han publicado nuevas convocatorias en el BOE.
        </td></tr>"""
    else:
        cuerpo_tabla = "".join(tarjeta_html(c) for c in convocatorias)

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>OpoNoticias — {fecha_larga}</title></head>
<body style="margin:0;padding:0;background:#f8f6f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f6f2;">
<tr><td align="center" style="padding:24px 16px 0;">

  <!-- Cabecera -->
  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:linear-gradient(135deg,#5a5047,#c4a574);border-radius:14px 14px 0 0;">
  <tr><td style="padding:28px 32px;">
    <div style="color:#fff;font-size:22px;font-family:'Georgia',serif;font-weight:700;">OpoNoticias</div>
    <div style="color:rgba(255,255,255,0.8);font-size:13px;margin-top:4px;">{fecha_larga} · {n} convocatoria{'s' if n != 1 else ''} nueva{'s' if n != 1 else ''}</div>
  </td></tr>
  </table>

  <!-- Cuerpo -->
  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-left:1px solid #e7e0d5;border-right:1px solid #e7e0d5;">
  <tr><td style="padding:20px 24px 8px;">
    <p style="margin:0;color:#5a5047;font-size:14px;">Buenos días. Estas son las nuevas convocatorias publicadas hoy en el BOE:</p>
  </td></tr>
  {cuerpo_tabla}
  <tr><td style="padding:20px 24px;">
    <a href="https://oponoticias.com" style="display:inline-block;background:#5a5047;color:#fff;text-decoration:none;padding:11px 22px;border-radius:8px;font-size:14px;font-weight:600;">
      Ver todas las oposiciones →
    </a>
  </td></tr>
  </table>

  <!-- Pie -->
  <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#2b2622;border-radius:0 0 14px 14px;">
  <tr><td style="padding:20px 24px;text-align:center;color:rgba(255,255,255,0.5);font-size:12px;line-height:1.7;">
    <a href="https://oponoticias.com" style="color:#c4a574;text-decoration:none;">oponoticias.com</a>
    &nbsp;·&nbsp;
    <a href="https://t.me/OPONOTICIAS" style="color:#c4a574;text-decoration:none;">Telegram</a>
    &nbsp;·&nbsp;
    <a href="mailto:info@oponoticias.com" style="color:#c4a574;text-decoration:none;">info@oponoticias.com</a>
    <br>
    Recibiste este correo porque te suscribiste en oponoticias.com
    <br>
    <a href="{{{{ params.unsubscribeUrl }}}}" style="color:rgba(255,255,255,0.35);text-decoration:underline;">Darse de baja</a>
  </td></tr>
  </table>

</td></tr>
</table>
</body>
</html>"""


def enviar_campana(convocatorias):
    fecha_larga = formatear_fecha_larga(HOY)
    n = len(convocatorias)
    asunto = f"Oposiciones {fecha_larga}: {n} convocatoria{'s' if n != 1 else ''} nueva{'s' if n != 1 else ''}"
    html_content = construir_html(convocatorias)

    # Crear campaña
    payload = {
        "name": f"Newsletter {HOY}",
        "subject": asunto,
        "sender": {"email": BREVO_SENDER_EMAIL, "name": BREVO_SENDER_NAME},
        "type": "classic",
        "htmlContent": html_content,
        "recipients": {"listIds": [BREVO_LIST_ID]},
    }
    status, resp = brevo_post("emailCampaigns", payload)
    if status not in (201, 200):
        print(f"  ❌ Error creando campaña: {status} — {resp}")
        raise SystemExit(1)

    campaign_id = resp.get("id")
    print(f"  ✓ Campaña creada (id={campaign_id})")

    # Enviar inmediatamente
    status2, resp2 = brevo_post(f"emailCampaigns/{campaign_id}/sendNow", {})
    if status2 not in (204, 200):
        print(f"  ❌ Error enviando campaña: {status2} — {resp2}")
        raise SystemExit(1)

    print(f"  ✅ Campaña enviada a los suscriptores de la lista {BREVO_LIST_ID}")


if __name__ == "__main__":
    print(f"\n📧 Enviando newsletter de {HOY}…")
    convocatorias = obtener_convocatorias_hoy()

    if not convocatorias:
        print("  ℹ️  Sin convocatorias hoy — no se envía newsletter (evita email vacío).")
        raise SystemExit(0)

    if campana_de_hoy_ya_existe():
        raise SystemExit(0)

    enviar_campana(convocatorias)
    print("✅ Newsletter enviada correctamente.")
