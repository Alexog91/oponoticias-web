"""
migrar_comunidad.py — Clasifica la COMUNIDAD AUTÓNOMA de cada convocatoria existente.

Recorre los registros de Supabase sin comunidad asignada, pregunta a Claude a qué
comunidad pertenece (a partir del título y del resumen) y guarda el resultado en la
columna `comunidad_autonoma`.

Requisito previo: ejecutar crear_columna_comunidad.sql en Supabase.

Coste estimado: ~0,05 € (claude-haiku, una línea por registro).

Uso:
  SUPABASE_URL=... SUPABASE_API_KEY=<service_role> ANTHROPIC_API_KEY=... python3 migrar_comunidad.py
"""

import urllib.request
import urllib.error
import json
import os
import time

SUPABASE_URL      = os.environ.get("SUPABASE_URL", "")
SUPABASE_API_KEY  = os.environ.get("SUPABASE_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Lista cerrada de respuestas válidas (debe coincidir con ORDEN_CA del frontend)
COMUNIDADES = [
    "Andalucía", "Aragón", "Asturias", "Baleares", "Canarias", "Cantabria",
    "Castilla-La Mancha", "Castilla y León", "Cataluña", "Comunidad Valenciana",
    "Extremadura", "Galicia", "La Rioja", "Madrid", "Murcia", "Navarra",
    "País Vasco", "Ceuta", "Melilla", "Nacional/Estatal",
]
VALIDAS = {c.lower(): c for c in COMUNIDADES}


def clasificar_comunidad(titulo, resumen):
    """Pregunta a Claude la comunidad autónoma. Devuelve una de COMUNIDADES o None."""
    prompt = f"""Convocatoria de oposición (BOE):
Título: {titulo}
Resumen: {resumen}

¿A qué comunidad autónoma de España corresponde el organismo convocante?

Responde ÚNICAMENTE con uno de estos valores EXACTOS, sin nada más:
{", ".join(COMUNIDADES)}

Reglas:
- Ayuntamientos, diputaciones y organismos locales → la comunidad de ese municipio/provincia.
- Juntas, gobiernos y consejerías autonómicas → su comunidad.
- Ministerios, INGESA, Guardia Civil, Policía Nacional, Administración General del Estado,
  agencias estatales, universidades de ámbito estatal → Nacional/Estatal.
- Si no puedes determinarla con seguridad, responde: DESCONOCIDA"""

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    data = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 20,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'),
                                     headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        texto = result['content'][0]['text'].strip()
        # Normalizar a un valor válido
        return VALIDAS.get(texto.lower())   # None si DESCONOCIDA o no reconocido
    except Exception as e:
        print(f"  ⚠️  Error Claude: {e}")
        return None


def obtener_sin_comunidad():
    url = (f"{SUPABASE_URL}/rest/v1/convocatorias"
           f"?select=id,titulo,resumen,resumen_claude&comunidad_autonoma=is.null"
           f"&order=id.asc&limit=1000")
    headers = {'apikey': SUPABASE_API_KEY, 'Authorization': f'Bearer {SUPABASE_API_KEY}'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def actualizar(id_reg, comunidad):
    url = f"{SUPABASE_URL}/rest/v1/convocatorias?id=eq.{id_reg}"
    headers = {
        'apikey': SUPABASE_API_KEY,
        'Authorization': f'Bearer {SUPABASE_API_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }
    data = json.dumps({'comunidad_autonoma': comunidad}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='PATCH')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"  ❌ Error Supabase id={id_reg}: {e}")
        return False


if __name__ == "__main__":
    if not all([SUPABASE_URL, SUPABASE_API_KEY, ANTHROPIC_API_KEY]):
        print("❌ Faltan variables: SUPABASE_URL, SUPABASE_API_KEY, ANTHROPIC_API_KEY")
        raise SystemExit(1)

    print("🔄 Obteniendo registros sin comunidad...")
    registros = obtener_sin_comunidad()
    total = len(registros)
    print(f"✓ A procesar: {total}\n")

    ok = sin_det = errores = 0
    for i, reg in enumerate(registros):
        # Damos a Claude el resumen_claude (lugar) y, si no, el resumen normal
        contexto = reg.get('resumen_claude') or reg.get('resumen') or ''
        ca = clasificar_comunidad(reg['titulo'], contexto)

        etiqueta = ca if ca else "— (sin determinar, se infiere en web)"
        print(f"[{i+1}/{total}] {reg['titulo'][:55]}… → {etiqueta}")

        if ca:
            if actualizar(reg['id'], ca):
                ok += 1
            else:
                errores += 1
        else:
            sin_det += 1   # se deja en null: el frontend la infiere

        if i < total - 1:
            time.sleep(1)
        if (i + 1) % 50 == 0:
            print(f"\n  ── Checkpoint {i+1}/{total} ({ok} OK, {sin_det} sin det., {errores} err) ──\n")

    print(f"\n✅ COMPLETADO  ·  asignadas: {ok}  ·  sin determinar: {sin_det}  ·  errores: {errores}")
