"""
newsletter_utils.py — Helpers compartidos por los motores de newsletter.

Usado por enviar_newsletter_ses.py (Amazon SES, en construcción). NO lo
importa enviar_newsletter.py (Brevo, producción) a propósito: ese script se
deja intacto mientras siga siendo el canal oficial (ver docs/PLAN-EMAIL-SES.md)
— cuando llegue el corte, quedará solo esta versión y la duplicación
desaparece sola.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
         'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def formatear_fecha_larga(iso):
    try:
        d = datetime.fromisoformat(iso[:10])
        return f"{d.day} de {MESES[d.month-1]} de {d.year}"
    except Exception:
        return iso[:10]


def supabase_get(supabase_url, supabase_api_key, endpoint, params):
    qs = urllib.parse.urlencode(params)
    url = f"{supabase_url}/rest/v1/{endpoint}?{qs}"
    headers = {
        "apikey": supabase_api_key,
        "Authorization": f"Bearer {supabase_api_key}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())
