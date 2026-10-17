from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.decorators.http import require_GET

from cuentas.permisos import requiere_permiso

from .models import Registro

User = get_user_model()


def _fecha(texto):
    for formato in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            continue
    return None


@requiere_permiso("ver_bitacora")
@require_GET
def lista(request):
    corredora = request.user.perfil.corredora
    registros = Registro.objects.filter(corredora=corredora)

    usuario = request.GET.get("usuario", "")
    operacion = request.GET.get("operacion", "")
    desde = request.GET.get("desde", "")
    hasta = request.GET.get("hasta", "")
    if usuario.isdigit():
        registros = registros.filter(usuario_id=int(usuario))
    if operacion in Registro.Operacion.values:
        registros = registros.filter(operacion=operacion)
    if _fecha(desde):
        registros = registros.filter(fecha__date__gte=_fecha(desde))
    if _fecha(hasta):
        registros = registros.filter(fecha__date__lte=_fecha(hasta))

    pagina = Paginator(registros, 50).get_page(request.GET.get("pagina"))
    ver = request.GET.get("ver", "")
    seleccionado = registros.filter(pk=int(ver)).first() if ver.isdigit() else None
    if seleccionado is None and pagina.object_list:
        seleccionado = pagina.object_list[0]

    return render(
        request,
        "bitacora/lista.html",
        {
            "pagina": pagina,
            "seleccionado": seleccionado,
            "operaciones": Registro.Operacion.choices,
            "usuarios": User.objects.filter(perfil__corredora=corredora).order_by("username"),
            "filtros": {"usuario": usuario, "operacion": operacion, "desde": desde, "hasta": hasta},
            "seccion": "bitacora",
        },
    )
