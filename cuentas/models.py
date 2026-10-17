from django.conf import settings
from django.db import models


class Corredora(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name_plural = "corredoras"

    def __str__(self):
        return self.nombre


class Perfil(models.Model):
    class Rol(models.TextChoices):
        ANALISTA = "ANALISTA", "Analista tributario"
        ADMIN = "ADMIN", "Administrador de corredora"
        AUDITOR = "AUDITOR", "Auditor / revisor"

    PERMISOS = {
        "consultar": (Rol.ANALISTA, Rol.ADMIN, Rol.AUDITOR),
        "editar": (Rol.ANALISTA, Rol.ADMIN),
        "ver_bitacora": (Rol.ADMIN, Rol.AUDITOR),
        "gestionar_usuarios": (Rol.ADMIN,),
    }

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil"
    )
    corredora = models.ForeignKey(Corredora, on_delete=models.PROTECT, related_name="perfiles")
    rol = models.CharField(max_length=10, choices=Rol.choices)

    def __str__(self):
        return f"{self.usuario} · {self.get_rol_display()} · {self.corredora}"

    def tiene_permiso(self, permiso):
        return self.rol in self.PERMISOS.get(permiso, ())

    @property
    def puede_editar(self):
        return self.tiene_permiso("editar")

    @property
    def puede_ver_bitacora(self):
        return self.tiene_permiso("ver_bitacora")

    @property
    def puede_gestionar_usuarios(self):
        return self.tiene_permiso("gestionar_usuarios")
