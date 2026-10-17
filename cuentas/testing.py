from django.contrib.auth import get_user_model

from .models import Corredora, Perfil

CLAVE_PRUEBA = "clave-de-prueba-123"


def crear_corredora(nombre="Corredora Andina S.A."):
    return Corredora.objects.get_or_create(nombre=nombre)[0]


def crear_usuario(username, corredora, rol=Perfil.Rol.ANALISTA, nombre=""):
    usuario = get_user_model().objects.create_user(
        username=username, password=CLAVE_PRUEBA, first_name=nombre or username
    )
    Perfil.objects.create(usuario=usuario, corredora=corredora, rol=rol)
    return usuario
