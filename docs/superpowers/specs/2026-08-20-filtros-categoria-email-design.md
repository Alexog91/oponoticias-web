# Filtros independientes de comunidad + categoría en el newsletter

**Fecha:** 2026-08-20
**Origen:** un suscriptor (Moisés) pidió por email poder filtrar por "administrativo /
auxiliar administrativo". Hoy el correo diario solo se puede segmentar por
**comunidad autónoma**; se añade un segundo filtro **independiente por categoría**.

## Objetivo

Que cada suscriptor pueda elegir, de forma independiente:
- su **comunidad autónoma** (ya existe), y
- **una categoría** de oposiciones (nuevo): Educación, Sanidad, Justicia, Seguridad,
  Administración, Hacienda, Correos, Técnica.

Los dos filtros son independientes: se puede elegir solo comunidad, solo categoría,
ambos, o ninguno.

## Alcance (alto nivel)

1. Columna `categoria` en la tabla `suscriptores`.
2. Lógica de envío: filtro de categoría independiente del de comunidad.
3. Selector de categoría en los **tres** puntos de captura: formulario de la home,
   popup de suscripción, y página `/preferencias`.
4. APIs `subscribe.js` y `preferencias.js` aceptan y validan `categoria`.
5. Aviso a los suscriptores de la novedad (redes sociales + email).

## 1. Modelo de datos

Añadir a `suscriptores` una columna:

```sql
ALTER TABLE suscriptores ADD COLUMN IF NOT EXISTS categoria TEXT;
```

- Nullable. `NULL` o `""` = **todas las categorías** (sin filtro).
- Guarda el **nombre** de la categoría tal cual aparece en `convocatorias.categoria`
  (`'Administración'`, `'Sanidad'`, …), NO el slug. Verificado: `convocatorias.categoria`
  guarda el nombre con mayúscula y tildes.
- Independiente de `comunidad`.

**Migración:** ninguna. Los 343 suscriptores actuales quedan con `categoria = NULL`
→ "todas" → su comportamiento **no cambia**.

## 2. Lógica de envío (`enviar_newsletter_ses.py`)

En `convocatorias_para(suscriptor, convocatorias)` se aplican **dos filtros
independientes unidos por Y lógico**; cada filtro es un no-op si su preferencia está
vacía. La firma cambia de `convocatorias_para(comunidad, convocatorias)` a recibir el
suscriptor completo (o comunidad + categoria) para leer ambas preferencias.

**Filtro de comunidad** (sin cambios respecto a hoy):
- `comunidad` vacía o estatal → pasa **todo**.
- `comunidad = X` → pasan las convocatorias con `comunidad_autonoma == X` **o**
  estatales (`_es_estatal`).

**Filtro de categoría** (nuevo):
- `categoria` vacía → pasa **todo**.
- `categoria = C` → pasan solo las convocatorias con `categoria == C`.

Una convocatoria se envía al suscriptor **si pasa AMBOS filtros**.

| Comunidad | Categoría | Recibe |
|---|---|---|
| Madrid | (ninguna) | Madrid + estatales, cualquier categoría *(comportamiento actual)* |
| (ninguna) | Administración | Administración de toda España (incl. estatales de Administración) |
| Madrid | Administración | (Madrid **o** estatal) **y** Administración |
| (ninguna) | (ninguna) | Todo *(comportamiento actual)* |

**Casos borde:**
- Convocatoria con `categoria` NULL/"" → un suscriptor que haya elegido una categoría
  concreta **no** la recibe. Aceptable: `extraer_cuerpo` asigna categoría a casi todas;
  el filtro de categoría es opt-in.
- La guarda `con_contenido` (no enviar correo si el suscriptor no tiene nada hoy) sigue
  igual: ahora puede saltar también porque su **categoría** no tuvo nada hoy. Correcto:
  evita correos vacíos (protege la tasa de quejas de SES).

**Nota de producto (expectativas):** ~95% de las convocatorias diarias del BOE son de
`Administración` (ayuntamientos/diputaciones). El filtro de categoría sirve sobre todo
para **estrechar a un nicho** (p. ej. un sanitario que solo quiere Sanidad se quita el
ruido administrativo). Quien elija Administración seguirá recibiendo casi todo — que es
justo lo que pidió Moisés. Categorías raras (Correos, Hacienda) recibirán pocos correos.

## 3. Interfaz — selector de categoría en 3 sitios

Un `<select>` de categoría (misma estética que el de comunidad ya existente) con:
`""` (Todas — recibir todas), Educación, Sanidad, Justicia, Seguridad, Administración,
Hacienda, Correos, Técnica.

1. **Formulario de la home** — `index.html`, `#newsletterFormHome` (ya tiene
   `#newsletterComunidad`). Añadir `#newsletterCategoria` debajo. El handler inline
   (JS en `index.html`) manda `categoria` a `/api/subscribe`.
2. **Popup de suscripción** — `assets/script.js` (ya tiene `#nlPopComunidad`). Añadir
   `#nlPopCategoria`; el handler manda `categoria`.
3. **Página `/preferencias`** — `preferencias.html` (ya tiene `#prefCom`). Añadir
   `#prefCat`; el JS manda `categoria` a `/api/preferencias`. Renombrar el H1/título de
   "Elige tu comunidad" a "Elige tus preferencias" y adaptar el texto.
4. **Email de bienvenida** (`api/subscribe.js`, `emailBienvenidaHtml`): cambiar el enlace
   "Elegir comunidad →" por "Elegir preferencias →".

## 4. APIs

Siguen el MISMO patrón que ya tiene `comunidad` (importante, resuelve el "limpiar"):

- **`api/subscribe.js`** (alta): leer `categoria` del body; validar contra los 8 nombres;
  guardarla en el upsert **solo si viene** (`...(cat ? { categoria: cat } : {})`), para no
  pisar con vacío una preferencia previa cuando alguien se re-suscribe con el campo en
  blanco. Igual que hoy con `comunidad`.
- **`api/preferencias.js`** (editar preferencias): añadir `categoria` a la whitelist y
  **escribirla siempre** en el upsert, incluso `""`. Así, elegir "Todas" en la página de
  preferencias **limpia** el filtro (vuelve a recibir todas las categorías). Igual que hoy
  hace con `comunidad`. Se pueden actualizar comunidad y/o categoría de forma independiente.
- Validación: `""` (todas) siempre es válido; un nombre debe estar en la lista de 8; un
  valor no reconocido se ignora (se trata como no enviado), no rompe la petición.
- Lista de categorías válidas duplicada en ambos endpoints (JS, sin import compartido):
  `Educación, Sanidad, Justicia, Seguridad, Administración, Hacienda, Correos, Técnica`.

## 5. Aviso a los suscriptores (novedad)

Anunciar la nueva función en **todas las redes** + a los suscriptores por email.

- **Copys por red** (Telegram, Facebook, Instagram, X): mensaje breve tipo
  *"📢 Novedad: ahora puedes recibir en tu correo solo las oposiciones de tu comunidad
  Y/O de tu categoría (Administración, Sanidad, Educación…). Ajusta tus preferencias
  aquí 👉 oponoticias.com/preferencias"*, adaptado al tono de cada red.
- **Email a los 343 suscriptores** (recomendado, son los beneficiarios directos): un
  correo único anunciando que ya pueden elegir su categoría en `/preferencias`. Se puede
  reutilizar la mecánica SMTP de SES del newsletter (envío puntual, no el diario).
- **Publicación:** los copys se preparan como entregable; la publicación en redes se hace
  con confirmación explícita (acción pública). El email puntual, igual.

## Fuera de alcance (YAGNI)

- Multi-categoría (varias a la vez) — se decidió una sola, simétrica con la comunidad.
- Multi-comunidad — la comunidad sigue siendo una sola.
- Filtros por sub-cuerpo o por número de plazas.

## Pruebas

- Matriz del filtro `convocatorias_para`: las 4 combinaciones de la tabla + interacción
  con estatales + convocatoria con `categoria` NULL (no llega a quien filtró por categoría).
- Validación de `categoria` en las APIs (nombre válido vs inválido vs vacío).
- Que `categoria` vacía/None preserva el comportamiento actual (no rompe a los 343 subs).
