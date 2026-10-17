"""Reglas de negocio de las calificaciones.

Todo ingreso, modificación y eliminación pasa por aquí (formulario, carga masiva
y comando de demostración), así las reglas y la bitácora se aplican siempre igual.
"""
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404

from bitacora.models import Registro
from bitacora.servicios import registrar

from . import motor
from .models import Calificacion, Mercado, Origen


class ErrorValidacion(Exception):
    """Los datos no cumplen una regla de negocio. ``mensajes`` explica cuál."""

    def __init__(self, mensajes):
        self.mensajes = [mensajes] if isinstance(mensajes, str) else list(mensajes)
        super().__init__("; ".join(self.mensajes))


@dataclass
class ResultadoGuardado:
    calificacion: Calificacion
    estado: str  # "creada", "actualizada" o "sin_cambios"
    suma: object


def mensaje_rn1(resultado):
    desde, hasta = settings.COLUMNAS_SUMA_REGLA
    return (
        f"RN1: la suma de los factores de las columnas {desde} a {hasta} es "
        f"{motor.a_texto(resultado.suma)}, mayor que 1."
    )


def calcular(montos, monto_base=None):
    """Calcula los factores y evalúa RN1 SIN guardar nada.

    Devuelve ``(factores, ResultadoSuma)``. Lanza ErrorValidacion si no se puede calcular.
    """
    desde, hasta = settings.COLUMNAS_FACTOR
    fuera = [c for c in montos if not desde <= c <= hasta]
    if fuera:
        raise ErrorValidacion(f"Las columnas deben estar entre {desde} y {hasta}: {sorted(fuera)}")
    try:
        factores = motor.calcular_factores(
            montos,
            modo=settings.FACTORES_MODO_REDONDEO,
            decimales=settings.FACTORES_DECIMALES,
            divisor=monto_base,
        )
    except motor.ErrorCalculo as error:
        raise ErrorValidacion(str(error)) from error
    return factores, motor.validar_suma(factores, settings.COLUMNAS_SUMA_REGLA)


def _validar_identificacion(ejercicio, mercado, instrumento, secuencia, origen):
    errores = []
    try:
        ejercicio = int(ejercicio)
        if not 1990 <= ejercicio <= 2100:
            raise ValueError
    except (TypeError, ValueError):
        errores.append("El ejercicio no es un año válido.")
    if mercado not in Mercado.values:
        errores.append("El mercado no es válido.")
    instrumento = (instrumento or "").strip()
    if not instrumento:
        errores.append("Falta el instrumento.")
    elif len(instrumento) > 60:
        errores.append("El instrumento admite como máximo 60 caracteres.")
    try:
        secuencia = int(secuencia)
        if secuencia < 1:
            raise ValueError
    except (TypeError, ValueError):
        errores.append("La secuencia de evento debe ser un número entero positivo.")
    if origen not in Origen.values:
        errores.append("El origen no es válido.")
    if errores:
        raise ErrorValidacion(errores)
    return ejercicio, mercado, instrumento, secuencia, origen


def _texto(monto):
    return format(monto, "f")


def _describir_cambios(existente, montos, monto_base, origen, suma):
    cambios = []
    anteriores = existente.montos_decimal
    for columna in sorted(set(anteriores) | set(montos)):
        antes, ahora = anteriores.get(columna), montos.get(columna)
        if antes != ahora:
            cambios.append(
                f"Columna {columna}: monto de {_texto(antes) if antes is not None else '—'} "
                f"a {_texto(ahora) if ahora is not None else '—'}."
            )
    if existente.monto_base != monto_base:
        antes = _texto(existente.monto_base) if existente.monto_base is not None else "—"
        ahora = _texto(monto_base) if monto_base is not None else "—"
        cambios.append(f"Monto base de {antes} a {ahora}.")
    if existente.origen != origen:
        cambios.append(f"Origen cambiado de {existente.get_origen_display()} a {Origen(origen).label}.")
    if existente.suma_factores != suma:
        cambios.append(
            f"La suma de factores pasó de {motor.a_texto(existente.suma_factores)} a {motor.a_texto(suma)}."
        )
    if existente.eliminada:
        cambios.append("La calificación estaba eliminada y se reactivó.")
    return " ".join(cambios)


@transaction.atomic
def guardar_calificacion(
    usuario,
    *,
    ejercicio,
    mercado,
    instrumento,
    secuencia,
    origen,
    montos,
    monto_base=None,
    via=Registro.Origen.FORMULARIO,
):
    """Ingresa o actualiza (upsert por llave) una calificación de la corredora del usuario.

    Aplica el cálculo de factores, RN1 (suma <= 1) y RN2 (prevalece el dato del
    corredor sobre el de Bolsa), y deja constancia en la bitácora.
    """
    corredora = usuario.perfil.corredora
    ejercicio, mercado, instrumento, secuencia, origen = _validar_identificacion(
        ejercicio, mercado, instrumento, secuencia, origen
    )
    factores, resultado = calcular(montos, monto_base)
    if not resultado.cumple:
        raise ErrorValidacion(mensaje_rn1(resultado))

    llave = dict(
        corredora=corredora,
        ejercicio=ejercicio,
        mercado=mercado,
        instrumento=instrumento,
        secuencia=secuencia,
    )
    existente = Calificacion.objects.select_for_update().filter(**llave).first()

    # RN2: si ya hay dato del corredor, el dato base de Bolsa no lo reemplaza.
    if (
        existente
        and not existente.eliminada
        and existente.origen == Origen.CORREDOR
        and origen == Origen.BOLSA
    ):
        raise ErrorValidacion(
            "RN2: ya existe el dato del corredor para este instrumento y periodo; "
            "prevalece sobre el dato base de Bolsa."
        )

    montos_json = {str(c): _texto(m) for c, m in sorted(montos.items())}
    factores_json = {str(c): motor.a_texto(f) for c, f in factores.items()}
    suma = resultado.suma
    prefijo = f"{ejercicio} · {Mercado(mercado).label}. "

    if existente is None:
        calificacion = Calificacion.objects.create(
            **llave,
            origen=origen,
            montos=montos_json,
            monto_base=monto_base,
            factores=factores_json,
            suma_factores=suma,
            creada_por=usuario,
            modificada_por=usuario,
        )
        registrar(
            usuario,
            Registro.Operacion.INGRESO,
            calificacion.etiqueta,
            origen=via,
            detalle=f"{prefijo}Se creó la calificación con suma de factores {motor.a_texto(suma)}. "
            "Validación RN1: cumple.",
        )
        return ResultadoGuardado(calificacion, "creada", suma)

    sin_cambios = (
        not existente.eliminada
        and existente.montos_decimal == montos
        and existente.monto_base == monto_base
        and existente.origen == origen
    )
    if sin_cambios:
        return ResultadoGuardado(existente, "sin_cambios", suma)

    detalle = _describir_cambios(existente, montos, monto_base, origen, suma)
    existente.origen = origen
    existente.montos = montos_json
    existente.monto_base = monto_base
    existente.factores = factores_json
    existente.suma_factores = suma
    existente.eliminada = False
    existente.modificada_por = usuario
    existente.save()
    registrar(
        usuario,
        Registro.Operacion.MODIFICACION,
        existente.etiqueta,
        origen=via,
        detalle=prefijo + detalle,
    )
    return ResultadoGuardado(existente, "actualizada", suma)


@transaction.atomic
def eliminar_logico(usuario, calificacion, via=Registro.Origen.FORMULARIO):
    """RN3: la calificación deja de mostrarse pero se conserva, y queda en bitácora."""
    if calificacion.corredora_id != usuario.perfil.corredora_id:
        raise PermissionDenied("La calificación pertenece a otra corredora.")
    if calificacion.eliminada:
        return calificacion
    calificacion.eliminada = True
    calificacion.modificada_por = usuario
    calificacion.save(update_fields=["eliminada", "modificada_por", "modificada"])
    registrar(
        usuario,
        Registro.Operacion.ELIMINACION,
        calificacion.etiqueta,
        origen=via,
        detalle="Eliminación lógica: el registro deja de mostrarse en las consultas, pero se conserva.",
    )
    return calificacion


def obtener_calificacion(usuario, pk):
    """Busca una calificación vigente. Si es de otra corredora la deniega y lo registra (RN6)."""
    calificacion = get_object_or_404(Calificacion, pk=pk, eliminada=False)
    if calificacion.corredora_id != usuario.perfil.corredora_id:
        registrar(
            usuario,
            Registro.Operacion.INTENTO_RECHAZADO,
            f"Calificación {pk}",
            detalle="Intento de acceso a un registro de otra corredora (RN6).",
        )
        raise PermissionDenied("La calificación pertenece a otra corredora.")
    return calificacion
