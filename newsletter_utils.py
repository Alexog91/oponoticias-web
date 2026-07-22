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


# Tope de filas por petición del Data API de Supabase ("Max rows", verificado
# en el panel del proyecto). Paginamos con este tamaño de página.
SUPABASE_MAX_ROWS = 1000


def _descargar(url, supabase_api_key):
    headers = {
        "apikey": supabase_api_key,
        "Authorization": f"Bearer {supabase_api_key}",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def supabase_get(supabase_url, supabase_api_key, endpoint, params, _fetch=None):
    """GET a PostgREST trayendo TODAS las filas, paginando si hace falta.

    Supabase corta cada respuesta en `SUPABASE_MAX_ROWS` filas. Sin paginar, el
    día que haya más de 1.000 suscriptores activos la newsletter dejaría de
    llegarle al resto **sin dar ningún error** — el mismo fallo silencioso que
    ya ocurrió con Brevo. Si el llamante pasa su propio `limit`, se respeta como
    número TOTAL de filas que quiere (p. ej. las 150 convocatorias recientes).

    `_fetch` se inyecta en los tests para no depender de la red.
    """
    fetch = _fetch or (lambda url: _descargar(url, supabase_api_key))
    base = dict(params)
    tope = int(base.pop("limit", 0) or 0) or None

    filas, offset = [], 0
    while True:
        pedir = SUPABASE_MAX_ROWS if tope is None else min(SUPABASE_MAX_ROWS, tope - len(filas))
        qs = urllib.parse.urlencode({**base, "limit": str(pedir), "offset": str(offset)})
        lote = fetch(f"{supabase_url}/rest/v1/{endpoint}?{qs}")
        filas.extend(lote)
        # Menos filas de las pedidas = se acabaron; si no, puede haber más página.
        if len(lote) < pedir or (tope is not None and len(filas) >= tope):
            return filas
        # Postgres no garantiza el mismo orden entre peticiones: sin ORDER BY,
        # al pasar de página se pueden repetir unas filas y perderse otras.
        if "order" not in base:
            print(f"  ⚠️  {endpoint}: paginando SIN 'order' — el resultado puede "
                  f"traer filas repetidas y perder otras. Añade order=id.")
        offset += len(lote)
