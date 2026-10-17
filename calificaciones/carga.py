"""Carga masiva de calificaciones desde un archivo CSV.

Flujo en tres pasos (igual que el prototipo):
  1. ``leer_csv`` lee y valida el archivo fila por fila SIN guardar nada.
  2. El usuario revisa la vista previa.
  3. ``ejecutar_carga`` guarda las filas válidas y rechaza las inválidas con su
     motivo. Una fila con error no cancela el resto del archivo.

Formato del CSV (separador coma o punto y coma, codificación UTF-8):
  ejercicio, mercado, instrumento, secuencia, origen, monto_8, monto_9, ..., monto_base
  * ``origen`` es opcional ("corredor" por defecto) y ``monto_base`` también.
  * Cada columna ``monto_N`` es opcional: se deja vacía si no aplica.
"""
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings

from bitacora.models import Registro
from bitacora.servicios import registrar

from . import motor, services
from .models import Calificacion, Mercado, Origen

ENCABEZADOS_OBLIGATORIOS = ("ejercicio", "mercado", "instrumento", "secuencia")

ALIAS_MERCADO = {
    "acciones": Mercado.ACCIONES,
    "accion": Mercado.ACCIONES,
    "cfi": Mercado.CFI,
    "cuotas de fondos de inversion": Mercado.CFI,
    "fondos mutuos": Mercado.FONDOS_MUTUOS,
    "fondo mutuo": Mercado.FONDOS_MUTUOS,
    "fondos_mutuos": Mercado.FONDOS_MUTUOS,
}

ALIAS_ORIGEN = {
    "": Origen.CORREDOR,
    "corredor": Origen.CORREDOR,
    "dato del corredor": Origen.CORREDOR,
    "bolsa": Origen.BOLSA,
    "dato base de bolsa": Origen.BOLSA,
}


class ErrorArchivo(Exception):
    """El archivo completo no se puede leer (formato, columnas o tamaño)."""


@dataclass
class FilaCarga:
    numero: int
    ejercicio: str = ""
    mercado: str = ""             # texto tal como venía en el archivo
    mercado_codigo: str = ""      # código normalizado, vacío si no se reconoció
    instrumento: str = ""
    secuencia: str = ""
    origen: str = Origen.CORREDOR
    montos: dict = field(default_factory=dict)
    monto_base: Decimal = None
    error: str = ""


@dataclass
class ResultadoCarga:
    total: int
    nuevas: int = 0
    actualizadas: int = 0
    sin_cambios: int = 0
    rechazadas: list = field(default_factory=list)  # [(numero_de_fila, motivo), ...]


def _normalizar(texto):
    """Minúsculas, sin tildes y sin espacios repetidos."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _leer_fila(numero, linea, indice, columnas_monto):
    def celda(nombre):
        posicion = indice.get(nombre)
        return linea[posicion].strip() if posicion is not None and posicion < len(linea) else ""

    fila = FilaCarga(numero=numero)
    errores = []

    fila.instrumento = celda("instrumento")
    if not fila.instrumento:
        errores.append("Falta el campo Instrumento")

    fila.mercado = celda("mercado")
    codigo = ALIAS_MERCADO.get(_normalizar(fila.mercado))
    if codigo:
        fila.mercado_codigo = codigo
    elif fila.mercado:
        errores.append(f"Mercado no reconocido: «{fila.mercado}»")
    else:
        errores.append("Falta el campo Mercado")

    fila.ejercicio = celda("ejercicio")
    if not (fila.ejercicio.isdigit() and 1990 <= int(fila.ejercicio) <= 2100):
        errores.append("El ejercicio no es un año válido")

    fila.secuencia = celda("secuencia")
    if not (fila.secuencia.isdigit() and int(fila.secuencia) >= 1):
        errores.append("La secuencia de evento no es un número")

    origen = ALIAS_ORIGEN.get(_normalizar(celda("origen")))
    if origen is None:
        errores.append("Origen no reconocido (usa corredor o bolsa)")
    else:
        fila.origen = origen

    for columna, posicion in columnas_monto.items():
        valor = linea[posicion].strip() if posicion < len(linea) else ""
        if not valor:
            continue
        try:
            fila.montos[columna] = motor.parsear_monto(valor)
        except motor.ErrorCalculo as error:
            errores.append(f"Columna {columna}: {error}")

    base = celda("monto_base")
    if base:
        try:
            fila.monto_base = motor.parsear_monto(base)
        except motor.ErrorCalculo as error:
            errores.append(f"Monto base: {error}")

    if not fila.montos and not any(e.startswith("Columna") for e in errores):
        errores.append("No informa ningún monto")

    fila.error = "; ".join(errores)
    return fila


def _validar_filas(filas, corredora):
    """Validaciones que miran más allá de la fila: reglas de negocio y duplicados."""
    ejercicios = {int(f.ejercicio) for f in filas if not f.error}
    # RN2: llaves donde ya existe el dato del corredor (no se pisa con dato de Bolsa).
    del_corredor = set(
        Calificacion.objects.filter(
            corredora=corredora, ejercicio__in=ejercicios, eliminada=False, origen=Origen.CORREDOR
        ).values_list("ejercicio", "mercado", "instrumento", "secuencia")
    )
    vistas = {}
    for fila in filas:
        if fila.error:
            continue
        try:
            _, resultado = services.calcular(fila.montos, fila.monto_base)
        except services.ErrorValidacion as error:
            fila.error = "; ".join(error.mensajes)
            continue
        if not resultado.cumple:
            fila.error = services.mensaje_rn1(resultado)
            continue
        llave = (int(fila.ejercicio), fila.mercado_codigo, fila.instrumento, int(fila.secuencia))
        if llave in vistas:
            fila.error = f"Llave repetida: ya aparece en la fila {vistas[llave]}"
            continue
        vistas[llave] = fila.numero
        if fila.origen == Origen.BOLSA and llave in del_corredor:
            fila.error = "RN2: ya existe el dato del corredor; prevalece sobre el dato de Bolsa"


def leer_csv(texto, corredora):
    """Lee y valida el archivo. Devuelve la lista de ``FilaCarga`` (con su error, si lo hay)."""
    texto = texto.lstrip("﻿")
    if not texto.strip():
        raise ErrorArchivo("El archivo está vacío.")
    primera = texto.splitlines()[0]
    delimitador = ";" if primera.count(";") > primera.count(",") else ","
    lector = csv.reader(io.StringIO(texto), delimiter=delimitador)
    encabezado = [_normalizar(h) for h in next(lector)]

    faltan = [c for c in ENCABEZADOS_OBLIGATORIOS if c not in encabezado]
    if faltan:
        raise ErrorArchivo("Faltan columnas obligatorias: " + ", ".join(faltan) + ".")

    columnas_monto = {}
    for posicion, nombre in enumerate(encabezado):
        coincide = re.fullmatch(r"monto[_ ]?(\d+)", nombre)
        if coincide:
            columnas_monto[int(coincide.group(1))] = posicion
    if not columnas_monto:
        raise ErrorArchivo("No hay columnas de monto (monto_8, monto_9, ...).")
    desde, hasta = settings.COLUMNAS_FACTOR
    fuera = sorted(c for c in columnas_monto if not desde <= c <= hasta)
    if fuera:
        raise ErrorArchivo(f"Las columnas de monto deben estar entre {desde} y {hasta}: {fuera}.")

    indice = {nombre: posicion for posicion, nombre in enumerate(encabezado)}
    filas = []
    for linea in lector:
        if not any(celda.strip() for celda in linea):
            continue
        if len(filas) >= settings.CARGA_MAX_FILAS:
            raise ErrorArchivo(f"El archivo supera el máximo de {settings.CARGA_MAX_FILAS} filas.")
        filas.append(_leer_fila(len(filas) + 1, linea, indice, columnas_monto))
    if not filas:
        raise ErrorArchivo("El archivo no tiene filas de datos.")

    _validar_filas(filas, corredora)
    return filas


def ejecutar_carga(usuario, filas, nombre_archivo):
    """Guarda las filas válidas, rechaza las inválidas y deja todo en la bitácora."""
    resultado = ResultadoCarga(total=len(filas))
    for fila in filas:
        if fila.error:
            resultado.rechazadas.append((fila.numero, fila.error))
            continue
        try:
            guardado = services.guardar_calificacion(
                usuario,
                ejercicio=int(fila.ejercicio),
                mercado=fila.mercado_codigo,
                instrumento=fila.instrumento,
                secuencia=int(fila.secuencia),
                origen=fila.origen,
                montos=fila.montos,
                monto_base=fila.monto_base,
                via=Registro.Origen.CARGA_MASIVA,
            )
        except services.ErrorValidacion as error:
            resultado.rechazadas.append((fila.numero, "; ".join(error.mensajes)))
            continue
        if guardado.estado == "creada":
            resultado.nuevas += 1
        elif guardado.estado == "actualizada":
            resultado.actualizadas += 1
        else:
            resultado.sin_cambios += 1

    registrar(
        usuario,
        Registro.Operacion.CARGA_MASIVA,
        nombre_archivo,
        origen=Registro.Origen.CARGA_MASIVA,
        detalle=(
            f"{resultado.total} filas leídas: {resultado.nuevas} nuevas, "
            f"{resultado.actualizadas} actualizadas, {resultado.sin_cambios} sin cambios, "
            f"{len(resultado.rechazadas)} rechazadas."
        ),
    )
    return resultado
