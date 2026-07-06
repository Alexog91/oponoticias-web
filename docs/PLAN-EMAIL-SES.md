# Plan: migrar el boletín diario de Brevo a motor propio (Amazon SES)

**Objetivo:** dejar de depender del límite de Brevo (300 envíos/día en el plan
gratis) montando un motor de envío propio con **Amazon SES** (~0,10 $/1.000
emails). El boletín sigue siendo **diario** y no cambia nada de cara al usuario.

**Regla de oro de esta migración:** **Brevo se queda INTACTO y sigue siendo el
canal oficial hasta que el usuario dé la orden de corte.** Todo lo nuevo se
construye EN PARALELO. En ningún momento el boletín en producción deja de salir
por Brevo hasta la Fase 5. Nada se apaga sin estar más que probado.

Estado: **Fase 0 en curso** (5 jul 2026). Ver [[oponoticias-esp-alternativas]].

---

## Reparto de tareas

- 🧑 **Usuario (Jaime/Alex):** todo lo que requiere cuenta/credenciales/DNS/consola
  (crear cuenta AWS, tocar DNS, ejecutar SQL en Supabase, poner secrets). Claude
  no puede crear cuentas ni introducir credenciales.
- 🤖 **Claude:** todo el código, SQL, scripts y documentación.

---

## Fase 0 — Fundaciones (sin tocar nada vivo) · EN CURSO
- [x] 🤖 Esquema Supabase: `crear_tabla_suscriptores.sql` (tablas `suscriptores`
      + `envios_newsletter`, RLS privada). **No toca Brevo.**
- [x] 🤖 Este documento de plan.
- [x] 🧑 Ejecutar `crear_tabla_suscriptores.sql` en Supabase → SQL Editor.
      ✅ HECHO 5 jul 2026 — verificado en Chrome: tablas `suscriptores` (con
      columna `comunidad`) y `envios_newsletter` creadas y vacías. Resto intacto.

## Fase 1 — Cuenta AWS SES + dominio (arranca el reloj del sandbox, ~1-3 días)
> Conviene empezar esto pronto porque la aprobación de AWS tarda días.
>
> **DATOS DE DNS VERIFICADOS (5 jul 2026) — leer antes de tocar nada:**
> - El DNS de `oponoticias.com` se gestiona en **Hostinger** (nameservers
>   `ns1/ns2.dns-parking.com`) → hPanel → Dominios → oponoticias.com → Zona DNS.
> - **SPF EXISTENTE:** `v=spf1 include:_spf.protonmail.ch ~all`. NO reemplazar.
>   Al añadir SES hay que FUSIONAR: `v=spf1 include:_spf.protonmail.ch include:amazonses.com ~all`
>   (si se reemplaza, se rompe el envío desde el buzón Proton `info@oponoticias.com`).
> - **DMARC EXISTENTE:** `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` (modo
>   monitorización) → NO hace falta tocarlo para empezar; SES funciona con p=none.
> - **Buzón del dominio = Proton** (MX protonmail.ch). El remitente `info@oponoticias.com`
>   pasaría a tener 3 caminos de envío (Proton + Brevo + SES); con el SPF fusionado
>   + DKIM propio de cada uno, conviven sin problema.
>
- [ ] 🧑 Crear cuenta de AWS (con método de pago; el coste será de céntimos).
- [ ] 🧑 Elegir región **EU (Irlanda) eu-west-1** en SES (residencia de datos en la UE).
- [x] 🤖 En SES: identidad de dominio `oponoticias.com` creada (Easy DKIM RSA 2048,
      región eu-west-1). ✅ HECHO 5 jul 2026. ARN:
      `arn:aws:ses:eu-west-1:819947220143:identity/oponoticias.com`. Estado: verificación pendiente.
- [x] 🤖 Añadir en Hostinger (Zona DNS) los **3 CNAME de DKIM**. ✅ HECHO 5 jul 2026,
      verificado en Chrome (filtro "amazonses" → los 3 presentes y bien formados).
      Nada existente tocado (Proton/Brevo/SPF/DMARC intactos).
      ✅ DOMINIO VERIFICADO por AWS el 5 jul 2026 (propagó en minutos). Valores de AWS:
      1. Nombre `f2q54xmh3ckw6unj53j4lynd37t6h35n._domainkey` →
         Valor `f2q54xmh3ckw6unj53j4lynd37t6h35n.dkim.amazonses.com`
      2. Nombre `6xzdlr4qedm4ppiabas5jsmrdmfslesg._domainkey` →
         Valor `6xzdlr4qedm4ppiabas5jsmrdmfslesg.dkim.amazonses.com`
      3. Nombre `dycrcgk73vqzjesvtfpmwrdaxoq7xyw2._domainkey` →
         Valor `dycrcgk73vqzjesvtfpmwrdaxoq7xyw2.dkim.amazonses.com`
- [x] 🤖 **DECISIÓN SPF/DMARC (corrige la nota de arriba):** NO hace falta tocar el
      SPF ni el DMARC ahora. Con MAIL FROM por defecto (`amazonses.com`), el SPF pasa
      contra amazonses.com y la **alineación DKIM** (d=oponoticias.com vía los 3 CNAME)
      basta para que DMARC pase. Tocar el SPF de Proton solo sería necesario si más
      adelante configuramos un MAIL FROM personalizado (opcional, no ahora). → Menos
      riesgo: no se toca nada del correo Proton existente.
- [~] 🤖 Solicitar **salida del sandbox**. Solicitud enviada 5 jul 2026; AWS pidió
      MÁS INFORMACIÓN (revisión manual, caso soporte #178327817600248). Respondido el
      mismo día vía AWS Support Center con el detalle del caso de uso (frecuencia diaria,
      lista 100% opt-in en Supabase, gestión de rebotes/quejas por SNS + supresión SES,
      baja de 1 clic con List-Unsubscribe, ejemplo de contenido). PENDIENTE: respuesta
      de AWS (suelen contestar en ≤24h). Mientras, sandbox = 200/día, 1/seg.
- [ ] 🧑 Crear usuario IAM con permiso **solo de enviar email** (no acceso
      general) y guardar sus credenciales como secrets.
- [ ] 🤖 Guiar cada paso + revisar los registros DNS antes de que propaguen.

## Fase 2 — Almacén de contactos en Supabase (en paralelo, Brevo intacto)
- [ ] 🧑 Exportar CSV de contactos desde Brevo (email + atributo COMUNIDAD).
      (Brevo → Contactos → seleccionar todos → Exportar.)
- [x] 🤖 `importar_suscriptores_brevo.py` ✅ HECHO 5 jul 2026. Lee el CSV (autodetecta
      columna email/comunidad y separador `;`/`,`), deduplica, normaliza email a
      minúsculas, valida comunidad. Upsert por email (merge-duplicates) en lotes de 500.
      NO envía estado ni token_baja (default de la BD → no resucita bajas, conserva
      tokens). `DRY_RUN=1` para simular. Verificado con CSV de ejemplo.
- [x] 🤖 **Doble escritura** ✅ HECHO 5 jul 2026. `api/subscribe.js` (alta → upsert
      `{email, estado:'activo', origen, material, comunidad?}`) y `api/preferencias.js`
      (cambio de comunidad → upsert `{email, comunidad}`) escriben TAMBIÉN en Supabase.
      Helper `https` autocontenido en cada archivo (sin módulo compartido, para no
      arriesgar el sistema de módulos de Vercel). NO bloquea: si Supabase falla, el
      alta/cambio en Brevo sigue OK (solo se registra el error). Requiere en Vercel las
      env vars `SUPABASE_URL` y `SUPABASE_API_KEY`. Sintaxis verificada.

## Fase 3 — Motor de envío SES (nuevo, NO reemplaza nada todavía)
- [x] 🤖 `enviar_newsletter_ses.py` ✅ HECHO 5 jul 2026. Lee suscriptores activos de
      Supabase, filtra convocatorias por comunidad EN PYTHON (`convocatorias_para()`,
      misma regla que la condición Brevo), y envía uno a uno por **SMTP de SES**
      (`smtplib`, sin boto3 — solo stdlib como el resto del repo). MIME multipart
      (texto + HTML) con cabeceras `List-Unsubscribe` + `List-Unsubscribe-Post` de 1 clic.
      Idempotencia reclamando el día en `envios_newsletter` (409 en la PK = ya enviado).
      Errores por-contacto no abortan el lote. **No cableado a ningún workflow.**
      Verificado con tests: segmentación correcta (Madrid ve estatal+Madrid, etc.),
      parseo plazas/puesto (4 plazas / 1 plaza / Varias), sin llaves Brevo residuales.
- [x] 🤖 `api/unsubscribe.js` ✅ HECHO 5 jul 2026. GET (clic → página de confirmación)
      y POST (one-click Gmail/Yahoo → 200). Marca `estado='baja'` + `fecha_baja` en
      Supabase por `token_baja`. Validación estricta: solo acepta UUID (evita PATCH sin
      filtro efectivo). Sintaxis verificada. **Requiere env vars nuevas en Vercel:
      `SUPABASE_URL` y `SUPABASE_API_KEY` (service_role legacy).**
- [x] 🤖 Modo prueba integrado: `TEST_EMAILS` (envía solo a esos buzones, ignora la
      tabla), `TEST_COMUNIDAD`, `DRY_RUN=1` (no envía ni toca Supabase), `SEND_INTERVAL`.

### Env vars pendientes de configurar (cuando toque probar/desplegar)
- **En el workflow / entorno del script Python:** `SES_SMTP_USER`, `SES_SMTP_PASS`
  (crear en SES → Configuración de SMTP → Crear credenciales SMTP; genera un IAM
  bajo el capó → cubre también el paso "usuario IAM de solo-envío" de la Fase 1),
  `SENDER_EMAIL`, `SENDER_NAME`. `SES_SMTP_HOST` por defecto ya es eu-west-1.
- **En Vercel (para el endpoint de bajas):** `SUPABASE_URL`, `SUPABASE_API_KEY`.

### Estado del código (5 jul 2026): TODO escrito y verificado en sintaxis/lógica.
Piezas listas e inertes (Brevo intacto): `enviar_newsletter_ses.py`, `api/unsubscribe.js`,
`importar_suscriptores_brevo.py`, doble escritura en `subscribe.js`/`preferencias.js`.
Falta solo lo que depende de credenciales/aprobación externa (abajo) + las pruebas.

## Fase 4 — Convivencia y validación (Brevo SIGUE siendo el oficial)
- [ ] 🧑🤖 Durante unos días: el script SES se ejecuta a mano enviando solo a
      buzones internos, mientras Brevo manda el boletín real. Comprobar:
      llega a bandeja de entrada (no spam) en Gmail/Outlook/Hotmail, render OK,
      enlaces OK, la baja funciona, la tabla Supabase está completa y sincronizada,
      la reputación en el panel de SES es buena y no hay rebotes raros.

## Fase 5 — Corte (SOLO cuando el usuario lo diga)
- [ ] 🧑 Orden explícita de cambio.
- [ ] 🤖 Cambiar el workflow para llamar a `enviar_newsletter_ses.py` en lugar
      del envío por Brevo.
- [ ] 🧑🤖 Vigilar de cerca la primera semana (rebotes, quejas, entregabilidad).
- [ ] 🧑 Apagar/archivar Brevo solo cuando esté confirmado que todo va bien.

---

## Notas técnicas de referencia
- **Supabase:** proyecto `opnbxphxfclazxduhmkp`. Escrituras necesitan la clave
  **service_role LEGACY** (JWT `eyJ…`, no `sb_secret_`) + cabecera
  `Authorization: Bearer`. Ver [[oponoticias-supabase-401]].
- **Idempotencia:** imprescindible mantenerla (un re-disparo del workflow no debe
  reenviar) — de ahí la tabla `envios_newsletter`. Ver el incidente de los 3
  correos del 26 jun en [[oponoticias-supabase-401]].
- **Gestión continua de SES:** casi nula. Rebotes/quejas los suprime AWS solo;
  el trabajo es montar alarmas (coste + tasa de rebote/queja) UNA vez y atender
  un email de AWS solo si alguna salta. Ver [[oponoticias-esp-alternativas]].
