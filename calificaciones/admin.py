from django.contrib import admin

from .models import Calificacion


@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    """Consulta en el admin. Para ingresar o modificar datos se usa la aplicación,
    que calcula los factores, valida las reglas y deja constancia en la bitácora."""

    list_display = ("instrumento", "secuencia", "ejercicio", "mercado", "origen", "corredora", "eliminada")
    list_filter = ("corredora", "ejercicio", "mercado", "origen", "eliminada")
    search_fields = ("instrumento",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
