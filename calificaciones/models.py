from decimal import Decimal

from django.conf import settings
from django.db import models


class Mercado(models.TextChoices):
    ACCIONES = "ACCIONES", "Acciones"
    CFI = "CFI", "Cuotas de fondos de inversión"
    FONDOS_MUTUOS = "FONDOS_MUTUOS", "Fondos mutuos"


class Origen(models.TextChoices):
    CORREDOR = "CORREDOR", "Dato del corredor"
    BOLSA = "BOLSA", "Dato base de Bolsa"


class Calificacion(models.Model):
    """Calificación tributaria de un instrumento, de una corredora, en un ejercicio.

    La llave única (RN4, supuesto por confirmar) es: corredora + ejercicio +
    mercado + instrumento + secuencia de evento. Los montos y factores se guardan
    como texto dentro de un JSON para no perder los ocho decimales.
    """

    corredora = models.ForeignKey(
        "cuentas.Corredora", on_delete=models.PROTECT, related_name="calificaciones"
    )
    ejercicio = models.PositiveSmallIntegerField()
    mercado = models.CharField(max_length=20, choices=Mercado.choices)
    instrumento = models.CharField(max_length=60)
    secuencia = models.PositiveIntegerField()
    origen = models.CharField(max_length=10, choices=Origen.choices, default=Origen.CORREDOR)

    montos = models.JSONField(default=dict)        # {"8": "500000", "9": "500000"}
    monto_base = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    factores = models.JSONField(default=dict)      # {"8": "0.50000000", ...}
    suma_factores = models.DecimalField(max_digits=12, decimal_places=8)

    # Eliminación lógica (RN3): el registro se conserva pero deja de mostrarse.
    eliminada = models.BooleanField(default=False, db_index=True)

    creada = models.DateTimeField(auto_now_add=True)
    modificada = models.DateTimeField(auto_now=True)
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    modificada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-ejercicio", "mercado", "instrumento", "secuencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["corredora", "ejercicio", "mercado", "instrumento", "secuencia"],
                name="llave_unica_calificacion",
            )
        ]

    def __str__(self):
        return f"{self.ejercicio} · {self.get_mercado_display()} · {self.instrumento} · sec. {self.secuencia}"

    @property
    def montos_decimal(self):
        return {int(columna): Decimal(valor) for columna, valor in self.montos.items()}

    @property
    def etiqueta(self):
        """Cómo se nombra el registro en la bitácora y los mensajes."""
        return f"{self.instrumento} · sec. {self.secuencia}"
