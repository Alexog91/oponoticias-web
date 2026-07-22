"""tests/test_newsletter_vacios.py — nadie debe recibir un boletín vacío.

Ejecuta:  python3 tests/test_newsletter_vacios.py

Por qué existe: el motor tiene una guarda GLOBAL (si el BOE no publica nada, no
se envía nada) pero durante meses no tuvo una POR SUSCRIPTOR. Quien filtraba por
una comunidad pequeña recibía igualmente su correo diario con el asunto
"0 convocatorias nuevas". Medido sobre 30 días reales: 412 de 10.200 correos
(4 %), y un sábado de junio con solo 6 convocatorias en todo el BOE se habrían
mandado 181 correos vacíos de golpe. Eso quema la lista y dispara las quejas de
spam, que en SES por encima del 0,1 % ponen en riesgo la cuenta.
"""

import os
import sys
from pathlib import Path

# El módulo lee credenciales al importarse; con valores falsos basta porque
# aquí no se toca la red.
os.environ.setdefault("SUPABASE_URL", "https://ejemplo.invalid")
os.environ.setdefault("SUPABASE_API_KEY", "falsa")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import enviar_newsletter_ses as motor  # noqa: E402


def convo(ccaa):
    return {"titulo": f"Plazas en {ccaa or 'todo el Estado'}", "comunidad_autonoma": ccaa}


MADRID = convo("Madrid")
ANDALUCIA = convo("Andalucía")
ESTATAL = convo("Nacional/Estatal")

casos = []
test = lambda nombre, fn: casos.append((nombre, fn))  # noqa: E731


test("un suscriptor SIN convocatorias suyas queda fuera del envío", lambda: (
    motor.con_contenido([{"comunidad": "Aragón"}], [MADRID, ANDALUCIA]) == []
))

test("con una convocatoria suya, sí recibe", lambda: (
    len(motor.con_contenido([{"comunidad": "Madrid"}], [MADRID, ANDALUCIA])) == 1
))

test("las estatales llegan a todo el mundo (nadie queda vacío)", lambda: (
    len(motor.con_contenido(
        [{"comunidad": "Aragón"}, {"comunidad": "Murcia"}], [ESTATAL])) == 2
))

test("sin comunidad = lo ve todo", lambda: (
    len(motor.con_contenido([{"comunidad": ""}], [MADRID])) == 1
))

test("devuelve YA calculadas las convocatorias de cada uno (no se recalculan)", lambda: (
    motor.con_contenido([{"comunidad": "Madrid"}], [MADRID, ANDALUCIA, ESTATAL])[0][1]
    == [MADRID, ESTATAL]
))

test("el caso real que motivó el fix: día flojo sin nada estatal", lambda: (
    # 6 convocatorias, ninguna estatal, ninguna de las comunidades de la lista.
    motor.con_contenido(
        [{"comunidad": "Canarias"}, {"comunidad": "Murcia"}, {"comunidad": "Galicia"}],
        [convo("Cataluña")] * 6) == []
))

test("mezcla: solo pasan los que tienen algo", lambda: (
    [s["comunidad"] for s, _ in motor.con_contenido(
        [{"comunidad": "Madrid"}, {"comunidad": "Aragón"}, {"comunidad": ""}],
        [MADRID])] == ["Madrid", ""]
))


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in casos:
        try:
            ok = fn()
        except Exception as e:                       # noqa: BLE001
            ok = False
            nombre = f"{nombre}  [excepción: {e}]"
        print(f"{'✓' if ok else '✗'} {nombre}")
        fallos += not ok
    print("─" * 62)
    print(f"{fallos} test(s) fallaron" if fallos else "TODO OK")
    sys.exit(1 if fallos else 0)
