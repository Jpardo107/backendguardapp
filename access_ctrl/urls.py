from django.urls import path, include
from .views import IngresoView, SalidaView, AccesoListView
from rest_framework.routers import DefaultRouter
from .views_user import UsuarioViewSet

router = DefaultRouter()
router.register(r'usuarios', UsuarioViewSet, basename='usuarios')

urlpatterns = [
    path("accesos/ingreso/", IngresoView.as_view(), name="accesos_ingreso"),
    path("accesos/salida/", SalidaView.as_view(), name="accesos_salida"),
    path('', include(router.urls)),
    path("accesos/", AccesoListView.as_view(), name="listar-accesos"),
]
