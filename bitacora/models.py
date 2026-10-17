from django.conf import settings
from django.db import models
from django.utils import timezone


class ErrorBitacoraInmutable(Exception):
    """Se intentó modificar o borrar un registro de la bitácora."""


class RegistroQuerySet(models.QuerySet):
    """Bloquea las operaciones masivas que alterarían registros existentes."""

    def update(self, **kwargs):
        raise ErrorBitacoraInmutable("La bitácora es inalterable: no se puede modificar.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ErrorBitacoraInmutable("La bitácora es inalterable: no se puede modificar.")

    def delete(self):
        raise ErrorBitacoraInmutable("La bitácora es inalterable: no se puede borrar.")


class Registro(models.Model):
    class Operacion(models.TextChoices):
        INGRESO = "INGRESO", "Ingreso"
        MODIFICACION = "MODIFICACION", "Modificación"
        ELIMINACION = "ELIMINACION", "Eliminación"
        CARGA_MASIVA = "CARGA_MASIVA", "Carga masiva"
        INTENTO_RECHAZADO = "INTENTO_RECHAZADO", "Intento rechazado"
        ACCESO = "ACCESO", "Inicio de sesión"
        ADMINISTRACION = "ADMINISTRACION", "Administración de usuarios"

    class Origen(models.TextChoices):
        FORMULARIO = "FORMULARIO", "Formulario web"
        CARGA_MASIVA = "CARGA_MASIVA", "Carga masiva"
        SISTEMA = "SISTEMA", "Sistema"

    fecha = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    usuario_nombre = models.CharField(max_length=150)
    corredora = models.ForeignKey(
        "cuentas.Corredora", null=True, on_delete=models.PROTECT, related_name="+"
    )
    operacion = models.CharField(max_length=20, choices=Operacion.choices, db_index=True)
    registro = models.CharField(max_length=200)
    origen = models.CharField(max_length=12, choices=Origen.choices, default=Origen.FORMULARIO)
    detalle = models.TextField(blank=True)

    objects = RegistroQuerySet.as_manager()

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "registro de bitácora"
        verbose_name_plural = "registros de bitácora"

    def __str__(self):
        return f"{self.fecha:%d-%m-%Y %H:%M} · {self.usuario_nombre} · {self.get_operacion_display()}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ErrorBitacoraInmutable("La bitácora es inalterable: no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ErrorBitacoraInmutable("La bitácora es inalterable: no se puede borrar.")
