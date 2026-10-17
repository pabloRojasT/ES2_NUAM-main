"""Motor de cálculo de factores tributarios.

Python puro: no depende de Django ni de la base de datos, para poder probarlo
solo y con rapidez. Toda la aritmética usa ``Decimal`` (nunca ``float``) para
evitar errores de representación sobre montos tributarios.

HIPÓTESIS DE TRABAJO (pendientes de confirmar con el cliente, informe sec. 9):
  * Divisor: si no se informa un monto base, es la suma de los montos informados.
  * Redondeo: por defecto se trunca a ocho decimales (el truncamiento garantiza
    que la suma de factores no supere 1 por efecto del redondeo).
"""
import re
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, localcontext

DECIMALES = 8
MODOS = {"truncar": ROUND_DOWN, "redondear": ROUND_HALF_UP}
TOPE_SUMA = Decimal("1")
MAX_DECIMALES_MONTO = 6

_PATRON_MONTO = re.compile(r"\d+([.,]\d+)?")


class ErrorCalculo(ValueError):
    """El cálculo no se puede realizar con los datos entregados."""


def parsear_monto(texto):
    """Convierte un texto en ``Decimal`` no negativo.

    Acepta solo dígitos y, si corresponde, un separador decimal (punto o coma).
    No acepta separadores de miles ("1.000.000") porque serían ambiguos.
    """
    if isinstance(texto, Decimal):
        valor = texto
    else:
        limpio = str(texto).strip().replace(" ", "")
        if not limpio:
            raise ErrorCalculo("el monto está vacío")
        if not _PATRON_MONTO.fullmatch(limpio):
            raise ErrorCalculo(
                f"«{texto}» no es un monto válido: usa solo dígitos y, si corresponde, un decimal"
            )
        valor = Decimal(limpio.replace(",", "."))
    if not valor.is_finite():
        raise ErrorCalculo("el monto no es un número finito")
    if valor < 0:
        raise ErrorCalculo("los montos no pueden ser negativos")
    if valor.as_tuple().exponent < -MAX_DECIMALES_MONTO:
        raise ErrorCalculo(f"el monto admite como máximo {MAX_DECIMALES_MONTO} decimales")
    return valor


def calcular_factores(montos, modo="truncar", decimales=DECIMALES, divisor=None):
    """Calcula el factor de cada columna: ``monto / divisor``.

    ``montos`` es un dict ``{columna: Decimal}``. Si ``divisor`` es None se usa
    la suma de los montos informados. Devuelve ``{columna: Decimal}`` con
    exactamente ``decimales`` decimales.
    """
    if modo not in MODOS:
        raise ErrorCalculo(f"modo de redondeo desconocido: «{modo}»")
    if not montos:
        raise ErrorCalculo("no se informó ningún monto")
    if divisor is None:
        divisor = sum(montos.values(), Decimal(0))
    if divisor <= 0:
        raise ErrorCalculo("el divisor es 0: no se puede calcular los factores")
    cuanto = Decimal(1).scaleb(-decimales)
    with localcontext() as contexto:
        contexto.prec = 50
        return {
            columna: (monto / divisor).quantize(cuanto, rounding=MODOS[modo])
            for columna, monto in sorted(montos.items())
        }


@dataclass(frozen=True)
class ResultadoSuma:
    """Resultado de aplicar la regla RN1 sobre un conjunto de factores."""

    suma: Decimal
    cumple: bool
    columnas: tuple


def validar_suma(factores, columnas_regla=(8, 16), tope=TOPE_SUMA):
    """RN1: la suma de los factores de las columnas de la regla debe ser <= ``tope``."""
    desde, hasta = columnas_regla
    columnas = tuple(c for c in sorted(factores) if desde <= c <= hasta)
    suma = sum((factores[c] for c in columnas), Decimal(0))
    return ResultadoSuma(suma=suma, cumple=suma <= tope, columnas=columnas)


def a_texto(valor, decimales=DECIMALES):
    """Formatea un decimal con exactamente ``decimales`` decimales (punto decimal)."""
    return format(valor, f".{decimales}f")
