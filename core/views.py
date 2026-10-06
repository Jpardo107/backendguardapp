from django.db.models.deletion import ProtectedError
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import Empresa, Instalacion, Sector
from .serializers import EmpresaSer, InstalacionSer, SectorSer
from .permissions import CatalogoPermission, es_admin_general, instalaciones_visibles


class CatalogoView(viewsets.ModelViewSet):
    permission_classes = [CatalogoPermission]

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError("No se puede eliminar: tiene historial de accesos. Conserve el registro para mantener la trazabilidad.")


class EmpresaView(CatalogoView):
    serializer_class = EmpresaSer

    def get_queryset(self):
        qs = Empresa.objects.all()
        return qs.order_by("id") if es_admin_general(self.request.user) else qs.filter(pk=self.request.user.empresa_id)

    def perform_create(self, serializer):
        if not es_admin_general(self.request.user):
            raise PermissionDenied("Solo la administración general puede crear empresas.")
        serializer.save()

    def perform_update(self, serializer):
        if not es_admin_general(self.request.user) and "es_administradora_general" in serializer.validated_data:
            raise PermissionDenied("No puede cambiar los permisos de la empresa.")
        serializer.save()

    def perform_destroy(self, instance):
        if not es_admin_general(self.request.user):
            raise PermissionDenied("Solo la administración general puede eliminar empresas.")
        super().perform_destroy(instance)


class InstalacionView(CatalogoView):
    serializer_class = InstalacionSer

    def get_queryset(self):
        qs = instalaciones_visibles(self.request.user)
        empresa = self.request.query_params.get("empresa_id")
        return (qs.filter(empresa_id=empresa) if empresa else qs).order_by("nombre")

    def perform_create(self, serializer):
        empresa = serializer.validated_data["empresa"]
        if not es_admin_general(self.request.user) and empresa.id != self.request.user.empresa_id:
            raise PermissionDenied("La instalación debe pertenecer a su empresa.")
        serializer.save()

    def perform_update(self, serializer):
        empresa = serializer.validated_data.get("empresa", serializer.instance.empresa)
        if empresa.id != serializer.instance.empresa_id:
            raise ValidationError("No se puede trasladar una instalación a otra empresa.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.visitas.exists():
            raise ValidationError("Esta instalación o sector tiene visitas enroladas. Gestione esos registros antes de eliminarlo.")
        if instance.usuarios.exists():
            raise ValidationError("Reasigne o elimine primero los usuarios de esta instalación.")
        super().perform_destroy(instance)


class SectorView(CatalogoView):
    serializer_class = SectorSer

    def get_queryset(self):
        qs = Sector.objects.filter(instalacion__in=instalaciones_visibles(self.request.user))
        inst = self.request.query_params.get("instalacion_id")
        return (qs.filter(instalacion_id=inst) if inst else qs).order_by("nombre")

    def perform_create(self, serializer):
        if not instalaciones_visibles(self.request.user).filter(pk=serializer.validated_data["instalacion"].id).exists():
            raise PermissionDenied("La instalación no pertenece a su empresa.")
        serializer.save()

    def perform_update(self, serializer):
        inst = serializer.validated_data.get("instalacion", serializer.instance.instalacion)
        if inst.id != serializer.instance.instalacion_id:
            raise ValidationError("No se puede trasladar un sector a otra instalación.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.visitas.exists():
            raise ValidationError("Esta instalación o sector tiene visitas enroladas. Gestione esos registros antes de eliminarlo.")
        if instance.usuarios.exists():
            raise ValidationError("Reasigne o elimine primero los usuarios de este sector.")
        super().perform_destroy(instance)
