# Plan: desbloquear el SEO de las fichas de convocatoria

> Objetivo: convertir las 519 fichas de `convocatoria/*.html` de "thin content"
> (motivo del rechazo de AdSense del 24 jun y razón del `noindex`) en páginas con
> contenido útil y único, para poder **quitar el `noindex`**, recuperar indexación,
> reactivar Google for Jobs y reaprobar AdSense.

## Diagnóstico (28 jun 2026)

- 519 fichas, **todas con `<meta name="robots" content="noindex, follow">`**.
- Contenido único real por ficha ≈ 200-300 caracteres: título del BOE (repetido),
  4 datos (puesto / plazas / ámbito / organismo), enlace al BOE y 3 relacionadas.
- El resto (≈90 %) es andamiaje idéntico en las 519: header, nav, footer, sidebar.
- Reparto por categoría: 499 Administración · 15 Técnica · 2 Educación · 1 Seguridad
  · 1 Sanidad · 1 Hacienda.
- Generador: `leer_boe.py` → `generar_html_convocatoria()` (línea ~1110).
  El `noindex` se escribe en la línea ~1156. El sitemap las excluye a propósito
  (`regenerar_sitemap`, ~1372).

## Estrategia

Añadir un **bloque de contenido enriquecido** generado SIN llamar a la API de Claude
(coste cero, plantilla que varía con los datos estructurados de cada ficha):
categoría, puesto, organismo, ámbito, plazas, fecha. Con suficientes dimensiones de
variación + texto genuinamente útil, dejan de ser thin/duplicadas.

Bloques a añadir dentro del `<div class="prose">`:
1. **Párrafo de contexto** específico (organismo + fecha + ámbito + puesto).
2. **Contexto de la categoría** (diccionario `CONTEXTO_CATEGORIA`, 2-3 frases útiles por área).
3. **"Cómo presentarte a esta convocatoria"** — pasos (plazo orientativo 20 días hábiles
   desde publicación en BOE, requisitos generales, dónde solicitar).
4. **FAQ** (3-4 preguntas que varían con los datos) + **schema `FAQPage`** (rich results).
5. **Enlaces internos** a la página de la categoría y de la CCAA correspondiente
   (mejora interlinking y quita sensación de página huérfana).

Resultado esperado: +1500-2500 caracteres de contenido variado y útil por ficha.

## Fases

- [x] **Fase 0 — Diagnóstico** (hecho 28 jun): confirmado noindex en las 519,
      estructura del generador, categorías y CCAA disponibles.
- [x] **Fase 1 — Bloque enriquecido** (hecho 28 jun): en `leer_boe.py` se añadió
      `CONTEXTO_CATEGORIA`, helpers `_norm_slug()` / `_slug_categoria()` / `_slug_ccaa()`
      y `_bloque_enriquecido(...)` (devuelve HTML + JSON-LD `FAQPage`). Wire hecho:
      el bloque se inserta antes de `{relacionadas_html}` y el FAQ schema en el `<head>`
      junto al `JobPosting`. Verificado en ficha de prueba: 2 JSON-LD válidos, enlaces
      internos a categoría y CCAA OK, +~1.500 caracteres de contenido único por ficha.
      Estilo inline (no se tocó `style.css`, se evita el cascadeo de `?v=`).
      **Efecto inmediato:** las fichas NUEVAS (workflow diario) ya salen enriquecidas;
      las 519 viejas siguen finas hasta la Fase 2. Ambas con noindex aún → consistente y seguro.
- [x] **Fase 2 — Regenerar las 519 fichas** (hecho 28 jun): script
      `scratchpad/regen_fichas.py` que parsea cada HTML existente (sin Supabase),
      preserva el bloque de "Convocatorias relacionadas" y rellama al generador con
      `forzar=True`. **OJO clave:** el sitio desplegado es el nivel superior del repo
      (`./convocatoria`, remoto `oponoticias-web.git`); el default
      `WEB_REPO_PATH=./oponoticias-web` es legacy → en local hay que ejecutar con
      `WEB_REPO_PATH=. PYTHONPATH=. python3 …` (CI ya usa `WEB_REPO_PATH='.'`).
      Resultado: 519/519 regeneradas, 0 fallos. Verificado: 519 con FAQ + pasos +
      schema `FAQPage`, JSON-LD válido, 249 conservan relacionadas (= las mismas que en
      HEAD, ninguna perdida), todas siguen en `noindex`. Tamaño medio 20KB→25KB.
      Script idempotente (re-ejecutar no duplica). **Pendiente de commit/deploy.**

  <!-- Referencia histórica de cómo se hizo, por si hay que repetir: -->
  <details><summary>Cómo se hizo la Fase 2</summary>
      1. La fuente de datos es Supabase (tabla de convocatorias). Ver `guardar_en_supabase()`
         y cómo `leer_boe.py` lee/consulta. Hay que recuperar cada `conv` guardada.
      2. Para cada conv: recalcular `relacionadas_html` (mirar cómo lo hace el flujo
         normal — buscar dónde se llama a `generar_html_convocatoria` con `relacionadas_html`)
         y llamar con `forzar=True`. El slug debe coincidir con el archivo existente
         (usa `generar_slug(titulo, ref_boe)`), así sobrescribe en vez de duplicar.
      3. Alternativa más simple si no se puede leer Supabase: parsear los datos desde
         los propios HTML existentes (título, ref_boe, fecha, comunidad, resumen) y
         rellamar al generador. Menos limpio pero evita dependencias.
      4. Regenerar también el sitemap (Fase 3 lo cubre).
      ⚠️ Verificar 2-3 fichas a mano tras regenerar antes de commitear las 519.
  </details>
- [ ] **Fase 3 — Quitar el `noindex`** (línea ~1156: cambiar a `index, follow`) e
      **incluir las fichas en el sitemap** (`regenerar_sitemap`, ~1372). Hacerlo solo
      cuando el contenido esté ya enriquecido. Considerar rollout gradual.
- [ ] **Fase 4 — Pedir reindexación** en Search Console y, semanas después con
      tráfico/contenido sólido, **reenviar AdSense a revisión**.

## Notas / gotchas

- Assets cacheados `immutable` 1 año en `vercel.json`: subir `?v=` si se tocan css/js.
- El `JobPosting` schema ya está, pero es inútil mientras haya `noindex` (Google for
  Jobs no muestra páginas noindex). Se desbloquea solo en Fase 3.
- No usar la API de Claude por ficha (519 llamadas = caro y lento). Todo por plantilla.
- Mantener el aviso "carácter informativo / lo vinculante es el BOE" (ya está).

## Estado actual

**28 jun 2026:** Fases 0, 1 y 2 completas. `leer_boe.py` genera fichas enriquecidas y
las 519 existentes ya están regeneradas en local (aún en `noindex`, pendiente de
commit/deploy). **Próximo paso = Fase 3** (quitar `noindex` + incluir en sitemap).

⚠️ **Aviso honesto para la Fase 3:** las 499 fichas de "Administración" comparten el
mismo párrafo de contexto de categoría (texto idéntico). La unicidad real por página
viene del intro (organismo/fecha/puesto/ámbito), las respuestas del FAQ y el título.
Es una mejora grande frente al original (~250 car. casi idénticos), pero no es
infalible: conviene quitar el `noindex` y pedir indexación, observar en Search Console
unas semanas, y solo entonces reenviar AdSense (Fase 4). Valorar rollout gradual.
