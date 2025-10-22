from django.urls import path, include
from .views import IngresoView, SalidaView, AccesoListView, BuscarPorRUTView, BuscarPorDNIView, RegistrarVisitaView, \
    buscar_ultimo_acceso_por_rut, VisitasPorInstalacionView, VisitaUpdateView, AccesosUltimas24View, \
    AccesosDiaEnCursoView, AccesosPorMesView, SectoresPorInstalacionView, AccesoUpdateAdminView, CargaMasivaAccesosView
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
    path('instalaciones/<int:instalacion_id>/visitas/', VisitasPorInstalacionView.as_view(),
         name='visitas_por_instalacion'),
    path('visitas/<int:pk>/', VisitaUpdateView.as_view(), name='actualizar_visita'),

    path("accesos/ultimas-24h/", AccesosUltimas24View.as_view(), name="accesos_ultimas_24h"),
    path("accesos/dia-curso/", AccesosDiaEnCursoView.as_view(), name="accesos_dia_curso"),
    path("accesos/por-mes/", AccesosPorMesView.as_view(), name="accesos_por_mes"),
    path('instalaciones/<int:instalacion_id>/sectores/', SectoresPorInstalacionView.as_view(),
         name='sectores_por_inst'),
    path('accesos/<int:pk>/', AccesoUpdateAdminView.as_view(), name='editar_acceso'),
    path("accesos/carga-masiva/", CargaMasivaAccesosView.as_view(), name="carga_masiva_accesos"),
]
