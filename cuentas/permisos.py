from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def perfil_de(usuario):
    return getattr(usuario, "perfil", None)


def tiene_permiso(usuario, permiso):
    perfil = perfil_de(usuario)
    return bool(
        usuario.is_authenticated and usuario.is_active and perfil and perfil.tiene_permiso(permiso)
    )


def denegar(request, motivo): 
    from bitacora.models import Registro
    from bitacora.servicios import registrar

    if perfil_de(request.user):
        registrar(
            request.user,
            Registro.Operacion.INTENTO_RECHAZADO,
            motivo,
            detalle=f"{request.method} {request.path}",
        )
    raise PermissionDenied(motivo)


def requiere_permiso(permiso):
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not tiene_permiso(request.user, permiso):
                denegar(request, f"Acceso denegado: se requiere el permiso «{permiso}»")
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
