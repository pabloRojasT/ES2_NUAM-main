import importlib.util

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/calificaciones/", permanent=False)),
]

for _app in settings.APPS_LOCALES:
    if importlib.util.find_spec(f"{_app}.urls"):
        urlpatterns.append(path("", include(f"{_app}.urls")))
