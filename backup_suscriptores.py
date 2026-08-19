#!/usr/bin/env python3
"""backup_suscriptores.py — Copia de seguridad de la tabla `suscriptores`.

Exporta TODA la tabla `suscriptores` de Supabase a un CSV y lo envía por Amazon
SES (SMTP) al buzón de backup (por defecto info@oponoticias.com, en Proton). Es
la copia de lo ÚNICO irremplazable del negocio: los emails no se reconstruyen si
Supabase se corrompe o se pierde la cuenta (las convocatorias se recuperan del
BOE y el blog está en GitHub). Ver docs/CONTINUIDAD.md.

Pensado para correr semanalmente en GitHub Actions (backup-suscriptores.yml).

Requiere:  SUPABASE_URL, SUPABASE_API_KEY (la service_role, que lee saltándose el
           RLS), SES_SMTP_USER, SES_SMTP_PASS.
Opcionales: SES_SMTP_HOST (email-smtp.eu-west-1.amazonaws.com), SES_SMTP_PORT
           (587), SENDER_EMAIL (info@oponoticias.com), BACKUP_EMAIL (idem),
           DRY_RUN=1 (genera el CSV pero NO envía; imprime un resumen).
"""

import os
import io
import csv
import ssl
import sys
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import newsletter_utils

SUPABASE_URL     = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_API_KEY = os.environ.get("SUPABASE_API_KEY", "")

SES_SMTP_HOST = os.environ.get("SES_SMTP_HOST", "email-smtp.eu-west-1.amazonaws.com")
SES_SMTP_PORT = int(os.environ.get("SES_SMTP_PORT", "587"))
SES_SMTP_USER = os.environ.get("SES_SMTP_USER", "")
SES_SMTP_PASS = os.environ.get("SES_SMTP_PASS", "")

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "info@oponoticias.com")
SENDER_NAME  = os.environ.get("SENDER_NAME", "OpoNoticias")
BACKUP_EMAIL = os.environ.get("BACKUP_EMAIL", "info@oponoticias.com")
DRY_RUN      = os.environ.get("DRY_RUN", "") not in ("", "0", "false", "False")


def obtener_suscriptores():
    """Toda la tabla `suscriptores` (paginada; el helper respeta el tope de 1.000
    por petición de Supabase)."""
    return newsletter_utils.supabase_get(
        SUPABASE_URL, SUPABASE_API_KEY, "suscriptores",
        {"select": "*", "order": "id"})


def a_csv(filas):
    """Devuelve (csv_texto, n_filas). Cabecera = unión de claves de todas las
    filas, en orden de aparición (estable)."""
    if not filas:
        return "", 0
    cols = []
    for f in filas:
        for k in f.keys():
            if k not in cols:
                cols.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for f in filas:
        w.writerow(f)
    return buf.getvalue(), len(filas)


def enviar(csv_texto, n, n_activos):
    hoy = datetime.now().strftime("%Y-%m-%d")
    nombre_csv = f"suscriptores-{hoy}.csv"
    msg = MIMEMultipart()
    msg["From"] = formataddr((SENDER_NAME, SENDER_EMAIL))
    msg["To"] = BACKUP_EMAIL
    msg["Subject"] = f"[Backup] Suscriptores OpoNoticias {hoy} — {n} filas ({n_activos} activos)"
    cuerpo = (
        "Copia de seguridad automática de la tabla `suscriptores` de Supabase.\n\n"
        f"Fecha: {hoy}\n"
        f"Total filas: {n}\n"
        f"Activos: {n_activos}\n\n"
        f"Adjunto: {nombre_csv}\n\n"
        "Guárdalo en un sitio seguro (es la única copia fuera de Supabase de los\n"
        "emails de tus suscriptores, que no se pueden reconstruir). Ver\n"
        "docs/CONTINUIDAD.md.\n"
    )
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))
    adj = MIMEApplication(csv_texto.encode("utf-8"), _subtype="csv")
    adj.add_header("Content-Disposition", "attachment", filename=nombre_csv)
    msg.attach(adj)

    servidor = smtplib.SMTP(SES_SMTP_HOST, SES_SMTP_PORT, timeout=30)
    try:
        servidor.starttls(context=ssl.create_default_context())
        servidor.login(SES_SMTP_USER, SES_SMTP_PASS)
        servidor.sendmail(SENDER_EMAIL, [BACKUP_EMAIL], msg.as_string())
    finally:
        servidor.quit()


def main():
    if not (SUPABASE_URL and SUPABASE_API_KEY):
        print("❌ Faltan SUPABASE_URL / SUPABASE_API_KEY")
        raise SystemExit(1)

    filas = obtener_suscriptores()
    csv_texto, n = a_csv(filas)

    # 0 filas casi con seguridad es un fallo de lectura (hay cientos de
    # suscriptores), no un backup válido → fallar para que se note.
    if n == 0:
        print("❌ 0 suscriptores leídos — no se envía (probable fallo de lectura/credenciales).")
        raise SystemExit(1)

    n_activos = sum(1 for f in filas if (f.get("estado") == "activo"))

    if DRY_RUN:
        print(f"🧪 DRY_RUN: {n} filas ({n_activos} activos). CSV generado ({len(csv_texto)} bytes). NO se envía.")
        return

    if not (SES_SMTP_USER and SES_SMTP_PASS):
        print("❌ Faltan SES_SMTP_USER / SES_SMTP_PASS")
        raise SystemExit(1)

    enviar(csv_texto, n, n_activos)
    print(f"✅ Backup enviado a {BACKUP_EMAIL}: {n} filas ({n_activos} activos)")


if __name__ == "__main__":
    main()
