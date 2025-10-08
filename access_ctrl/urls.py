from django.urls import path, include
from .views import IngresoView, SalidaView, AccesoListView, BuscarPorRUTView, BuscarPorDNIView, RegistrarVisitaView, \
    buscar_ultimo_acceso_por_rut
from rest_framework.routers import DefaultRouter

from .views_token import CustomTokenObtainPairView
from .views_user import UsuarioViewSet

router = DefaultRouter()
router.register(r'usuarios', UsuarioViewSet, basename='usuarios')

urlpatterns = [
    path("accesos/ingreso/", IngresoView.as_view(), name="accesos_ingreso"),
    path("accesos/salida/", SalidaView.as_view(), name="accesos_salida"),
    path('', include(router.urls)),
    path("accesos/", AccesoListView.as_view(), name="listar-accesos"),
    path('visitas/buscar-rut/<str:rut>/', BuscarPorRUTView.as_view(), name='buscar_por_rut'),
    path('visitas/buscar-dni/<str:dni>/', BuscarPorDNIView.as_view(), name='buscar_por_dni'),
    path('visitas/crear/', RegistrarVisitaView.as_view(), name='crear_visita'),
    path("auth/token/id/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("accesos/buscar-ultimo/<str:rut>/", buscar_ultimo_acceso_por_rut, name="buscar_ultimo_acceso_por_rut"),
]
