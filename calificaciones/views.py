import dataclasses

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from cuentas.permisos import requiere_permiso

from . import carga, motor, services
from .models import Calificacion, Mercado, Origen

COLUMNAS = list(range(settings.COLUMNAS_FACTOR[0], settings.COLUMNAS_FACTOR[1] + 1))


# --- Lista, ingreso, edición y eliminación -----------------------------------

@requiere_permiso("consultar")
@require_GET
def lista(request):
    corredora = request.user.perfil.corredora
    base = Calificacion.objects.filter(corredora=corredora, eliminada=False)
    calificaciones = base

    mercado = request.GET.get("mercado", "")
    origen = request.GET.get("origen", "")
    ejercicio = request.GET.get("ejercicio", "")
    busqueda = request.GET.get("q", "").strip()
    if mercado in Mercado.values:
        calificaciones = calificaciones.filter(mercado=mercado)
    if origen in Origen.values:
        calificaciones = calificaciones.filter(origen=origen)
    if ejercicio.isdigit():
        calificaciones = calificaciones.filter(ejercicio=int(ejercicio))
    if busqueda:
        calificaciones = calificaciones.filter(instrumento__icontains=busqueda)

    pagina = Paginator(calificaciones, 25).get_page(request.GET.get("pagina"))
    return render(
        request,
        "calificaciones/lista.html",
        {
            "pagina": pagina,
            "total": base.count(),
            "mercados": Mercado.choices,
            "origenes": Origen.choices,
            "ejercicios": sorted(
                base.order_by().values_list("ejercicio", flat=True).distinct(), reverse=True
            ),
            "filtros": {"mercado": mercado, "origen": origen, "ejercicio": ejercicio, "q": busqueda},
            "columnas_regla": settings.COLUMNAS_SUMA_REGLA,
            "seccion": "calificaciones",
        },
    )


def _leer_montos(montos_txt, base_txt):
    """Convierte los textos del formulario en montos. Devuelve (montos, monto_base, errores)."""
    montos, errores, monto_base = {}, [], None
    for columna, texto in montos_txt.items():
        if not texto:
            continue
        try:
            montos[columna] = motor.parsear_monto(texto)
        except motor.ErrorCalculo as error:
            errores.append(f"Columna {columna}: {error}.")
    if base_txt:
        try:
            monto_base = motor.parsear_monto(base_txt)
        except motor.ErrorCalculo as error:
            errores.append(f"Monto base: {error}.")
    return montos, monto_base, errores


@requiere_permiso("editar")
@require_http_methods(["GET", "POST"])
def formulario(request, pk=None):
    """Ingreso de una calificación nueva o edición de una existente.

    El botón «Calcular» muestra los factores y el estado de RN1 sin guardar;
    «Guardar» calcula, valida y guarda.
    """
    calificacion = services.obtener_calificacion(request.user, pk) if pk else None

    if calificacion:
        datos = {
            "ejercicio": calificacion.ejercicio,
            "mercado": calificacion.mercado,
            "instrumento": calificacion.instrumento,
            "secuencia": calificacion.secuencia,
            "origen": calificacion.origen,
        }
        montos_txt = {c: "" for c in COLUMNAS}
        montos_txt.update({int(c): m for c, m in calificacion.montos.items()})
        base_txt = format(calificacion.monto_base, "f") if calificacion.monto_base is not None else ""
    else:
        datos = {
            "ejercicio": timezone.localdate().year - 1,
            "mercado": Mercado.ACCIONES,
            "instrumento": "",
            "secuencia": 1,
            "origen": Origen.CORREDOR,
        }
        montos_txt = {c: "" for c in COLUMNAS}
        base_txt = ""

    errores, factores_txt, resultado = [], {}, None

    if request.method == "POST":
        if not calificacion:
            for clave in datos:
                datos[clave] = request.POST.get(clave, "").strip()
        for columna in COLUMNAS:
            montos_txt[columna] = request.POST.get(f"monto_{columna}", "").strip()
        base_txt = request.POST.get("monto_base", "").strip()

        montos, monto_base, errores = _leer_montos(montos_txt, base_txt)
        if not errores:
            try:
                factores, resultado = services.calcular(montos, monto_base)
            except services.ErrorValidacion as error:
                errores = error.mensajes
        if not errores:
            factores_txt = {c: motor.a_texto(f) for c, f in factores.items()}
            if not resultado.cumple:
                errores = [services.mensaje_rn1(resultado)]
            elif request.POST.get("accion") == "guardar":
                try:
                    guardado = services.guardar_calificacion(
                        request.user,
                        ejercicio=datos["ejercicio"],
                        mercado=datos["mercado"],
                        instrumento=datos["instrumento"],
                        secuencia=datos["secuencia"],
                        origen=datos["origen"],
                        montos=montos,
                        monto_base=monto_base,
                    )
                except services.ErrorValidacion as error:
                    errores = error.mensajes
                else:
                    textos = {
                        "creada": "Calificación guardada. El ingreso quedó registrado en la bitácora.",
                        "actualizada": "Calificación actualizada. El cambio quedó registrado en la bitácora.",
                        "sin_cambios": "No había cambios que guardar.",
                    }
                    messages.success(request, textos[guardado.estado])
                    return redirect("calificaciones:lista")

    corte = settings.COLUMNAS_SUMA_REGLA[1]
    filas = [{"columna": c, "monto": montos_txt[c], "factor": factores_txt.get(c, "")} for c in COLUMNAS]
    return render(
        request,
        "calificaciones/formulario.html",
        {
            "calificacion": calificacion,
            "datos": datos,
            "mercados": Mercado.choices,
            "origenes": Origen.choices,
            "base_txt": base_txt,
            "filas_principales": [f for f in filas if f["columna"] <= corte],
            "filas_extra": [f for f in filas if f["columna"] > corte],
            "errores": errores,
            "resultado": resultado,
            "suma_texto": motor.a_texto(resultado.suma) if resultado else "",
            "bloqueado": bool(resultado and not resultado.cumple),
            "modo_redondeo": settings.FACTORES_MODO_REDONDEO,
            "columnas_regla": settings.COLUMNAS_SUMA_REGLA,
            "seccion": "calificaciones",
        },
    )


@requiere_permiso("editar")
@require_http_methods(["GET", "POST"])
def eliminar(request, pk):
    calificacion = services.obtener_calificacion(request.user, pk)
    if request.method == "POST":
        services.eliminar_logico(request.user, calificacion)
        messages.success(
            request,
            "Calificación eliminada (lógica). La operación quedó registrada en la bitácora.",
        )
        return redirect("calificaciones:lista")
    return render(
        request,
        "calificaciones/eliminar.html",
        {"calificacion": calificacion, "seccion": "calificaciones"},
    )


# --- Carga masiva (3 pasos) --------------------------------------------------

@requiere_permiso("editar")
@require_http_methods(["GET", "POST"])
def carga_subir(request):
    """Paso 1: elegir el archivo."""
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        error = None
        if not archivo:
            error = "Selecciona un archivo CSV."
        elif not archivo.name.lower().endswith(".csv"):
            error = "El archivo debe tener extensión .csv."
        elif archivo.size > settings.CARGA_MAX_BYTES:
            error = f"El archivo supera el máximo de {settings.CARGA_MAX_BYTES // 1_000_000} MB."
        else:
            try:
                texto = archivo.read().decode("utf-8-sig")
                carga.leer_csv(texto, request.user.perfil.corredora)
            except UnicodeDecodeError:
                error = "El archivo debe estar codificado en UTF-8."
            except carga.ErrorArchivo as problema:
                error = str(problema)
        if error:
            messages.error(request, error)
        else:
            request.session["carga_texto"] = texto
            request.session["carga_nombre"] = archivo.name
            return redirect("calificaciones:carga_previa")
    return render(request, "calificaciones/carga_subir.html", {"seccion": "carga"})


def _filas_en_sesion(request):
    texto = request.session.get("carga_texto")
    if not texto:
        return None
    return carga.leer_csv(texto, request.user.perfil.corredora)


@requiere_permiso("editar")
@require_GET
def carga_previa(request):
    """Paso 2: vista previa fila por fila. No se guarda nada todavía."""
    try:
        filas = _filas_en_sesion(request)
    except carga.ErrorArchivo as error:
        messages.error(request, str(error))
        return redirect("calificaciones:carga")
    if filas is None:
        messages.error(request, "Primero selecciona un archivo.")
        return redirect("calificaciones:carga")
    con_error = [f for f in filas if f.error]
    solo_errores = request.GET.get("errores") == "1"
    mostradas = (con_error if solo_errores else filas)[:200]
    return render(
        request,
        "calificaciones/carga_previa.html",
        {
            "nombre": request.session.get("carga_nombre", ""),
            "total": len(filas),
            "validas": len(filas) - len(con_error),
            "con_error": len(con_error),
            "filas": mostradas,
            "solo_errores": solo_errores,
            "seccion": "carga",
        },
    )


@requiere_permiso("editar")
@require_POST
def carga_confirmar(request):
    """Paso 3: guarda las filas válidas y rechaza las inválidas."""
    try:
        filas = _filas_en_sesion(request)
    except carga.ErrorArchivo as error:
        messages.error(request, str(error))
        return redirect("calificaciones:carga")
    if filas is None:
        messages.error(request, "Primero selecciona un archivo.")
        return redirect("calificaciones:carga")
    resultado = carga.ejecutar_carga(request.user, filas, request.session.get("carga_nombre", "archivo.csv"))
    request.session["carga_resultado"] = dataclasses.asdict(resultado)
    request.session.pop("carga_texto", None)
    request.session.pop("carga_nombre", None)
    return redirect("calificaciones:carga_resultado")


@requiere_permiso("editar")
@require_GET
def carga_resultado(request):
    resultado = request.session.get("carga_resultado")
    if not resultado:
        return redirect("calificaciones:carga")
    return render(
        request,
        "calificaciones/carga_resultado.html",
        {
            "resultado": resultado,
            "procesadas": resultado["nuevas"] + resultado["actualizadas"] + resultado["sin_cambios"],
            "seccion": "carga",
        },
    )


@requiere_permiso("editar")
@require_GET
def carga_plantilla(request):
    """Descarga un CSV de ejemplo con el formato que espera la carga masiva."""
    columnas = range(settings.COLUMNAS_SUMA_REGLA[0], settings.COLUMNAS_SUMA_REGLA[1] + 1)
    encabezado = ["ejercicio", "mercado", "instrumento", "secuencia", "origen"]
    encabezado += [f"monto_{c}" for c in columnas] + ["monto_base"]
    ejemplo = ["2025", "Acciones", "ACCION-EJEMPLO", "1", "corredor", "1000000", "1000000", "1000000"]
    ejemplo += [""] * (len(encabezado) - len(ejemplo))
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="plantilla_calificaciones.csv"'
    respuesta.write(",".join(encabezado) + "\n" + ",".join(ejemplo) + "\n")
    return respuesta
