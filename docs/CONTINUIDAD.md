# Plan de continuidad de OpoNoticias

> Qué pasa si se rompe el Mac, cómo trabajar desde otro dispositivo, y qué hay
> que proteger para que el negocio nunca dependa de un solo ordenador.

## TL;DR — la tranquilidad primero

**El negocio NO depende del Mac.** Todo lo que mantiene OpoNoticias vivo corre en
la nube:

- **El código** está en GitHub (`Alexog91/oponoticias-web`) — fuente única de verdad.
- **La automatización diaria** (BOE, newsletter, blog, redes) corre en **GitHub
  Actions**, no en el Mac. Aunque el Mac esté apagado o roto, **todo sigue
  publicándose solo**.
- **Los datos** (convocatorias, suscriptores, blog) están en **Supabase**.
- **La web** está en **Vercel** (se despliega sola desde GitHub).
- **El correo** sale por **Amazon SES**.
- **Las claves/secretos** están en **GitHub Actions Secrets** (en la nube).
- **El Mac NO guarda ninguna contraseña ni clave** (no hay `.env` local).

Si el Mac muere hoy, OpoNoticias no se entera: mañana publica igual. El Mac solo
sirve para *hacer cambios*, no para *funcionar*.

## Dónde vive cada cosa

| Sistema | Qué guarda | ¿Sobrevive si se rompe el Mac? | ¿Backup? |
|---|---|:---:|---|
| GitHub | Todo el código + workflows + secretos | ✅ Sí | El propio Git (historial completo) |
| Supabase | Convocatorias, **suscriptores**, blog | ✅ Sí | ✅ Suscriptores: backup semanal por email (`backup-suscriptores.yml`) |
| Vercel | Hosting de la web | ✅ Sí | Se redespliega desde GitHub |
| AWS SES | Envío de correo | ✅ Sí | N/A (infraestructura) |
| Registrador del dominio | `oponoticias.com` | ✅ Sí | N/A |
| Google | Search Console, AdSense (ingresos) | ✅ Sí | N/A |
| Meta / TikTok / X / Telegram | Redes sociales | ✅ Sí | N/A |

## Si se rompe el Mac (o quieres trabajar desde otro dispositivo)

No hace falta el Mac para que el negocio funcione. Solo lo necesitas (o cualquier
otro ordenador) para *tocar el código*. Para dejar un ordenador nuevo listo:

```bash
git clone https://github.com/Alexog91/oponoticias-web.git
cd oponoticias-web
```

Y ya está: tienes todo el proyecto. Los cambios se suben con `git push` y los
workflows los recogen solos. No necesitas copiar ningún secreto al ordenador
nuevo — los secretos viven en GitHub, no en el ordenador.

**Incluso sin ordenador:** puedes editar archivos y hacer commits desde la **web
de GitHub** (github.com, botón de editar ✏️) o desde **GitHub Codespaces** (un
editor completo en el navegador). Con el móvil + navegador puedes gestionar casi
todo.

## Los verdaderos puntos únicos de fallo (NO es el Mac — son las CUENTAS)

El riesgo real no es el ordenador, es **perder el acceso a las cuentas**. Todo el
negocio es un conjunto de cuentas en la nube. Protégelas así:

1. **Contraseñas en un gestor multi-dispositivo** (Bitwarden, 1Password o iCloud
   Llavero sincronizado). Si las contraseñas solo están en el navegador del Mac,
   se pierden con el Mac. Guarda ahí: GitHub, Supabase, Vercel, AWS, registrador
   del dominio, Google, Meta, TikTok, X, y el **correo de Google del negocio**.

2. **El correo de Google del negocio es la llave maestra.** Casi todas las cuentas
   se recuperan por email. Si pierdes ese Gmail, caen todas en cascada.
   Protégelo con 2FA + códigos de recuperación guardados.

3. **2FA con copia.** Si el segundo factor está solo en una app del móvil y
   pierdes el móvil, te quedas fuera. Usa un autenticador que sincronice en la
   nube (Authy, 1Password, o Google Authenticator con copia) y **guarda los
   códigos de recuperación** de cada cuenta en el gestor.

4. **El dominio `oponoticias.com`.** Si caduca o pierdes el registrador, se cae
   toda la web y el correo. Activa **renovación automática** y apunta la fecha de
   caducidad.

5. **Los ~20 secretos de GitHub Actions** (lista abajo). En GitHub no se pueden
   *leer* una vez guardados (solo sobrescribir). Guarda una **copia de sus
   valores** en el gestor de contraseñas para poder re-crearlos en cualquier
   sitio si algún día migras de cuenta.

## Secretos que hacen funcionar la automatización

Guarda el valor de cada uno en tu gestor de contraseñas (aquí solo los nombres):

`ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_API_KEY`, `TELEGRAM_TOKEN`,
`TELEGRAM_CHAT_ID`, `TELEGRAM_ADMIN_CHAT_ID`, `FB_PAGE_TOKEN`, `FB_PAGE_ID`,
`FB_IG_ID`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `SES_SMTP_USER`,
`SES_SMTP_PASS`, `MAKE_WEBHOOK_URL`, `INSTAGRAM_WEBHOOK_URL`, `VIDEO_WEBHOOK_URL`.
(`GITHUB_TOKEN` lo genera GitHub solo; `BREVO_*` es el proveedor de correo antiguo,
ya no se usa.)

## Recuperación por sistema (si pasa lo peor)

- **Se corrompe/borra Supabase** → lo único irremplazable son los **suscriptores**
  (los emails no se pueden reconstruir). Las convocatorias se recuperan releyendo
  el BOE y las fichas están en GitHub. **Por eso hay que tener un backup de la
  tabla `suscriptores`** (ver PENDIENTE abajo).
- **Se pierde la cuenta de GitHub** → con la copia de los secretos + el código
  clonado en cualquier sitio, se recrea el repo y se re-suben los secretos.
- **Se cae Vercel** → se conecta el repo de GitHub a Vercel (o a Netlify/Cloudflare
  Pages) y se redespliega en minutos; es todo estático.
- **Se pierde el dominio** → se recompra/recupera en el registrador; la web y el
  correo vuelven al re-apuntar el DNS.

## PENDIENTE (lo que falta, y solo lo puedes hacer tú)

- [x] ~~Backup automático de la tabla `suscriptores`~~ → **HECHO**: `backup_suscriptores.py`
  + workflow `backup-suscriptores.yml` envían un CSV por email a `info@oponoticias.com`
  cada domingo. Guarda esos correos (o muévelos a una carpeta) para tener la copia
  fuera de Supabase.
- [ ] Guardar el valor de los secretos en el gestor de contraseñas.
- [ ] Activar renovación automática del dominio y anotar su caducidad.
- [ ] Verificar 2FA + códigos de recuperación de todas las cuentas.
