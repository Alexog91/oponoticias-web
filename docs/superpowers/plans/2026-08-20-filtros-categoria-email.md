# Filtros comunidad + categoría en el newsletter — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada suscriptor pueda filtrar su correo diario por una categoría de oposiciones, de forma independiente de su comunidad autónoma.

**Architecture:** Se añade una columna `categoria` a `suscriptores`. El envío (`enviar_newsletter_ses.py`) aplica dos filtros independientes con Y lógico (comunidad ya existía; categoría es nuevo). Un selector de categoría se añade a los 3 puntos de captura (home, popup, `/preferencias`) y a sus 2 APIs. Un banner autolimitado por fecha en el newsletter anuncia la novedad. Copys de redes como entregable.

**Tech Stack:** Python 3.11 (smtplib/SES, urllib), funciones serverless Vercel (Node/JS), HTML+JS vanilla, Supabase (Postgres/PostgREST).

## Global Constraints

- Las 8 categorías, EXACTAS (nombre con mayúscula y tildes, como en `convocatorias.categoria`): `Educación`, `Sanidad`, `Justicia`, `Seguridad`, `Administración`, `Hacienda`, `Correos`, `Técnica`.
- `categoria` vacía (`""`/`NULL`) = todas las categorías (sin filtro). Debe preservar el comportamiento actual de los 343 suscriptores.
- La comunidad sigue siendo UNA sola; la categoría, UNA sola. Independientes. NO multi-selección (YAGNI).
- `categoria` del suscriptor guarda el NOMBRE, no el slug.
- El aviso (banner + redes) se publica DESPUÉS de desplegar la función.
- Commits frecuentes; el repo es público (nada de PII ni secretos en commits).

---

### Task 1: Migración — columna `categoria` en `suscriptores`

**Files:**
- Ejecutar SQL en Supabase (SQL Editor). Sin archivo en el repo.

**Interfaces:**
- Produces: columna `suscriptores.categoria TEXT` (nullable), leída/escrita por las tareas siguientes.

- [ ] **Step 1: Ejecutar la migración en Supabase → SQL Editor**

```sql
ALTER TABLE suscriptores ADD COLUMN IF NOT EXISTS categoria TEXT;
```

- [ ] **Step 2: Verificar que la columna existe**

```sql
select column_name from information_schema.columns
where table_name = 'suscriptores' and column_name = 'categoria';
```
Expected: devuelve 1 fila (`categoria`).

(No hay commit: es cambio de esquema en la BD, no en el repo.)

---

### Task 2: Filtro de categoría en el envío (Python, TDD)

**Files:**
- Modify: `enviar_newsletter_ses.py` (`convocatorias_para`, `con_contenido`, `obtener_suscriptores`, constante `TEST_CATEGORIA`)
- Test: `tests/test_newsletter_categoria.py` (nuevo)

**Interfaces:**
- Consumes: `_es_estatal(ccaa)` (ya existe en el módulo).
- Produces: `convocatorias_para(comunidad, categoria, convocatorias) -> list` — filtro comunidad Y categoría, independientes; cada uno no-op si su preferencia está vacía.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_newsletter_categoria.py`:

```python
"""tests/test_newsletter_categoria.py — filtro independiente comunidad + categoría.

Ejecuta:  python3 tests/test_newsletter_categoria.py
"""
import os, sys
from pathlib import Path
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_API_KEY", "x")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import enviar_newsletter_ses as nl  # noqa: E402

CONV = [
    {"titulo": "A", "comunidad_autonoma": "Madrid",           "categoria": "Administración"},
    {"titulo": "B", "comunidad_autonoma": "Madrid",           "categoria": "Sanidad"},
    {"titulo": "C", "comunidad_autonoma": "Galicia",          "categoria": "Administración"},
    {"titulo": "D", "comunidad_autonoma": "Nacional/Estatal", "categoria": "Administración"},
    {"titulo": "E", "comunidad_autonoma": "Nacional/Estatal", "categoria": "Sanidad"},
    {"titulo": "F", "comunidad_autonoma": "Madrid",           "categoria": None},
]
def titulos(comunidad, categoria):
    return sorted(c["titulo"] for c in nl.convocatorias_para(comunidad, categoria, CONV))

casos = []
test = lambda n, f: casos.append((n, f))  # noqa: E731

# Sin filtros → todo (comportamiento actual de los 343 subs)
test("sin comunidad ni categoría → todo", lambda: titulos("", "") == ["A","B","C","D","E","F"])
# Solo comunidad → su comunidad + estatales (comportamiento actual)
test("solo Madrid → Madrid + estatales", lambda: titulos("Madrid", "") == ["A","B","D","E","F"])
# Solo categoría → esa categoría de toda España (incl. estatales de esa categoría)
test("solo Administración → todas las de Administración", lambda: titulos("", "Administración") == ["A","C","D"])
# Comunidad + categoría → (comunidad O estatal) Y categoría
test("Madrid + Administración", lambda: titulos("Madrid", "Administración") == ["A","D"])
test("Galicia + Sanidad → solo estatal de Sanidad", lambda: titulos("Galicia", "Sanidad") == ["E"])
# Convocatoria con categoría None NO llega a quien filtró por categoría
test("categoría None excluida al filtrar por categoría", lambda: "F" not in titulos("Madrid", "Administración"))
# Estatal como comunidad del suscriptor → ve todo (categoría vacía)
test("suscriptor estatal → todo", lambda: titulos("Nacional/Estatal", "") == ["A","B","C","D","E","F"])

if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try: ok = fn()
        except Exception as e: ok, nombre = False, f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}"); fallos += not ok
    print("─"*58); print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
```

- [ ] **Step 2: Ejecutar el test y ver que falla**

Run: `python3 tests/test_newsletter_categoria.py`
Expected: FALLA — `convocatorias_para()` aún recibe 2 args (`comunidad, convocatorias`), no 3.

- [ ] **Step 3: Cambiar `convocatorias_para` a filtro doble independiente**

En `enviar_newsletter_ses.py`, reemplazar la función actual:

```python
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
```

por:

```python
def convocatorias_para(comunidad, categoria, convocatorias):
    """Convocatorias que le tocan a un suscriptor. DOS filtros independientes con
    Y lógico; cada uno es no-op si su preferencia está vacía:
    - Comunidad: vacía/estatal → todas; si no → las de su CCAA + las estatales.
    - Categoría: vacía → todas; si no → solo las de esa categoría (nombre exacto)."""
    cat = (categoria or "").strip()
    objetivo = (comunidad or "").strip()

    def pasa_comunidad(c):
        if _es_estatal(comunidad):
            return True
        return (_es_estatal(c.get("comunidad_autonoma"))
                or (c.get("comunidad_autonoma") or "").strip() == objetivo)

    def pasa_categoria(c):
        if not cat:
            return True
        return (c.get("categoria") or "").strip() == cat

    return [c for c in convocatorias if pasa_comunidad(c) and pasa_categoria(c)]
```

- [ ] **Step 4: Actualizar la llamada en `con_contenido`**

Cambiar (línea ~160):

```python
        suyas = convocatorias_para(s.get("comunidad") or "", convocatorias)
```
por:
```python
        suyas = convocatorias_para(s.get("comunidad") or "", s.get("categoria") or "", convocatorias)
```

- [ ] **Step 5: Que `obtener_suscriptores` traiga `categoria`**

En `obtener_suscriptores`, cambiar el `select` y el modo TEST:

```python
    if TEST_EMAILS:
        print(f"  🧪 Modo prueba: {len(TEST_EMAILS)} destinatario(s) de TEST_EMAILS "
              f"(comunidad simulada: '{TEST_COMUNIDAD or 'todas'}')")
        return [{"email": e, "comunidad": TEST_COMUNIDAD, "categoria": TEST_CATEGORIA, "token_baja": "test"}
                for e in TEST_EMAILS]
    subs = supabase_get("suscriptores", {
        "select": "email,comunidad,categoria,token_baja",
        "estado": "eq.activo",
        "order": "id",
    })
```

Y añadir la constante junto a `TEST_COMUNIDAD` (línea ~66):

```python
TEST_CATEGORIA = os.environ.get("TEST_CATEGORIA", "")
```

- [ ] **Step 6: Ejecutar el test y ver que pasa**

Run: `python3 tests/test_newsletter_categoria.py`
Expected: `TODO OK`

- [ ] **Step 7: Ejecutar toda la suite (no romper nada)**

Run: `for t in tests/test_*.py; do python3 "$t" >/dev/null 2>&1 && echo "OK $t" || echo "FALLA $t"; done`
Expected: todos OK.

- [ ] **Step 8: Commit**

```bash
git add enviar_newsletter_ses.py tests/test_newsletter_categoria.py
git commit -m "feat(newsletter): filtro de categoría independiente de la comunidad"
```

---

### Task 3: Banner de aviso en el newsletter (autolimitado por fecha)

**Files:**
- Modify: `enviar_newsletter_ses.py` (`construir_html`, nueva constante `AVISO_CATEGORIA_HASTA`)

**Interfaces:**
- Consumes: `HOY` (date del módulo), `date` (importado).

- [ ] **Step 1: Añadir la constante de fecha límite** (junto a las demás constantes, ~línea 66)

```python
# El banner de "novedad: filtro por categoría" se muestra en el newsletter hasta
# esta fecha (incl.) y luego desaparece solo. Poner la fecha del despliegue + ~1 semana.
AVISO_CATEGORIA_HASTA = os.environ.get("AVISO_CATEGORIA_HASTA", "2026-08-27")
```

- [ ] **Step 2: Insertar el banner en `construir_html`**

En `construir_html`, justo después de `n = len(convocatorias_suyas)`, añadir:

```python
    aviso_cat = ""
    if HOY.isoformat() <= AVISO_CATEGORIA_HASTA:
        aviso_cat = (
            '<tr><td style="padding:0 0 16px;">'
            '<div style="background:#f4efe6;border:1px solid #e6ddcb;border-radius:10px;'
            'padding:14px 16px;font-size:14px;color:#5a5047;">'
            '📢 <strong>Novedad:</strong> ahora puedes recibir en el correo solo tu '
            '<strong>comunidad</strong> y/o tu <strong>categoría</strong> '
            '(Administración, Sanidad, Educación…). '
            '<a href="https://oponoticias.com/preferencias" '
            'style="color:#c4a574;font-weight:600;text-decoration:none;">Ajusta tus preferencias&nbsp;→</a>'
            '</div></td></tr>'
        )
```

Luego, en el HTML devuelto por la función, insertar `{aviso_cat}` como primera fila de la tabla del cuerpo (antes de `{cuerpo_tabla}`). Localizar en el `return` la tabla que contiene `{cuerpo_tabla}` y anteponer `{aviso_cat}` en esa misma tabla.

- [ ] **Step 3: Verificar que el banner se genera/oculta según la fecha**

Run:
```bash
python3 -c "
import os
os.environ['SUPABASE_URL']='http://x'; os.environ['SUPABASE_API_KEY']='x'
os.environ['AVISO_CATEGORIA_HASTA']='2099-01-01'
import enviar_newsletter_ses as nl
h = nl.construir_html([], 0, '', 'http://u')
print('CON aviso:', 'Novedad' in h)
os.environ['AVISO_CATEGORIA_HASTA']='2000-01-01'
import importlib; importlib.reload(nl)
h2 = nl.construir_html([], 0, '', 'http://u')
print('SIN aviso:', 'Novedad' not in h2)
"
```
Expected: `CON aviso: True` y `SIN aviso: True`.

- [ ] **Step 4: Commit**

```bash
git add enviar_newsletter_ses.py
git commit -m "feat(newsletter): banner de aviso de la nueva preferencia de categoría (autolimitado)"
```

---

### Task 4: API de alta — `api/subscribe.js` acepta `categoria`

**Files:**
- Modify: `api/subscribe.js` (lectura del body, validación, upsert, texto del email de bienvenida)

**Interfaces:**
- Consumes: columna `suscriptores.categoria` (Task 1).

- [ ] **Step 1: Añadir la whitelist de categorías** (arriba del handler)

```javascript
const CATEGORIAS = new Set([
  'Educación', 'Sanidad', 'Justicia', 'Seguridad',
  'Administración', 'Hacienda', 'Correos', 'Técnica',
]);
```

- [ ] **Step 2: Leer y validar `categoria` del body**

Donde se hace `const { email, material, comunidad } = req.body || {};`, cambiar a incluir `categoria`, y tras el saneado de `com`:

```javascript
  const { email, material, comunidad, categoria } = req.body || {};
  // ... (validación de email y com existentes) ...
  const cat = (typeof categoria === 'string' && CATEGORIAS.has(categoria.trim()))
    ? categoria.trim() : '';
```

- [ ] **Step 3: Guardar `categoria` en el upsert solo si viene**

En el objeto de campos del upsert, junto a `...(com ? { comunidad: com } : {})`, añadir:

```javascript
    ...(cat ? { categoria: cat } : {}),
```

- [ ] **Step 4: Cambiar el enlace del email de bienvenida**

En `emailBienvenidaHtml`, cambiar el texto del enlace de `Elegir comunidad&nbsp;→` por `Elegir preferencias&nbsp;→` (misma URL `/preferencias`).

- [ ] **Step 5: Verificar sintaxis**

Run: `node --check api/subscribe.js`
Expected: sin salida (OK).

- [ ] **Step 6: Commit**

```bash
git add api/subscribe.js
git commit -m "feat(api): subscribe acepta y valida categoria; email de bienvenida enlaza a preferencias"
```

---

### Task 5: API de preferencias — `api/preferencias.js` acepta `categoria`

**Files:**
- Modify: `api/preferencias.js` (whitelist, lectura, upsert que permite limpiar)

**Interfaces:**
- Consumes: columna `suscriptores.categoria`.
- Nota: a diferencia del alta, aquí se DEBE poder poner `""` para volver a "todas" (limpiar). Solo se escribe `categoria` si la clave viene en el body (una página vieja que no la manda no la pisa).

- [ ] **Step 1: Añadir la whitelist de categorías** (junto a `COMUNIDADES`)

```javascript
const CATEGORIAS = new Set([
  'Educación', 'Sanidad', 'Justicia', 'Seguridad',
  'Administración', 'Hacienda', 'Correos', 'Técnica',
]);
```

- [ ] **Step 2: Leer `categoria`, validar y construir el upsert que permite limpiar**

Donde hoy hace `const { email, comunidad } = req.body || {};` y el upsert de comunidad, ampliar para incluir `categoria` cuando venga en el body:

```javascript
  const { email, comunidad, categoria } = req.body || {};
  // ... validación de email + comunidad existentes ...
  const fila = { email, comunidad };            // comunidad se escribe siempre (permite limpiar)
  if ('categoria' in (req.body || {})) {         // solo si el cliente la manda
    // "" = limpiar (todas); nombre válido = filtrar; valor desconocido = "" (limpiar)
    const c = typeof categoria === 'string' ? categoria.trim() : '';
    fila.categoria = CATEGORIAS.has(c) ? c : '';
  }
  await supabaseUpsert('suscriptores', [fila]);
```

(Adaptar a la forma exacta del upsert actual del archivo — la clave es: `categoria` se incluye solo si viene en el body, y `""` limpia.)

- [ ] **Step 3: Verificar sintaxis**

Run: `node --check api/preferencias.js`
Expected: sin salida (OK).

- [ ] **Step 4: Commit**

```bash
git add api/preferencias.js
git commit -m "feat(api): preferencias acepta categoria (permite elegir y limpiar el filtro)"
```

---

### Task 6: Selector de categoría en el formulario de la home (`index.html`)

**Files:**
- Modify: `index.html` (`#newsletterFormHome`: nuevo `<select id="newsletterCategoria">`; handler inline JS que manda `categoria`)

- [ ] **Step 1: Añadir el `<select>` de categoría bajo el de comunidad**

Justo después del `<select id="newsletterComunidad" ...>...</select>` (dentro de `#newsletterFormHome`), añadir:

```html
              <select id="newsletterCategoria" name="categoria" aria-label="Categoría (opcional)" style="width:100%;margin-top:10px;padding:12px 14px;border:1.5px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font-family:var(--sans);font-size:0.95rem;">
                <option value="">Categoría (opcional) — todas</option>
                <option>Educación</option>
                <option>Sanidad</option>
                <option>Justicia</option>
                <option>Seguridad</option>
                <option>Administración</option>
                <option>Hacienda</option>
                <option>Correos</option>
                <option>Técnica</option>
              </select>
```

- [ ] **Step 2: Que el handler inline mande `categoria`**

En el JS inline de `index.html` que gestiona `#newsletterFormHome` (donde lee `newsletterComunidad`), leer también la categoría y añadirla al body del POST:

```javascript
        var catSel = document.getElementById('newsletterCategoria');
        var categoria = catSel ? catSel.value : '';
```
y en el `JSON.stringify({ ... })` del `/api/subscribe`, añadir `categoria: categoria`.

- [ ] **Step 3: Verificar en el navegador (preview)**

Servir la web y comprobar que el selector aparece y que al enviar, la petición a `/api/subscribe` incluye `categoria`. (read_network_requests / DevTools.)

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(web): selector de categoría en el formulario de suscripción de la home"
```

---

### Task 7: Selector de categoría en el popup (`assets/script.js`)

**Files:**
- Modify: `assets/script.js` (popup: `<select id="nlPopCategoria">` en el HTML generado + handler que manda `categoria`)

- [ ] **Step 1: Añadir el `<select>` de categoría tras `#nlPopComunidad`**

En la cadena HTML del popup (donde se construye `#nlPopComunidad`), añadir tras ese `</select>`:

```javascript
            '<select id="nlPopCategoria" name="categoria" aria-label="Categoría (opcional)" style="width:100%;margin-top:10px;padding:12px 14px;border:1.5px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);font-family:var(--sans);font-size:0.95rem;">' +
              '<option value="">Categoría (opcional) — todas</option>' +
              '<option>Educación</option><option>Sanidad</option><option>Justicia</option>' +
              '<option>Seguridad</option><option>Administración</option><option>Hacienda</option>' +
              '<option>Correos</option><option>Técnica</option>' +
            '</select>' +
```

- [ ] **Step 2: Que el handler del popup mande `categoria`**

Donde lee `var comunidad = comSel ? comSel.value : '';`, añadir:

```javascript
      var catSel = document.getElementById('nlPopCategoria');
      var categoria = catSel ? catSel.value : '';
```
y añadir `categoria: categoria` al `JSON.stringify({...})` del POST a `/api/subscribe`.

- [ ] **Step 3: Verificar en el navegador**

Abrir la web, forzar el popup, comprobar el selector y que la petición incluye `categoria`.

- [ ] **Step 4: Commit**

```bash
git add assets/script.js
git commit -m "feat(web): selector de categoría en el popup de suscripción"
```

---

### Task 8: Selector de categoría en `/preferencias`

**Files:**
- Modify: `preferencias.html` (`<select id="prefCat">`, JS que manda `categoria`, renombrar título/H1)

- [ ] **Step 1: Renombrar la página a "preferencias"**

Cambiar `<title>Elige tu comunidad — OpoNoticias</title>` → `<title>Elige tus preferencias — OpoNoticias</title>`, el `<h1>Elige tu comunidad</h1>` → `<h1>Elige tus preferencias</h1>`, y adaptar el `<p class="lead">` para mencionar comunidad y categoría.

- [ ] **Step 2: Añadir el `<select>` de categoría tras el de comunidad (`#prefCom`)**

```html
            <select id="prefCat" class="pref-select" style="margin-top:12px;">
              <option value="">Todas las categorías</option>
              <option>Educación</option>
              <option>Sanidad</option>
              <option>Justicia</option>
              <option>Seguridad</option>
              <option>Administración</option>
              <option>Hacienda</option>
              <option>Correos</option>
              <option>Técnica</option>
            </select>
```

- [ ] **Step 3: Que el JS de la página mande `categoria` a `/api/preferencias`**

En el `fetch('/api/preferencias', ...)` de `preferencias.html`, leer `document.getElementById('prefCat').value` y añadir `categoria` al body JSON (junto a `comunidad`). Así el POST siempre incluye la clave `categoria` (permite limpiar eligiendo "Todas").

- [ ] **Step 4: Verificar en el navegador**

Abrir `/preferencias?e=test@x.com`, comprobar los dos selectores y que el guardado manda ambos.

- [ ] **Step 5: Commit**

```bash
git add preferencias.html
git commit -m "feat(web): pagina de preferencias con selector de categoria + renombrada"
```

---

### Task 9: Copys del aviso para redes sociales (entregable)

**Files:**
- Create: `docs/avisos/2026-08-aviso-filtro-categoria.md` (copys por red, listos para copiar/pegar)

**Interfaces:**
- Se publican MANUALMENTE por el usuario, DESPUÉS de que las Tasks 1-8 estén desplegadas y verificadas.

- [ ] **Step 1: Escribir los copys por red**

Crear `docs/avisos/2026-08-aviso-filtro-categoria.md` con un copy para Telegram, Facebook, Instagram y X. Cada uno: anuncia que ahora el correo diario se puede filtrar por comunidad y/o categoría, con enlace a `oponoticias.com/preferencias`, adaptado al tono/longitud de cada red. (Contenido real, no placeholder — ver spec §5.)

- [ ] **Step 2: Commit**

```bash
git add docs/avisos/2026-08-aviso-filtro-categoria.md
git commit -m "docs: copys del aviso de la nueva preferencia de categoria para redes"
```

---

## Orden de despliegue y verificación final

1. Task 1 (migración) primero.
2. Tasks 2-8 (código) — se despliegan solas (Vercel en push; el newsletter lo recoge el cron).
3. Verificar en vivo: alta con categoría, `/preferencias` guarda categoría, y un envío de prueba del newsletter con `TEST_EMAILS` + `TEST_CATEGORIA` (workflow_dispatch del newsletter en modo test) segmenta bien.
4. Solo entonces: publicar los copys (Task 9) y dejar el banner activo hasta `AVISO_CATEGORIA_HASTA`.

## Notas de verificación (spec coverage)

- Filtro independiente (4 combinaciones + estatales + categoría None): Task 2 tests.
- Migración nula / no romper a los 343: Task 2 (test "sin filtros → todo") + `categoria` opcional en APIs.
- Limpiar el filtro (volver a todas): Task 5 (preferencias escribe `""`).
- Aviso: Task 3 (banner newsletter) + Task 9 (redes).
