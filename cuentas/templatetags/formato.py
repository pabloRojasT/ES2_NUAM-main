from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def coma(valor):
    """Muestra un decimal con coma, como se usa en Chile: 0.33333333 -> 0,33333333."""
    if valor is None or valor == "":
        return "—"
    return str(valor).replace(".", ",")


@register.filter
def pesos(valor):
    """Monto con puntos de miles y coma decimal: 1000000 -> 1.000.000."""
    if valor is None or valor == "":
        return "—"
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return str(valor)
    entero, _, decimales = format(numero, "f").partition(".")
    entero = f"{int(entero):,}".replace(",", ".")
    return entero + ("," + decimales if decimales.strip("0") else "")
