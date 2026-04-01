from rest_framework.routers import DefaultRouter
from .views import EmpresaView, InstalacionView, SectorView

r = DefaultRouter()
r.register("empresas", EmpresaView, basename="empresa")
r.register("instalaciones", InstalacionView, basename="instalacion")
r.register("sectores", SectorView, basename="sector")

urlpatterns = r.urls