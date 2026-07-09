---
name: motion-design-serio
description: Guía de motion design para los vídeos promocionales de OpoNoticias (crear_video_kit.py y similares) — cómo dar intención al movimiento sin caer en la estética infantil/cartoon ni en el genérico "fade + Ken Burns" por defecto. Úsala antes de escribir o revisar cualquier escena de vídeo.
license: Elaborada a partir de los 12 principios de animación de Johnston & Thomas (Disney, 1981), adaptados a un tono institucional/serio.
---

# Motion design serio para OpoNoticias

Actúa como el director de motion graphics de un estudio que hace vídeos para instituciones y medios especializados (piensa en el motion de un banco, una consultora o un telediario), no para una app infantil. OpoNoticias trata oposiciones, BOE, plazos legales — el movimiento debe transmitir **precisión y autoridad**, nunca ligereza. Si una animación te hace pensar en un dibujo animado, está mal calibrada para esta marca.

Los 12 principios clásicos de animación (Johnston & Thomas) son técnicas de **cómo se mueve algo en el tiempo**, no un estilo visual. La mayoría son perfectamente serios. Dos de ellos SÍ leen como cartoon y hay que evitarlos aquí:

## Excluidos explícitamente (leen como cartoon)

- **Squash & stretch** (deformar un objeto al moverse para dar sensación de peso/elasticidad): nunca en UI/tarjetas/texto. Cero excepciones.
- **Exageración**: nada de overshoot cómico, rebotes tipo goma elástica, ni "pop" con overshoot > 100%. Si un elemento entra, entra y se queda — sin rebote visible.

## Los 10 que sí aplican, adaptados a tono serio

1. **Timing (velocidad) y ease serio.** Nunca `linear`. Pero tampoco `ease-out-elastic` ni `bounce`. Usa curvas `ease-in-out` cortas y contenidas (cubic-bezier suave, sin overshoot). Regla práctica: si la curva tiene un nombre con "bounce", "elastic" o "back" en tu librería de animación, no es para este proyecto.

2. **Slow in / slow out.** Todo movimiento acelera al empezar y frena al terminar — nunca velocidad constante. Es lo que hace que algo se sienta con intención en vez de "puesto ahí". Ya lo aplica el Ken Burns de `crear_video_kit.py` (zoompan con progresión, no salto brusco).

3. **Anticipación mínima, no cómica.** Antes de un cambio importante (aparece un dato, cambia de escena), un instante muy breve de preparación ayuda al ojo — pero en registro serio es casi imperceptible (100–150ms de pre-fade o de leve desenfoque), no un "agacharse antes de saltar" visible.

4. **Staging: un solo protagonista por plano.** En cada escena debe estar clarísimo qué mirar primero. Si hay una hoja de Excel Y un titular grande Y un CTA compitiendo por atención al mismo tiempo, sobra jerarquía — escalona su aparición o reduce el peso visual de los secundarios (ya se hizo en `crear_promo_kit.py`: título arriba, hoja centrada, CTA abajo, nunca los tres con el mismo peso).

5. **Arcos.** El movimiento natural no es en línea recta ni en zoom puramente central — un desplazamiento sutil en diagonal o un punto de zoom ligeramente descentrado (no el centro geométrico exacto) se siente más intencionado que un zoom perfectamente simétrico.

6. **Acción secundaria, contenida.** Un detalle de apoyo (un chip que aparece un instante después del titular, una línea que se subraya) refuerza sin robar protagonismo — pero en tono serio son 1 elemento, nunca 3 cosas moviéndose a la vez.

7. **Continuidad/overlap entre escenas.** Los cortes secos (in a, out a) leen a PowerPoint. Usa transiciones que solapen (el `xfade` que ya usa `crear_video_kit.py` es correcto) en vez de cortes duros — pero el fundido debe ser corto (0.3–0.5s): un fundido largo en contenido serio se siente lento, no elegante.

8. **Appeal = claridad, no simpatía.** En animación de personajes "appeal" significa carisma. Aquí significa **legibilidad instantánea**: tipografía con jerarquía clara (ya se usa Merriweather para titulares/serif de autoridad + Inter para datos), contraste suficiente, nunca un elemento que tape a otro a mitad de transición.

9. **Pose a pose, no straight-ahead.** Diseña primero los estados clave (inicio/fin de cada escena) y solo después decide cómo se interpola entre ellos — evita improvisar movimiento continuo sin saber a dónde llega, que es como se cuelan los desbordes de layout que ya detectó el chequeo automático de `crear_promo_kit.py`.

10. **Solid drawing → aquí, solidez de marca.** Cada escena debe sostenerse visualmente con los tokens reales de `assets/style.css` (paleta, --serif/--sans) — nunca un color o tipografía "de más" que no exista en la marca, por bonito que parezca en el momento.

## Antes de dar por bueno un vídeo o pieza, pregúntate

- ¿Alguna curva de easing tiene rebote o overshoot? → quítalo.
- ¿Hay más de un elemento pidiendo atención en el mismo instante? → escalona o reduce peso.
- ¿El corte entre escenas es duro en vez de solapado? → añade xfade corto.
- ¿El zoom/paneo es perfectamente simétrico y centrado? → dale un arco sutil.
- ¿Se entendería la jerarquía (qué mirar primero) con el audio quitado? → si no, la staging falla.
