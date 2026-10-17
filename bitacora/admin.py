from django.contrib import admin

from .models import Registro


@admin.register(Registro)
class RegistroAdmin(admin.ModelAdmin):

    list_display = ("fecha", "usuario_nombre", "operacion", "registro", "origen", "corredora")
    list_filter = ("operacion", "origen", "corredora")
    search_fields = ("usuario_nombre", "registro", "detalle")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
