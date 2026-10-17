from .models import Registro


def registrar(usuario, operacion, registro, *, origen=Registro.Origen.FORMULARIO, detalle="", corredora=None):
    if corredora is None:
        perfil = getattr(usuario, "perfil", None)
        corredora = perfil.corredora if perfil else None
    nombre = usuario.get_full_name() or usuario.get_username()
    return Registro.objects.create(
        usuario=usuario,
        usuario_nombre=nombre,
        corredora=corredora,
        operacion=operacion,
        registro=str(registro)[:200],
        origen=origen,
        detalle=detalle,
    )
