from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from bitacora.models import Registro
from bitacora.servicios import registrar


@receiver(user_logged_in)
def registrar_acceso(sender, request, user, **kwargs):
    if getattr(user, "perfil", None):
        registrar(
            user,
            Registro.Operacion.ACCESO,
            "Inicio de sesión",
            origen=Registro.Origen.SISTEMA,
        )
