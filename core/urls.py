from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmpresaView, InstalacionView, SectorView

r = DefaultRouter()
r.register("empresas", EmpresaView)
r.register("instalaciones", InstalacionView)
r.register("sectores", SectorView)

urlpatterns = [path("", include(r.urls))]
