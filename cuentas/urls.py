from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path(
        "ingresar/",
        auth_views.LoginView.as_view(
            template_name="cuentas/login.html", redirect_authenticated_user=True
        ),
        name="ingresar",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="salir"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/<int:pk>/cambiar/", views.usuario_cambiar, name="usuario_cambiar"),
]
