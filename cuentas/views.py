from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from bitacora.models import Registro
from bitacora.servicios import registrar

from .models import Perfil
from .permisos import denegar, requiere_permiso

User = get_user_model()


class FormUsuario(forms.Form):
    correo = forms.EmailField(label="Correo")
    nombre = forms.CharField(label="Nombre", max_length=80)
    rol = forms.ChoiceField(label="Perfil", choices=Perfil.Rol.choices)
    clave = forms.CharField(label="Contraseña inicial", widget=forms.PasswordInput)

    def clean_correo(self):
        correo = self.cleaned_data["correo"].lower()
        if User.objects.filter(username__iexact=correo).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return correo

    def clean_clave(self):
        clave = self.cleaned_data["clave"]
        validate_password(clave)
        return clave


@requiere_permiso("gestionar_usuarios")
@require_http_methods(["GET", "POST"])
def usuarios(request):
    """Lista los usuarios de la corredora y permite crear nuevos."""
    corredora = request.user.perfil.corredora
    if request.method == "POST":
        form = FormUsuario(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            with transaction.atomic():
                nuevo = User.objects.create_user(
                    username=datos["correo"],
                    email=datos["correo"],
                    first_name=datos["nombre"],
                    password=datos["clave"],
                )
                Perfil.objects.create(usuario=nuevo, corredora=corredora, rol=datos["rol"])
                registrar(
                    request.user,
                    Registro.Operacion.ADMINISTRACION,
                    f"Usuario {nuevo.username}",
                    detalle=f"Alta con perfil {Perfil.Rol(datos['rol']).label}.",
                )
            messages.success(request, f"Usuario {nuevo.username} creado.")
            return redirect("cuentas:usuarios")
    else:
        form = FormUsuario()
    perfiles = (
        Perfil.objects.filter(corredora=corredora)
        .select_related("usuario")
        .order_by("usuario__username")
    )
    return render(
        request,
        "cuentas/usuarios.html",
        {"form": form, "perfiles": perfiles, "roles": Perfil.Rol.choices, "seccion": "usuarios"},
    )


@requiere_permiso("gestionar_usuarios")
@require_POST
def usuario_cambiar(request, pk):
    """Cambia el perfil o activa/desactiva a un usuario de la misma corredora."""
    perfil = get_object_or_404(Perfil.objects.select_related("usuario"), pk=pk)
    if perfil.corredora_id != request.user.perfil.corredora_id:
        denegar(request, "Intento de modificar un usuario de otra corredora")
    if perfil.usuario_id == request.user.pk:
        messages.error(request, "No puedes cambiar tu propio perfil ni desactivarte.")
        return redirect("cuentas:usuarios")

    accion = request.POST.get("accion")
    if accion == "rol" and request.POST.get("rol") in Perfil.Rol.values:
        perfil.rol = request.POST["rol"]
        perfil.save(update_fields=["rol"])
        detalle = f"Perfil cambiado a {perfil.get_rol_display()}."
    elif accion in ("activar", "desactivar"):
        perfil.usuario.is_active = accion == "activar"
        perfil.usuario.save(update_fields=["is_active"])
        detalle = "Usuario activado." if accion == "activar" else "Usuario desactivado."
    else:
        messages.error(request, "Acción no válida.")
        return redirect("cuentas:usuarios")

    registrar(
        request.user,
        Registro.Operacion.ADMINISTRACION,
        f"Usuario {perfil.usuario.username}",
        detalle=detalle,
    )
    messages.success(request, detalle)
    return redirect("cuentas:usuarios")
