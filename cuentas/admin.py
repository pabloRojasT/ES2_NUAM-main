from django.contrib import admin

from .models import Corredora, Perfil


@admin.register(Corredora)
class CorredoraAdmin(admin.ModelAdmin):
    list_display = ("nombre", "creada")
    search_fields = ("nombre",)


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ("usuario", "corredora", "rol")
    list_filter = ("corredora", "rol")
