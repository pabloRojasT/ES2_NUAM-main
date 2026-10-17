from django.urls import path

from . import views

app_name = "calificaciones"

urlpatterns = [
    path("calificaciones/", views.lista, name="lista"),
    path("calificaciones/nueva/", views.formulario, name="nueva"),
    path("calificaciones/<int:pk>/editar/", views.formulario, name="editar"),
    path("calificaciones/<int:pk>/eliminar/", views.eliminar, name="eliminar"),
    path("carga/", views.carga_subir, name="carga"),
    path("carga/plantilla.csv", views.carga_plantilla, name="carga_plantilla"),
    path("carga/vista-previa/", views.carga_previa, name="carga_previa"),
    path("carga/confirmar/", views.carga_confirmar, name="carga_confirmar"),
    path("carga/resultado/", views.carga_resultado, name="carga_resultado"),
]
